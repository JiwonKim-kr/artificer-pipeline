#!/usr/bin/env python3
"""play test — Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성 러너.

CLAUDE.md 검증 게이트를 로컬에서 부분 실행한다(‘play test’ 범위):
  Stage 1  Godot headless 임포트 성공          (게이트 #1)
  Stage 2  스모크 테스트 통과                    (게이트 #2)
  Stage 3  매니페스트 ↔ 스키마 + 실제 파일 정합성  (게이트 #4)

(네이밍/디렉토리 규칙 게이트 #3, lore 정본 모순 게이트 #5 는 상위 `verify`
명령의 몫이며 이 러너 범위 밖이다.)

단계적 설계: 프로젝트에 아직 씬이 없어도 각 스테이지가 의미 있게 동작한다.
Stage 2 스모크 테스트는 main_scene 미설정 시 부트/임포트만 확인하고 통과한다.

종료 코드: 0 = 전체 통과, 1 = 한 스테이지 이상 실패, 2 = 러너 오류(godot 없음 등).
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

# 같은 디렉토리의 manifest 모듈 재사용 (검증 로직 단일화)
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


SMOKE_SCRIPT = "res://pipeline/tests/smoke_test.gd"


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
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    print("=" * 64)
    print("play test — 임포트 · 스모크 · 매니페스트 정합성")
    print(f"프로젝트: {project_dir}")
    print("=" * 64)

    stages: list[Stage] = []
    if args.skip_godot:
        print("[i] --skip-godot: Godot 스테이지 생략")
    else:
        if shutil.which(args.godot) is None and not Path(args.godot).exists():
            print(f"오류: godot 실행 파일을 찾을 수 없습니다 ({args.godot!r}). "
                  f"--godot 로 경로를 지정하거나 --skip-godot 을 사용하세요.", file=sys.stderr)
            return 2
        stages.append(run_godot_import(args.godot, project_dir))
        stages.append(run_smoke(args.godot, project_dir))

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
