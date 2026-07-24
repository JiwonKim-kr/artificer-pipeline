#!/usr/bin/env python3
"""play test — Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성 러너.

CLAUDE.md 검증 게이트를 로컬에서 부분 실행한다(‘play test’ 범위):
  Stage 1  Godot headless 임포트 성공          (게이트 #1)
  Stage 2  스모크 테스트 통과                    (게이트 #2)
  Stage 3  매니페스트 ↔ 스키마 + 실제 파일 정합성  (게이트 #4)

(네이밍/디렉토리 규칙 게이트 #3, lore 정본 모순 게이트 #5 는 상위 `verify`
명령의 몫이며 이 러너 범위 밖이다.)

옵트인 스테이지(`--screenshot`): 메인 씬(또는 --shot-scene)을 **실제로 렌더**해
PNG 스크린샷을 저장하고 비어있지 않은 렌더인지 검증한다. 스모크(게이트 #2)가
'씬이 로드/인스턴스화되는가'만 headless 로 빠르게 보는 반면, 이 스테이지는
'화면에 무엇이 보이는가'를 눈으로(그리고 픽셀 검사로) 판정하게 한다.
무겁고(실제 렌더) 창이 뜨므로 **기본 실행에는 포함하지 않는다** — 명시적으로
`--screenshot` 을 줄 때만 돈다. 기본 `play test` 는 headless 로 빠르게 유지한다.

단계적 설계: 프로젝트에 아직 씬이 없어도 각 스테이지가 의미 있게 동작한다.
Stage 2 스모크 테스트는 main_scene 미설정 시 부트/임포트만 확인하고 통과한다.

스크린샷 스테이지 플랫폼 주의:
  - 순수 `--headless` 는 더미 렌더 드라이버라 뷰포트 캡처가 불가(무한 대기)하므로 쓰지 않는다.
  - macOS/기타 GUI: `--rendering-driver opengl3` 로 실제 렌더(창이 잠깐 뜬다).
  - Linux(CI 등 GUI 없음): `xvfb-run` 가상 디스플레이로 래핑해야 실제 렌더가 된다.
  - macOS 에는 `timeout` 명령이 없으므로 파이썬 subprocess 로 타임아웃/프로세스 정리를 직접 한다.

종료 코드: 0 = 전체 통과, 1 = 한 스테이지 이상 실패, 2 = 러너 오류(godot 없음 등).
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import os
import shutil
import signal
import subprocess
import sys
import zlib
from pathlib import Path

# 같은 디렉토리의 manifest 모듈 재사용 (검증 로직 단일화)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


SMOKE_SCRIPT = "res://pipeline/tests/smoke_test.gd"
SCREENSHOT_SCRIPT = "res://pipeline/tests/screenshot.gd"
# 저장소 상대 기본 경로. pipeline/artifacts/ 는 .gitignore 로 커밋 대상에서 제외한다.
DEFAULT_SHOT_OUTPUT = "pipeline/artifacts/screenshot.png"


class Stage:
    def __init__(self, name: str):
        self.name = name
        self.ok = False
        self.detail = ""


def run_godot_import(godot: str, project_dir: Path) -> Stage:
    st = Stage("Godot headless 임포트")
    try:
        proc = subprocess.run(
            [godot, "--headless", "--path", str(project_dir), "--import"],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        st.detail = f"godot 실행 파일을 찾을 수 없음: {godot!r}"
        return st
    except subprocess.TimeoutExpired:
        st.detail = "임포트 타임아웃 (300s)"
        return st
    st.ok = proc.returncode == 0
    st.detail = (
        "임포트 성공"
        if st.ok
        else f"임포트 실패 (exit={proc.returncode})\n{proc.stderr.strip()}"
    )
    return st


def run_smoke(godot: str, project_dir: Path) -> Stage:
    st = Stage("스모크 테스트")
    try:
        proc = subprocess.run(
            [godot, "--headless", "--path", str(project_dir), "--script", SMOKE_SCRIPT],
            capture_output=True,
            text=True,
            timeout=300,
        )
    except FileNotFoundError:
        st.detail = f"godot 실행 파일을 찾을 수 없음: {godot!r}"
        return st
    except subprocess.TimeoutExpired:
        st.detail = "스모크 테스트 타임아웃 (300s)"
        return st
    out = proc.stdout
    # 스크립트가 명시적으로 출력하는 결과 마커를 신뢰(엔진 종료코드보다 확실)
    passed = "SMOKE_RESULT: PASS" in out and proc.returncode == 0
    st.ok = passed
    tail = "\n".join(line for line in out.splitlines() if line.startswith(("[", "SMOKE_RESULT")))
    st.detail = tail if tail else out.strip() or proc.stderr.strip()
    return st


def run_manifest_integrity(manifest_path: Path, schema_path: Path, project_dir: Path) -> Stage:
    st = Stage("매니페스트 정합성 (스키마 + 파일)")
    try:
        schema = manifest_mod.load_schema(str(schema_path))
        data = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError) as exc:
        st.detail = f"매니페스트/스키마 로드 실패: {exc}"
        return st

    errors = manifest_mod.validate_manifest(data, schema)
    problems: list[str] = [f"[{e.code}] {e.path}: {e.message}" for e in errors]

    # 파일 참조 정합성: file 이 지정된 entry 는 실제 파일이 존재해야 한다.
    for i, entry in enumerate(data.get("entries", [])):
        file_ref = entry.get("file")
        if file_ref:
            resolved = _resolve_res_path(file_ref, project_dir)
            if not resolved.exists():
                problems.append(
                    f"[missing_file] entries[{i}].file: 파일 없음 → {file_ref}"
                )

    st.ok = not problems
    st.detail = (
        f"entry {len(data.get('entries', []))}개 정합성 통과"
        if st.ok
        else "\n".join(problems)
    )
    return st


def _resolve_res_path(ref: str, project_dir: Path) -> Path:
    """매니페스트의 file 경로를 실제 파일시스템 경로로 해석."""
    if ref.startswith("res://"):
        return project_dir / ref[len("res://"):]
    p = Path(ref)
    return p if p.is_absolute() else project_dir / p


# ---------------------------------------------------------------------------
# 스크린샷(시각) 스테이지 — 옵트인
# ---------------------------------------------------------------------------
def build_screenshot_cmd(
    godot: str,
    project_dir: Path,
    output_path: Path,
    scene: str | None,
    frames: int,
    plat: str,
) -> list[str]:
    """플랫폼별 스크린샷 실행 커맨드를 구성한다(테스트 가능하도록 순수 함수로 분리).

    - **headless 금지**: 더미 렌더 드라이버는 뷰포트 캡처가 불가하다.
    - macOS/기타: 실제 렌더 드라이버(opengl3)로 직접 실행 — GUI 세션이라 창이 잠깐 뜬다.
    - Linux: GUI 가 없으므로 `xvfb-run` 가상 디스플레이로 래핑한 뒤 opengl3.

    plat 은 `sys.platform` 형식 문자열('darwin'|'linux'|...). 테스트에서 주입 가능.
    """
    godot_cmd = [
        godot, "--path", str(project_dir),
        "--rendering-driver", "opengl3",
        "--script", SCREENSHOT_SCRIPT,
        "--", "--output", str(output_path), "--frames", str(frames),
    ]
    if scene:
        godot_cmd += ["--scene", scene]
    if plat.startswith("linux"):
        # -a: 빈 디스플레이 번호 자동 선택. 화면은 뷰포트보다 크게 잡는다.
        return ["xvfb-run", "-a", "--server-args=-screen 0 1280x720x24", *godot_cmd]
    return godot_cmd


def _signal_group(proc: subprocess.Popen, sig: int) -> None:
    """자식(그리고 그 자식들: xvfb-run→Xvfb/godot)까지 프로세스 그룹 단위로 시그널."""
    try:
        os.killpg(os.getpgid(proc.pid), sig)
    except (ProcessLookupError, OSError):
        try:
            proc.send_signal(sig)  # 그룹 조회 실패 시 직접 프로세스에 폴백
        except (ProcessLookupError, OSError):
            pass


def _run_process_group(
    cmd: list[str], timeout: int, env: dict[str, str] | None = None
) -> tuple[int, str, str, bool]:
    """새 세션(프로세스 그룹)으로 실행하고 타임아웃 시 그룹 전체를 정리한다.

    macOS 에는 `timeout` 명령이 없고, xvfb-run 은 자식(Xvfb/godot)을 남기므로
    셸 timeout 대신 파이썬에서 프로세스 그룹째 종료한다(좀비/창 잔존 금지).
    반환: (returncode, stdout, stderr, timed_out).
    """
    proc = subprocess.Popen(
        cmd, stdout=subprocess.PIPE, stderr=subprocess.PIPE,
        text=True, env=env, start_new_session=True,
    )
    try:
        out, err = proc.communicate(timeout=timeout)
        return proc.returncode, out, err, False
    except subprocess.TimeoutExpired:
        pass
    # 타임아웃 → 그룹 전체 종료(SIGTERM → 안 죽으면 SIGKILL)
    _signal_group(proc, signal.SIGTERM)
    try:
        out, err = proc.communicate(timeout=8)
    except subprocess.TimeoutExpired:
        _signal_group(proc, signal.SIGKILL)
        try:
            out, err = proc.communicate(timeout=8)
        except subprocess.TimeoutExpired:
            out, err = "", ""
    rc = proc.returncode if proc.returncode is not None else -1
    return rc, out or "", err or "", True


def _find_marker(text: str, prefix: str) -> str | None:
    for line in text.splitlines():
        if line.startswith(prefix):
            return line[len(prefix):].strip()
    return None


def _tail(out: str, err: str, n: int = 12) -> str:
    lines = [ln for ln in out.splitlines() if ln.strip()][-n:]
    if err.strip():
        lines += ["[stderr]"] + err.splitlines()[-n:]
    return "\n".join(lines)


_PNG_SIG = b"\x89PNG\r\n\x1a\n"


def _read_png_dimensions(path: Path) -> tuple[int, int] | None:
    """PNG 시그니처 + IHDR 만 읽어 (width, height) 반환. 무압축 해제(가벼움)."""
    try:
        with open(path, "rb") as f:
            head = f.read(24)
    except OSError:
        return None
    if len(head) < 24 or head[:8] != _PNG_SIG or head[12:16] != b"IHDR":
        return None
    w = int.from_bytes(head[16:20], "big")
    h = int.from_bytes(head[20:24], "big")
    return (w, h)


def _paeth(a: int, b: int, c: int) -> int:
    p = a + b - c
    pa, pb, pc = abs(p - a), abs(p - b), abs(p - c)
    if pa <= pb and pa <= pc:
        return a
    if pb <= pc:
        return b
    return c


def _unfilter_line(
    ftype: int, line: bytes, prev: bytearray, bpp: int, stride: int
) -> bytearray | None:
    recon = bytearray(stride)
    if ftype == 0:            # None
        recon[:] = line
    elif ftype == 1:          # Sub
        for i in range(stride):
            a = recon[i - bpp] if i >= bpp else 0
            recon[i] = (line[i] + a) & 0xFF
    elif ftype == 2:          # Up
        for i in range(stride):
            recon[i] = (line[i] + prev[i]) & 0xFF
    elif ftype == 3:          # Average
        for i in range(stride):
            a = recon[i - bpp] if i >= bpp else 0
            recon[i] = (line[i] + ((a + prev[i]) >> 1)) & 0xFF
    elif ftype == 4:          # Paeth
        for i in range(stride):
            a = recon[i - bpp] if i >= bpp else 0
            c = prev[i - bpp] if i >= bpp else 0
            recon[i] = (line[i] + _paeth(a, prev[i], c)) & 0xFF
    else:
        return None
    return recon


def _decode_png(path: Path) -> tuple[int, int, int, bytearray] | None:
    """순수 파이썬 PNG 디코더(8-bit, colortype 0/2/4/6, non-interlace 한정).

    반환: (width, height, bytes_per_pixel, raw_pixels) 또는 디코드 불가 시 None.
    빈/단색 렌더 감지(독립 픽셀 검사)를 위한 최소 구현 — 외부 패키지 없이 stdlib(zlib)만.
    """
    try:
        data = Path(path).read_bytes()
    except OSError:
        return None
    if data[:8] != _PNG_SIG:
        return None
    pos = 8
    width = height = None
    bit_depth = color_type = interlace = None
    idat = bytearray()
    n = len(data)
    while pos + 8 <= n:
        length = int.from_bytes(data[pos:pos + 4], "big")
        ctype = data[pos + 4:pos + 8]
        cdata = data[pos + 8:pos + 8 + length]
        pos += 12 + length  # length(4) + type(4) + data + crc(4)
        if ctype == b"IHDR":
            if len(cdata) < 13:
                return None
            width = int.from_bytes(cdata[0:4], "big")
            height = int.from_bytes(cdata[4:8], "big")
            bit_depth = cdata[8]
            color_type = cdata[9]
            interlace = cdata[12]
        elif ctype == b"IDAT":
            idat += cdata
        elif ctype == b"IEND":
            break
    if width is None or bit_depth != 8 or interlace != 0:
        return None
    channels = {0: 1, 2: 3, 4: 2, 6: 4}.get(color_type)
    if channels is None or width <= 0 or height <= 0:
        return None
    try:
        raw = zlib.decompress(bytes(idat))
    except zlib.error:
        return None
    stride = width * channels
    if len(raw) < (stride + 1) * height:
        return None
    out = bytearray(stride * height)
    prev = bytearray(stride)
    ri = 0
    for y in range(height):
        ftype = raw[ri]
        ri += 1
        line = raw[ri:ri + stride]
        ri += stride
        recon = _unfilter_line(ftype, line, prev, channels, stride)
        if recon is None:
            return None
        out[y * stride:(y + 1) * stride] = recon
        prev = recon
    return (width, height, channels, out)


def _png_distinct_sample(path: Path, limit: int = 8) -> int | None:
    """PNG 를 디코드해 격자 샘플의 서로 다른 색 수를 센다(빈/단색 렌더 감지).

    작은 스프라이트도 놓치지 않도록 촘촘히(최대 128x128 격자) 보되, 충분히
    다채로우면 조기 종료한다. 디코드 불가(예상 밖 포맷)면 None → 엔진 마커로 폴백.
    """
    decoded = _decode_png(path)
    if decoded is None:
        return None
    w, h, bpp, raw = decoded
    step_x = max(1, w // 128)
    step_y = max(1, h // 128)
    row_bytes = w * bpp
    seen: set[bytes] = set()
    for y in range(0, h, step_y):
        base = y * row_bytes
        for x in range(0, w, step_x):
            off = base + x * bpp
            seen.add(bytes(raw[off:off + bpp]))
            if len(seen) > limit:
                return len(seen)
    return len(seen)


def run_screenshot(
    godot: str,
    project_dir: Path,
    output_path,
    scene: str | None = None,
    frames: int = 12,
    timeout: int = 120,
    plat: str | None = None,
) -> Stage:
    """옵트인 시각 스테이지: 메인 씬을 렌더해 PNG 저장 + 비어있지 않은 렌더인지 검증."""
    st = Stage("스크린샷 (시각 렌더)")
    plat = plat if plat is not None else sys.platform

    out = Path(output_path)
    if not out.is_absolute():
        out = project_dir / out
    out = out.resolve()

    if plat.startswith("linux") and shutil.which("xvfb-run") is None:
        st.detail = (
            "Linux 에서 스크린샷은 가상 디스플레이가 필요합니다: 'xvfb-run' 을 찾을 수 없음. "
            "CI/서버는 xvfb + Mesa GL(apt: xvfb libgl1-mesa-dri) 설치가 필요합니다."
        )
        return st

    # 오래된 산출물 제거(이전 PNG 를 성공으로 오판하지 않도록)
    try:
        if out.exists():
            out.unlink()
    except OSError:
        pass
    out.parent.mkdir(parents=True, exist_ok=True)

    cmd = build_screenshot_cmd(godot, project_dir, out, scene, frames, plat)
    try:
        rc, stdout, stderr, timed_out = _run_process_group(cmd, timeout)
    except FileNotFoundError:
        st.detail = f"실행 파일을 찾을 수 없음: {cmd[0]!r}"
        return st

    saved = _find_marker(stdout, "SHOT_SAVED:")
    err_marker = _find_marker(stdout, "SHOT_ERROR:")
    nonblank_marker = _find_marker(stdout, "SHOT_NONBLANK:")
    size_marker = _find_marker(stdout, "SHOT_SIZE:")

    if timed_out:
        st.detail = (
            f"타임아웃 ({timeout}s) — 창이 뜨지 않거나 렌더가 진행되지 않았습니다. "
            "headless 환경이거나 GL 컨텍스트 생성에 실패했을 수 있습니다.\n"
            + _tail(stdout, stderr)
        )
        return st
    if err_marker:
        st.detail = f"스크립트 오류: {err_marker}\n" + _tail(stdout, stderr)
        return st
    if not saved:
        st.detail = (
            f"SHOT_SAVED 마커가 없어 저장 실패로 판단합니다 (exit={rc}).\n"
            + _tail(stdout, stderr)
        )
        return st

    if not out.exists():
        st.detail = f"마커는 저장 성공을 알리나 파일이 없습니다: {out}"
        return st
    size = out.stat().st_size
    if size < 100:
        st.detail = f"PNG 크기가 비정상적으로 작습니다 ({size} bytes): {out}"
        return st

    dims = _read_png_dimensions(out)
    if dims is None:
        st.detail = f"유효한 PNG 가 아닙니다(IHDR 파싱 실패): {out}"
        return st
    w, h = dims
    if w <= 0 or h <= 0:
        st.detail = f"PNG 해상도가 비정상입니다: {w}x{h}"
        return st

    # 독립 비-단색 검사(파이썬 자체 디코드). 디코드 불가 시 엔진 마커로 폴백.
    distinct = _png_distinct_sample(out)
    if distinct is not None:
        if distinct <= 1:
            st.detail = (
                f"빈/단색 렌더 감지 (독립 픽셀 검사: 서로 다른 색 {distinct}개) — "
                f"까만 화면/빈 렌더로 의심됩니다: {out}"
            )
            return st
        blank_note = f"독립 픽셀 검사 {distinct}색(비-단색)"
    else:
        if nonblank_marker is not None and nonblank_marker.lower() != "true":
            st.detail = f"엔진 판정 단색(SHOT_NONBLANK=false) — 빈 렌더로 의심됩니다: {out}"
            return st
        blank_note = "엔진 마커 기준 비-단색(파이썬 디코드 폴백)"

    st.ok = True
    st.detail = (
        f"렌더 성공: {size_marker or f'{w}x{h}'} · {blank_note} · {size} bytes\n"
        f"저장: {out}"
    )
    return st


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="play_test.py",
        description="Godot 임포트 + 스모크 테스트 + 매니페스트 정합성 러너",
    )
    parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"),
                        help="godot 실행 파일 (기본: $GODOT_BIN 또는 'godot')")
    parser.add_argument("--project", default=str(root), help="Godot 프로젝트 디렉토리")
    parser.add_argument("--manifest", default=manifest_mod.default_manifest())
    parser.add_argument("--schema", default=manifest_mod.default_schema())
    parser.add_argument("--skip-godot", action="store_true",
                        help="Godot 스테이지(1,2)를 건너뛰고 매니페스트 정합성만 검사")
    parser.add_argument("--screenshot", "--visual", action="store_true", dest="screenshot",
                        help="(옵트인) 메인 씬을 실제 렌더해 PNG 스크린샷을 저장·검증하는 시각 "
                             "스테이지를 추가한다. headless 불가 — macOS 는 창이 잠깐 뜨고, "
                             "Linux 는 xvfb 가상 디스플레이가 필요하다.")
    parser.add_argument("--shot-output", default=DEFAULT_SHOT_OUTPUT,
                        help=f"스크린샷 PNG 저장 경로 (기본: {DEFAULT_SHOT_OUTPUT}, 저장소 상대. "
                             "pipeline/artifacts/ 는 .gitignore 처리됨)")
    parser.add_argument("--shot-scene", default=None,
                        help="렌더할 씬 (기본: project.godot 의 main_scene)")
    parser.add_argument("--shot-frames", type=int, default=12,
                        help="캡처 전 대기할 렌더 프레임 수 (기본: 12)")
    parser.add_argument("--shot-timeout", type=int, default=120,
                        help="스크린샷 스테이지 타임아웃 초 (기본: 120)")
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    print("=" * 64)
    print("play test — 임포트 · 스모크 · 매니페스트 정합성")
    print(f"프로젝트: {project_dir}")
    print("=" * 64)

    stages: list[Stage] = []
    if args.skip_godot:
        print("[i] --skip-godot: Godot 스테이지 생략")
        if args.screenshot:
            print("[i] --screenshot 은 Godot 렌더가 필요하므로 --skip-godot 과 함께 무시됩니다.")
    else:
        if shutil.which(args.godot) is None and not Path(args.godot).exists():
            print(f"오류: godot 실행 파일을 찾을 수 없습니다 ({args.godot!r}). "
                  f"--godot 로 경로를 지정하거나 --skip-godot 을 사용하세요.", file=sys.stderr)
            return 2
        stages.append(run_godot_import(args.godot, project_dir))
        stages.append(run_smoke(args.godot, project_dir))
        if args.screenshot:
            print("[i] --screenshot: 실제 렌더 스테이지 실행 "
                  "(macOS 는 창이 잠깐 뜸 / Linux 는 xvfb 필요)")
            stages.append(run_screenshot(
                args.godot, project_dir, args.shot_output,
                scene=args.shot_scene, frames=args.shot_frames,
                timeout=args.shot_timeout,
            ))

    stages.append(run_manifest_integrity(Path(args.manifest), Path(args.schema), project_dir))

    print()
    failures = 0
    for st in stages:
        badge = "PASS" if st.ok else "FAIL"
        if not st.ok:
            failures += 1
        print(f"[{badge}] {st.name}")
        for line in st.detail.splitlines():
            print(f"        {line}")

    print("-" * 64)
    if failures:
        print(f"결과: 실패 {failures}건 / {len(stages)} 스테이지")
        return 1
    print(f"결과: 전체 통과 ({len(stages)} 스테이지)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
