#!/usr/bin/env python3
"""verify — CLAUDE.md 「검증 게이트」 5항목 통합 러너.

CLAUDE.md 의 검증 게이트를 한 번에 실행하고 게이트별 PASS/FAIL/SKIP 을 종합한다.

  게이트 #1  Godot headless 임포트 성공
  게이트 #2  스모크 테스트 통과
  게이트 #3  네이밍/디렉토리 규칙 준수         ← 이 러너의 신규 핵심
  게이트 #4  매니페스트 ↔ 실제 파일 정합성
  게이트 #5  lore 정본과의 모순 없음 (기계 검사; 의미 검사는 Claude 몫)

게이트 #1/#2/#4 는 play_test.py 의 스테이지를, 게이트 #5 는 lore_check.py 를
재사용한다(로직 단일화). 게이트 #3 만 이 파일이 새로 구현한다.

게이트 #3(네이밍/디렉토리) 검사 규칙 (docs/conventions.md 근거):
  snake_case_filename   src/·scenes/·assets/ 하위 게임 파일명이 snake_case 인가
                        (PLACEHOLDER_ 접두사는 허용, 이후는 snake_case)
  scene_root_mismatch   씬 파일명이 루트 노드 PascalCase 의 snake_case 와 일치하는가
  undeclared_placeholder PLACEHOLDER_ 파일이 매니페스트에 등록돼 있는가
  audio_ext             assets/audio/se·bgm 는 .ogg 만 허용
  sprite_path           assets/art/sprites/ 는 <카테고리>/<파일> 2단 경로
  ui_path               assets/art/ui/ 는 <화면>/<요소> 2단 경로
  manifest_id_format    매니페스트 entry id 가 스키마 id 패턴과 일치 (naming 관점)

  (.uid/.import/.gitkeep/.gitignore 등 Godot·VCS 부산물, __pycache__/.godot 등은 제외)

--full: 위 게이트에 더해 pipeline/tests/run_*.py 러너 전부를 자동 발견해 실행한다.
        무한 재귀 방지: 자식 러너 실행 시 환경변수 ARTIFICER_IN_VERIFY_FULL=1 을 심고,
        이미 그 안에서 다시 --full 이 호출되면 러너 실행을 생략(게이트만)한다.

종료 코드: 0 = 전체 통과(SKIP 포함), 1 = 게이트/러너 위반, 2 = 실행 오류.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import os
import re
import shutil
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

# 같은 디렉토리의 보조 모듈 재사용 (검증 로직 단일화)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402
import play_test as play_test_mod  # noqa: E402

# --full 재귀 가드 환경변수
IN_FULL_ENV = "ARTIFICER_IN_VERIFY_FULL"


def _repo_root() -> Path:
    # pipeline/scripts/verify.py -> repo_root
    return Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 게이트 결과 표현
# ---------------------------------------------------------------------------
@dataclass
class Gate:
    num: int
    name: str
    status: str = "SKIP"          # PASS | FAIL | SKIP
    lines: list[str] = field(default_factory=list)


@dataclass
class Violation:
    """게이트 #3 위반 하나. 리포트는 `파일:항목` 으로 출력한다."""
    file: str
    item: str

    def render(self) -> str:
        return f"{self.file}:{self.item}"


# ---------------------------------------------------------------------------
# 게이트 #3 — 네이밍/디렉토리 규칙 (신규 핵심)
# ---------------------------------------------------------------------------
SCAN_ROOTS = ("src", "scenes", "assets")

# 스캔에서 완전히 제외할 이름/디렉토리 (Godot·VCS·빌드 부산물)
_SKIP_DIRS = {".git", ".godot", "__pycache__", "node_modules", "export", ".import"}
_SKIP_NAMES = {".gitkeep", ".gitignore", ".DS_Store"}
# Godot 부산물 확장자 — 네이밍 검사 대상 아님
_BYPRODUCT_SUFFIXES = {".import", ".uid"}
# 문서/설정 파일 — snake_case 강제 대상 아님(README 등 관례 허용)
_DOC_SUFFIXES = {".md", ".json", ".txt", ".cfg", ".yml", ".yaml"}

PLACEHOLDER_PREFIX = "PLACEHOLDER_"

_SNAKE_RE = re.compile(r"^[a-z0-9]+(_[a-z0-9]+)*$")


def _is_snake_case(stem: str) -> bool:
    """PLACEHOLDER_ 접두사는 벗겨낸 뒤 나머지가 snake_case 인지 판정."""
    core = stem[len(PLACEHOLDER_PREFIX):] if stem.startswith(PLACEHOLDER_PREFIX) else stem
    return bool(_SNAKE_RE.match(core))


def _iter_files(root: Path):
    """스캔 대상 파일을 (절대경로) 로 순회. 부산물/스킵 디렉토리 제외."""
    for dirpath, dirnames, filenames in os.walk(root):
        # 스킵 디렉토리 가지치기 (in-place)
        dirnames[:] = [d for d in dirnames if d not in _SKIP_DIRS]
        for fn in filenames:
            if fn in _SKIP_NAMES:
                continue
            yield Path(dirpath) / fn


def pascal_to_snake(name: str) -> str:
    """PascalCase → snake_case. 예: Player→player, MainMenu→main_menu."""
    s = re.sub(r"(?<!^)(?=[A-Z])", "_", name)
    return s.lower()


def _scene_root_node(text: str) -> str | None:
    """.tscn 텍스트에서 루트 노드 이름을 추출. 루트 = parent 속성이 없는 첫 node."""
    for line in text.splitlines():
        if not line.startswith("[node "):
            continue
        if "parent=" in line:
            continue  # 자식 노드
        m = re.search(r'name="([^"]+)"', line)
        if m:
            return m.group(1)
    return None


def _manifest_declared_files(project_dir: Path, manifest_path: Path) -> set[Path] | None:
    """매니페스트에 등록된 file 경로들을 절대경로 집합으로. 로드 실패 시 None."""
    try:
        data = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError):
        return None
    declared: set[Path] = set()
    for entry in data.get("entries", []):
        ref = entry.get("file")
        if ref:
            declared.add(play_test_mod._resolve_res_path(ref, project_dir).resolve())
    return declared


def _schema_id_pattern(schema_path: Path) -> re.Pattern[str] | None:
    """스키마에서 entry id 패턴을 읽어온다(하드코딩 회피). 실패 시 None."""
    try:
        schema = manifest_mod.load_schema(str(schema_path))
    except (FileNotFoundError, ValueError):
        return None
    try:
        pat = schema["definitions"]["entry"]["properties"]["id"]["pattern"]
    except (KeyError, TypeError):
        return None
    return re.compile(pat)


def check_naming_rules(
    project_dir: Path, manifest_path: Path, schema_path: Path
) -> list[Violation]:
    """게이트 #3: 파일시스템 네이밍/디렉토리 규칙 + 매니페스트 id 형식 검사."""
    violations: list[Violation] = []

    def rel(p: Path) -> str:
        # as_posix(): 위반 리포트 경로는 OS 무관 슬래시 고정(러너·CI 대조 일관성)
        try:
            return p.resolve().relative_to(project_dir.resolve()).as_posix()
        except ValueError:
            return p.as_posix()

    declared = _manifest_declared_files(project_dir, manifest_path)

    for root_name in SCAN_ROOTS:
        root = project_dir / root_name
        if not root.exists():
            continue
        for f in _iter_files(root):
            suffix = f.suffix.lower()
            if suffix in _BYPRODUCT_SUFFIXES:
                continue

            relpath = rel(f)

            # --- snake_case 파일명 (문서/설정 확장자는 제외) ---
            if suffix not in _DOC_SUFFIXES:
                if not _is_snake_case(f.stem):
                    violations.append(Violation(
                        relpath,
                        f"파일명이 snake_case 규칙 위반 (stem='{f.stem}')",
                    ))

            # --- PLACEHOLDER_ 파일은 매니페스트 등록 필수 ---
            if f.name.startswith(PLACEHOLDER_PREFIX) and declared is not None:
                if f.resolve() not in declared:
                    violations.append(Violation(
                        relpath,
                        "PLACEHOLDER_ 파일이 매니페스트에 등록되지 않음 "
                        "(manifest.py add 로 등록 필요)",
                    ))

            # --- 씬 파일명 = 루트 노드 snake_case ---
            if suffix == ".tscn":
                try:
                    text = f.read_text(encoding="utf-8")
                except OSError:
                    text = ""
                root_node = _scene_root_node(text)
                if root_node is not None:
                    expected = pascal_to_snake(root_node)
                    if expected != f.stem:
                        violations.append(Violation(
                            relpath,
                            f"씬 파일명이 루트 노드 '{root_node}' 와 불일치 "
                            f"(기대 '{expected}.tscn')",
                        ))

    # --- 오디오 확장자: assets/audio/se·bgm 는 .ogg 만 ---
    for sub in ("se", "bgm"):
        adir = project_dir / "assets" / "audio" / sub
        if not adir.exists():
            continue
        for f in _iter_files(adir):
            if f.suffix.lower() in _BYPRODUCT_SUFFIXES:
                continue
            if f.suffix.lower() != ".ogg":
                violations.append(Violation(
                    rel(f),
                    f"assets/audio/{sub} 는 .ogg 만 허용 (실제 '{f.suffix}')",
                ))

    # --- 스프라이트/UI 경로 규약 (이미지 파일 대상) ---
    sprites_dir = project_dir / "assets" / "art" / "sprites"
    if sprites_dir.exists():
        for f in _iter_files(sprites_dir):
            if f.suffix.lower() != ".png":
                continue
            depth = len(f.resolve().relative_to(sprites_dir.resolve()).parts)
            if depth < 2:  # <카테고리>/<파일> 이어야 함
                violations.append(Violation(
                    rel(f),
                    "스프라이트는 assets/art/sprites/<카테고리>/<파일> 2단 경로 필요",
                ))
    ui_dir = project_dir / "assets" / "art" / "ui"
    if ui_dir.exists():
        for f in _iter_files(ui_dir):
            if f.suffix.lower() != ".png":
                continue
            depth = len(f.resolve().relative_to(ui_dir.resolve()).parts)
            if depth < 2:  # <화면>/<요소> 이어야 함
                violations.append(Violation(
                    rel(f),
                    "UI 아트는 assets/art/ui/<화면>/<요소> 2단 경로 필요",
                ))

    # --- 매니페스트 id 형식 (스키마 패턴 재사용, naming 관점) ---
    id_pat = _schema_id_pattern(schema_path)
    if id_pat is not None:
        try:
            data = manifest_mod.load_manifest(str(manifest_path))
        except (FileNotFoundError, ValueError):
            data = None
        if data is not None:
            for i, entry in enumerate(data.get("entries", [])):
                eid = entry.get("id")
                if isinstance(eid, str) and id_pat.match(eid) is None:
                    violations.append(Violation(
                        rel(manifest_path),
                        f"entries[{i}].id '{eid}' 가 id 형식(<track>:<...>) 위반",
                    ))

    return violations


def gate_naming(project_dir: Path, manifest_path: Path, schema_path: Path) -> Gate:
    g = Gate(3, "네이밍/디렉토리 규칙")
    violations = check_naming_rules(project_dir, manifest_path, schema_path)
    if violations:
        g.status = "FAIL"
        g.lines = [v.render() for v in violations]
    else:
        g.status = "PASS"
        g.lines = ["네이밍/디렉토리 규칙 위반 없음"]
    return g


# ---------------------------------------------------------------------------
# 게이트 #5 — lore 기계 검사 (canon 비어 있으면 SKIP)
# ---------------------------------------------------------------------------
def _canon_doc_count(canon_dir: Path) -> int:
    if not canon_dir.exists():
        return 0
    return len([p for p in canon_dir.glob("*.md")])


def gate_lore(project_dir: Path) -> Gate:
    g = Gate(5, "lore 정본 모순 (기계 검사)")
    canon_dir = project_dir / "lore" / "canon"
    if _canon_doc_count(canon_dir) == 0:
        g.status = "SKIP"
        g.lines = [
            "canon 문서가 없어 기계 검사를 건너뜁니다 (lore init 미실행).",
            "참고: 의미적 모순 검사는 스크립트가 아닌 Claude(/lore-check)의 몫입니다.",
        ]
        return g

    lore_check = Path(__file__).resolve().parent / "lore_check.py"
    proc = subprocess.run(
        [sys.executable, str(lore_check), "--canon", str(canon_dir)],
        capture_output=True, text=True,
    )
    # lore_check: 0 = error/warning 없음, 1 = error/warning 검출, 2 = 실행 오류
    if proc.returncode == 0:
        g.status = "PASS"
    elif proc.returncode == 1:
        g.status = "FAIL"
    else:
        g.status = "FAIL"
    tail = [ln for ln in proc.stdout.splitlines()
            if ln.startswith(("[", "요약")) or "검출된 항목" in ln]
    g.lines = tail[:20] if tail else [proc.stdout.strip() or proc.stderr.strip()]
    g.lines.append(
        "참고: 의미적 모순(설정 충돌) 검사는 Claude(/lore-check) 판단 단계의 몫입니다."
    )
    return g


# ---------------------------------------------------------------------------
# 게이트 #1/#2/#4 — play_test 스테이지 재사용
# ---------------------------------------------------------------------------
def _stage_to_gate(num: int, name: str, stage) -> Gate:
    g = Gate(num, name)
    g.status = "PASS" if stage.ok else "FAIL"
    g.lines = stage.detail.splitlines() or [""]
    return g


# ---------------------------------------------------------------------------
# --full: 러너 자동 발견/실행
# ---------------------------------------------------------------------------
# 러너 실패 원인으로 볼 만한 줄. "error 0" 같은 요약 카운트는 잡지 않도록 좁게 둔다.
_FAILURE_LINE = re.compile(
    r"\[FAIL\]|Traceback \(most recent call last\)|^\s*\w*(Error|Exception):|^\s*결과: 실패"
)


def _failure_excerpt(stdout: str, stderr: str, *, max_hits: int = 15,
                     tail_n: int = 8) -> list[str]:
    """실패한 러너의 출력에서 '왜 실패했는지'가 보이는 줄을 골라 준다.

    꼬리만 찍으면 안 되는 이유: run_se_pipeline 처럼 마지막 섹션이 회귀 검사(전부
    PASS)로 끝나는 러너는 tail 에 정작 [FAIL] 줄이 안 들어와, CI 로그만 보고는
    원인을 알 수 없다(실제로 #91 에서 그랬다). 원인 줄을 먼저 뽑고 꼬리를 덧붙인다.
    """
    lines = stdout.splitlines()
    if not lines:
        return [ln for ln in (stderr or "").strip().splitlines()[-tail_n:]] or ["(출력 없음)"]

    hits = [(i, ln) for i, ln in enumerate(lines) if _FAILURE_LINE.search(ln)]
    out: list[str] = []
    if hits:
        shown = hits[:max_hits]
        out.append(f"-- 실패 지점 {len(hits)}건" + (f" (앞 {max_hits}건만 표시)"
                                                    if len(hits) > max_hits else "") + " --")
        out += [f"L{i + 1}: {ln.strip()}" for i, ln in shown]
    out.append(f"-- 출력 끝 {tail_n}줄 --")
    out += lines[-tail_n:]
    if stderr and stderr.strip():
        err = stderr.strip().splitlines()
        out.append("-- stderr --")
        out += err[-tail_n:]
    return out


def discover_runners(tests_dir: Path, exclude: set[str] | None = None) -> list[Path]:
    """pipeline/tests/run_*.py 러너를 정렬해 반환. exclude 의 파일명은 제외."""
    exclude = exclude or set()
    return sorted(
        p for p in tests_dir.glob("run_*.py") if p.name not in exclude
    )


# ---------------------------------------------------------------------------
# 게이트 실행 (importable)
# ---------------------------------------------------------------------------
def run_gates(
    project_dir: Path,
    manifest_path: Path,
    schema_path: Path,
    godot: str,
    skip_godot: bool,
) -> tuple[list[Gate], int]:
    """게이트 1~5 를 실행. (gates, exec_error_count) 반환.
    exec_error_count>0 이면 러너 오류(종료 2)로 취급."""
    gates: list[Gate] = []
    exec_errors = 0

    # 게이트 #1/#2 — Godot 임포트 + 스모크
    if skip_godot:
        g1 = Gate(1, "Godot headless 임포트")
        g1.status = "SKIP"
        g1.lines = ["--skip-godot: Godot 스테이지 생략"]
        g2 = Gate(2, "스모크 테스트")
        g2.status = "SKIP"
        g2.lines = ["--skip-godot: Godot 스테이지 생략"]
        gates.extend([g1, g2])
    elif shutil.which(godot) is None and not Path(godot).exists():
        g1 = Gate(1, "Godot headless 임포트")
        g1.status = "FAIL"
        g1.lines = [f"godot 실행 파일을 찾을 수 없음: {godot!r} "
                    "(--godot 로 지정하거나 --skip-godot 사용)"]
        gates.append(g1)
        exec_errors += 1
    else:
        s1 = play_test_mod.run_godot_import(godot, project_dir)
        gates.append(_stage_to_gate(1, "Godot headless 임포트", s1))
        s2 = play_test_mod.run_smoke(godot, project_dir)
        gates.append(_stage_to_gate(2, "스모크 테스트", s2))

    # 게이트 #3 — 네이밍/디렉토리
    gates.append(gate_naming(project_dir, manifest_path, schema_path))

    # 게이트 #4 — 매니페스트 정합성
    s4 = play_test_mod.run_manifest_integrity(manifest_path, schema_path, project_dir)
    gates.append(_stage_to_gate(4, "매니페스트 정합성 (스키마 + 파일)", s4))

    # 게이트 #5 — lore 기계 검사
    gates.append(gate_lore(project_dir))

    return gates, exec_errors


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="verify.py",
        description="CLAUDE.md 검증 게이트 5항목 통합 러너",
    )
    parser.add_argument("--project", default=str(root), help="Godot 프로젝트 디렉토리")
    parser.add_argument("--manifest", default=None,
                        help="기본: <project>/pipeline/manifest.json")
    parser.add_argument("--schema", default=None,
                        help="기본: <project>/pipeline/schemas/asset-manifest.schema.json")
    parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
    parser.add_argument("--skip-godot", action="store_true",
                        help="Godot 스테이지(게이트 1·2) 생략")
    parser.add_argument("--full", action="store_true",
                        help="게이트에 더해 pipeline/tests/run_*.py 러너 전부 실행")
    parser.add_argument("--json", action="store_true", help="JSON 요약 출력")
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    manifest_path = (
        Path(args.manifest) if args.manifest
        else project_dir / "pipeline" / "manifest.json"
    )
    schema_path = (
        Path(args.schema) if args.schema
        else project_dir / "pipeline" / "schemas" / "asset-manifest.schema.json"
    )

    gates, exec_errors = run_gates(
        project_dir, manifest_path, schema_path, args.godot, args.skip_godot
    )

    # ---- 게이트 출력 ----
    print("=" * 64)
    print("verify — CLAUDE.md 검증 게이트 통합 검사")
    print(f"프로젝트: {project_dir}")
    print("=" * 64)
    for g in gates:
        print(f"[{g.status}] 게이트 #{g.num} {g.name}")
        for ln in g.lines:
            print(f"        {ln}")

    gate_failures = sum(1 for g in gates if g.status == "FAIL")

    # ---- --full: 러너 실행 (재귀 가드) ----
    runner_failures = 0
    runner_results: list[tuple[str, bool]] = []
    if args.full:
        nested = os.environ.get(IN_FULL_ENV) == "1"
        tests_dir = project_dir / "pipeline" / "tests"
        print("-" * 64)
        if nested:
            print("[i] --full (중첩): 이미 verify --full 안에서 호출됨 → "
                  "러너 재실행 생략 (무한 재귀 방지). 게이트만 검사합니다.")
        else:
            runners = discover_runners(tests_dir)
            print(f"[i] --full: 테스트 러너 {len(runners)}종 실행")
            child_env = dict(os.environ)
            child_env[IN_FULL_ENV] = "1"
            for rp in runners:
                proc = subprocess.run(
                    [sys.executable, str(rp)],
                    capture_output=True, text=True, env=child_env,
                )
                ok = proc.returncode == 0
                runner_results.append((rp.name, ok))
                if not ok:
                    runner_failures += 1
                badge = "PASS" if ok else "FAIL"
                print(f"  [{badge}] {rp.name}")
                if not ok:
                    for ln in _failure_excerpt(proc.stdout, proc.stderr):
                        print(f"          {ln}")

    # ---- 종합 판정 ----
    print("-" * 64)
    if exec_errors:
        print(f"결과: 실행 오류 {exec_errors}건 (종료 2)")
        rc = 2
    elif gate_failures or runner_failures:
        print(f"결과: 게이트 실패 {gate_failures}건"
              + (f" · 러너 실패 {runner_failures}건" if args.full else ""))
        rc = 1
    else:
        skips = sum(1 for g in gates if g.status == "SKIP")
        print(f"결과: 전체 통과 (게이트 {len(gates)}개 중 SKIP {skips}개)"
              + (f" · 러너 {len(runner_results)}종 통과" if args.full else ""))
        rc = 0

    if args.json:
        import json
        payload = {
            "project": str(project_dir),
            "gates": [
                {"num": g.num, "name": g.name, "status": g.status, "lines": g.lines}
                for g in gates
            ],
            "full": args.full,
            "runners": [{"name": n, "ok": ok} for n, ok in runner_results],
            "exit_code": rc,
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))

    return rc


if __name__ == "__main__":
    raise SystemExit(main())
