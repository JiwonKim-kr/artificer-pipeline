#!/usr/bin/env python3
"""play 트랙 파이프라인 테스트 (manifest 검증 · 쓰기 · play_test 러너).

Phase 1 의 run_lore_roundtrip.py 와 같은 스타일(단일 파일·번호 섹션·check 헬퍼).

  [1] manifest 스키마 검증  : valid fixture 통과 / 각 invalid fixture 가
                              의도한 error code 로 검출되는지 확인.
  [2] manifest 쓰기 창구    : 임시 사본에 add/update-status/list 를 실행.
                              중복 ID·잘못된 ID 는 검증 실패로 '쓰이지 않음' 확인.
  [3] play_test 정합성 로직 : run_manifest_integrity 가 파일 누락을 잡고,
                              파일이 존재하면 통과하는지 확인.
  [4] play_test 엔드투엔드   : play_test.py 를 실제 프로젝트에 실행 →
                              임포트 + 스모크 + 매니페스트 정합성 전체 통과.
  [5] 스크린샷 스테이지      : 순수 파이썬 헬퍼(PNG 디코드/빈 렌더 감지, 플랫폼별
                              커맨드 구성) 단위 검증 + (옵트인) 실제 렌더 e2e.

CLAUDE.md 규칙: 실데이터(pipeline/manifest.json)는 절대 수정하지 않는다.
쓰기 검사는 전부 임시 사본/임시 디렉토리 대상.

[5]의 실제 렌더 e2e 는 무겁고(GUI/xvfb) 창이 뜨므로 기본은 SKIP 이며
환경변수 ARTIFICER_RUN_SCREENSHOT_RENDER=1 일 때만 실행한다. 이렇게 해서
`verify.py --full`(CI 기본 게이트)이 이 러너를 자동 실행해도 느려지지 않는다.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
SCRIPTS = TESTS_DIR.parent / "scripts"
FX = TESTS_DIR / "fixtures" / "manifest"
SCHEMA = REPO_ROOT / "pipeline" / "schemas" / "asset-manifest.schema.json"

# play_test 모듈을 직접 import (정합성 로직 단위 검증용)
sys.path.insert(0, str(SCRIPTS))
import play_test as play_test_mod  # noqa: E402
import manifest as manifest_mod  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
_failures = 0


def check(label: str, condition: bool) -> None:
    global _failures
    if not condition:
        _failures += 1
    print(f"  [{PASS if condition else FAIL}] {label}")


def _manifest(manifest_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable, str(SCRIPTS / "manifest.py"),
        "--manifest", str(manifest_path), "--schema", str(SCHEMA), *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _validate_codes(manifest_path: Path) -> tuple[int, list[str]]:
    r = _manifest(manifest_path, "validate", "--json")
    payload = json.loads(r.stdout)
    return r.returncode, [e["code"] for e in payload["errors"]]


def section_schema_validation() -> None:
    print("\n[1] manifest 스키마 검증 (valid / invalid fixtures)")
    rc, codes = _validate_codes(FX / "valid_manifest.json")
    check("valid_manifest 통과 (exit 0)", rc == 0 and not codes)

    expected = {
        "invalid_version": "const",
        "invalid_bad_id": "pattern",
        "invalid_missing_field": "required",
        "invalid_bad_enum": "enum",
        "invalid_id_track_mismatch": "id_track_mismatch",
        "invalid_duplicate_id": "duplicate_id",
    }
    for name, code in expected.items():
        rc, codes = _validate_codes(FX / f"{name}.json")
        check(f"{name} → exit 1", rc == 1)
        check(f"{name} → '{code}' 검출", code in codes)


def section_write_gateway() -> None:
    print("\n[2] manifest 쓰기 창구 (add / update-status / list, 임시 사본)")
    with tempfile.TemporaryDirectory() as td:
        mpath = Path(td) / "manifest.json"
        shutil.copy(FX / "valid_manifest.json", mpath)

        # add 성공
        r = _manifest(
            mpath, "add",
            "--id", "art:enemy/slime_idle", "--track", "art",
            "--spec", "슬라임 대기 스프라이트",
            "--requested-by", "scene_node:scenes/enemy.tscn::Slime/Sprite2D",
        )
        check("add 성공 (exit 0)", r.returncode == 0)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("add 후 entry 3개", len(entries) == 3)
        new = next((e for e in entries if e["id"] == "art:enemy/slime_idle"), None)
        check("추가 entry 존재", new is not None)
        check("추가 entry history=registered 1건",
              new is not None and new["history"][0]["action"] == "registered")

        # 중복 ID → 실패, 파일 미변경
        r = _manifest(
            mpath, "add",
            "--id", "art:enemy/slime_idle", "--track", "art",
            "--spec", "중복", "--requested-by", "scene_node:x.tscn::A",
        )
        check("중복 ID add 실패 (exit 1)", r.returncode == 1)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("중복 add 후에도 entry 3개 (쓰이지 않음)", len(entries) == 3)

        # 잘못된 ID(대문자) → 실패
        r = _manifest(
            mpath, "add",
            "--id", "art:Enemy/Boss", "--track", "art",
            "--spec", "패턴 위반", "--requested-by", "scene_node:x.tscn::A",
        )
        check("잘못된 ID add 실패 (exit 1)", r.returncode == 1)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("잘못된 add 후에도 entry 3개 (쓰이지 않음)", len(entries) == 3)

        # update-status
        r = _manifest(
            mpath, "update-status",
            "--id", "art:enemy/slime_idle", "--status", "generated",
            "--file", "assets/art/sprites/enemy/slime_idle.png",
        )
        check("update-status 성공 (exit 0)", r.returncode == 0)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        upd = next((e for e in entries if e["id"] == "art:enemy/slime_idle"), None)
        check("status=generated 반영", upd is not None and upd["status"] == "generated")
        check("history 2건으로 증가", upd is not None and len(upd["history"]) == 2)
        check("file 경로 반영", upd is not None and upd["file"].endswith("slime_idle.png"))

        # list --track 필터
        arts = json.loads(_manifest(mpath, "list", "--track", "art", "--json").stdout)
        check("list --track art 필터 (2건)", len(arts) == 2)

        # 최종 사본이 여전히 유효
        rc, codes = _validate_codes(mpath)
        check("쓰기 이후 사본이 유효", rc == 0 and not codes)


def section_integrity_logic() -> None:
    print("\n[3] play_test 정합성 로직 (파일 누락 검출)")
    schema = manifest_mod.load_schema(str(SCHEMA))
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        mpath = proj / "manifest.json"
        manifest = {
            "version": 1,
            "style_guide": None,
            "entries": [
                {
                    "id": "art:player/player_idle",
                    "track": "art",
                    "status": "placeholder",
                    "spec": "정합성 테스트",
                    "requested_by": [{"kind": "scene_node", "path": "scenes/player.tscn::Player"}],
                    "file": "assets/art/PLACEHOLDER_player_idle.png",
                }
            ],
        }
        mpath.write_text(json.dumps(manifest), encoding="utf-8")

        # 파일 미존재 → 정합성 실패
        st = play_test_mod.run_manifest_integrity(mpath, SCHEMA, proj)
        check("참조 파일 없으면 정합성 FAIL", st.ok is False)
        check("detail 에 missing_file 표시", "missing_file" in st.detail)

        # 파일 생성 후 → 정합성 통과
        fpath = proj / "assets" / "art" / "PLACEHOLDER_player_idle.png"
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(b"\x89PNG placeholder")
        st = play_test_mod.run_manifest_integrity(mpath, SCHEMA, proj)
        check("참조 파일 존재하면 정합성 PASS", st.ok is True)


def section_play_test_e2e() -> None:
    print("\n[4] play_test.py 엔드투엔드 (실제 프로젝트: 임포트 + 스모크 + 정합성)")
    godot = os.environ.get("GODOT_BIN", "godot")
    have_godot = shutil.which(godot) is not None or Path(godot).exists()
    if not have_godot:
        print("  [SKIP] godot 실행 파일을 찾을 수 없어 Godot 스테이지를 건너뜁니다.")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "play_test.py"), "--skip-godot"],
            capture_output=True, text=True,
        )
        check("play_test --skip-godot 통과 (exit 0)", r.returncode == 0)
        return
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "play_test.py")],
        capture_output=True, text=True,
    )
    check("play_test.py 전체 통과 (exit 0)", r.returncode == 0)
    check("출력에 '전체 통과'", "전체 통과" in r.stdout)
    check("임포트 스테이지 PASS", "[PASS] Godot headless 임포트" in r.stdout)
    check("스모크 스테이지 PASS", "[PASS] 스모크 테스트" in r.stdout)


def _write_png(path: Path, width: int, height: int, pixels: list[tuple[int, int, int, int]]) -> None:
    """8-bit RGBA PNG 를 filter=None(0) 스캔라인으로 인코딩(테스트 픽스처용, stdlib 만)."""
    raw = bytearray()
    for y in range(height):
        raw.append(0)  # 필터 타입 None
        for x in range(width):
            r, g, b, a = pixels[y * width + x]
            raw += bytes((r & 0xFF, g & 0xFF, b & 0xFF, a & 0xFF))

    def chunk(ctype: bytes, cdata: bytes) -> bytes:
        return (len(cdata).to_bytes(4, "big") + ctype + cdata
                + zlib.crc32(ctype + cdata).to_bytes(4, "big"))

    ihdr = width.to_bytes(4, "big") + height.to_bytes(4, "big") + bytes((8, 6, 0, 0, 0))
    png = (b"\x89PNG\r\n\x1a\n"
           + chunk(b"IHDR", ihdr)
           + chunk(b"IDAT", zlib.compress(bytes(raw)))
           + chunk(b"IEND", b""))
    path.write_bytes(png)


def section_screenshot_helpers() -> None:
    print("\n[5] 스크린샷 스테이지 (순수 파이썬 헬퍼 단위 검증)")

    # --- 플랫폼별 커맨드 구성: headless 금지 + macOS opengl3 / Linux xvfb-run ---
    proj = REPO_ROOT
    mac_cmd = play_test_mod.build_screenshot_cmd(
        "godot", proj, Path("/tmp/shot.png"), None, 12, "darwin")
    check("macOS 커맨드에 --headless 없음", "--headless" not in mac_cmd)
    check("macOS 커맨드에 --rendering-driver opengl3", "opengl3" in mac_cmd)
    check("macOS 커맨드에 xvfb-run 없음", "xvfb-run" not in mac_cmd)
    check("macOS 커맨드에 스크린샷 스크립트", play_test_mod.SCREENSHOT_SCRIPT in mac_cmd)

    lin_cmd = play_test_mod.build_screenshot_cmd(
        "godot", proj, Path("/tmp/shot.png"), None, 12, "linux")
    check("Linux 커맨드는 xvfb-run 으로 시작", lin_cmd[0] == "xvfb-run")
    check("Linux 커맨드에 --headless 없음", "--headless" not in lin_cmd)
    check("Linux 커맨드에도 opengl3", "opengl3" in lin_cmd)

    scene_cmd = play_test_mod.build_screenshot_cmd(
        "godot", proj, Path("/tmp/shot.png"), "res://scenes/x.tscn", 5, "darwin")
    check("--scene 인자 전달됨", "res://scenes/x.tscn" in scene_cmd)
    check("--frames 인자 전달됨", "5" in scene_cmd)

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # --- IHDR 해상도 파싱 ---
        blank = tdp / "blank.png"
        _write_png(blank, 8, 4, [(30, 30, 30, 255)] * 32)
        check("_read_png_dimensions 8x4", play_test_mod._read_png_dimensions(blank) == (8, 4))

        # --- 단색 PNG → distinct == 1 (빈/까만 화면 감지) ---
        check("단색 PNG distinct==1", play_test_mod._png_distinct_sample(blank) == 1)

        # --- 색이 섞인 PNG → distinct >= 2 ---
        px = [(30, 30, 30, 255)] * 32
        px[10] = (200, 50, 50, 255)
        px[20] = (50, 200, 50, 255)
        multi = tdp / "multi.png"
        _write_png(multi, 8, 4, px)
        d = play_test_mod._png_distinct_sample(multi)
        check("다색 PNG distinct>=2", d is not None and d >= 2)

        # --- PNG 아닌 파일 → 해상도 None, distinct None(폴백 경로) ---
        notpng = tdp / "notpng.bin"
        notpng.write_bytes(b"not a png at all")
        check("비-PNG 해상도 None", play_test_mod._read_png_dimensions(notpng) is None)
        check("비-PNG distinct None(폴백)", play_test_mod._png_distinct_sample(notpng) is None)

        # --- run_screenshot: 커맨드 미실행 상황(godot 없음)에서도 명확 실패 ---
        # 존재하지 않는 실행 파일 → FileNotFoundError 를 잡아 Stage.ok=False
        st = play_test_mod.run_screenshot(
            str(tdp / "no_such_godot_bin"), proj, tdp / "x.png",
            frames=1, timeout=5, plat="darwin")
        check("godot 부재 시 스크린샷 스테이지 FAIL", st.ok is False)


def section_screenshot_render() -> None:
    print("\n[5b] 스크린샷 실제 렌더 e2e (옵트인: ARTIFICER_RUN_SCREENSHOT_RENDER=1)")
    if os.environ.get("ARTIFICER_RUN_SCREENSHOT_RENDER") != "1":
        print("  [SKIP] 실제 렌더는 무겁고 GUI/xvfb 가 필요합니다. "
              "ARTIFICER_RUN_SCREENSHOT_RENDER=1 로 활성화하세요.")
        return
    godot = os.environ.get("GODOT_BIN", "godot")
    if not (shutil.which(godot) or Path(godot).exists()):
        print("  [SKIP] godot 실행 파일을 찾을 수 없습니다.")
        return
    with tempfile.TemporaryDirectory() as td:
        out = Path(td) / "shot.png"  # 임시 경로 — 저장소를 더럽히지 않음
        st = play_test_mod.run_screenshot(godot, REPO_ROOT, out, frames=10, timeout=120)
        check("실제 렌더 스테이지 PASS", st.ok)
        check("PNG 파일 생성됨", out.exists())
        dims = play_test_mod._read_png_dimensions(out) if out.exists() else None
        check("PNG 해상도 유효(>0)", dims is not None and dims[0] > 0 and dims[1] > 0)
        d = play_test_mod._png_distinct_sample(out) if out.exists() else None
        check("렌더가 비-단색(빈 화면 아님)", d is not None and d >= 2)


def main() -> int:
    print("=" * 64)
    print("play 파이프라인 테스트: manifest 검증·쓰기 · play_test 러너")
    print("=" * 64)
    section_schema_validation()
    section_write_gateway()
    section_integrity_logic()
    section_play_test_e2e()
    section_screenshot_helpers()
    section_screenshot_render()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
