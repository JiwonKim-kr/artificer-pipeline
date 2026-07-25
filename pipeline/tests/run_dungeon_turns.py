#!/usr/bin/env python3
"""dungeon_and_turns(Spec A) 수용 기준 자동 테스트 러너.

승인 spec(docs/specs/dungeon_and_turns.md)의 수용 기준 1~6 을, Godot 헤드리스
SceneTree 스크립트(acceptance_dungeon_turns.gd)로 검증한다:

  1) 도달성  — 생성된 던전의 모든 바닥이 시작점에서 flood-fill 로 도달 가능
  2) 결정성  — 같은 시드 2회 생성 → 타일 배치 완전 동일
  3) 이동    — 방향 입력 1회 → 좌표 정확히 1칸 + 턴 카운터 +1
  4) 차단    — 벽/맵 경계 입력 → 좌표 불변 + 턴 미소비
  5) 대기    — 제자리 대기 → 좌표 불변 + 턴 카운터 +1
  6) 정렬    — 정지 시 월드 좌표 = 셀 × 타일 크기

(수용 기준 7 「메인 씬이 렌더되어 던전·승탑자가 보인다」는 play_test --screenshot
스테이지가 담당한다 — 이 러너 밖.)

플로우:
  1) godot --headless --import  (전역 클래스 캐시 보장, 멱등)
  2) godot --headless --script <acceptance_dungeon_turns.gd>
  3) 출력의 [PASS]/[FAIL] 마커와 ACCEPT_RESULT 로 판정 + 수용기준별 매핑 리포트.

종료 코드: 0 = 전체 통과, 1 = 하나 이상 실패, 2 = 러너 오류(godot 없음 등).
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import os
import shutil
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
ACCEPT_SCRIPT = "res://pipeline/tests/acceptance_dungeon_turns.gd"

# 각 수용 기준을 검증하는 체크 라벨 접두사 (리포트 매핑용)
CRITERIA = {
	"AC1 (도달성 — 모든 바닥이 시작점에서 도달)": "AC1",
	"AC2 (결정성 — 같은 시드 → 같은 배치)": "AC2",
	"AC3 (이동 1회 → 좌표 1칸 + 턴 +1)": "AC3",
	"AC4 (벽/경계 → 좌표 불변 + 턴 미소비)": "AC4",
	"AC5 (대기 → 좌표 불변 + 턴 +1)": "AC5",
	"AC6 (정지 시 월드 = 셀 × 타일)": "AC6",
}


def _run_godot(godot: str, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[godot, "--headless", "--path", str(project), *args],
		capture_output=True, text=True, timeout=300,
	)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		prog="run_dungeon_turns.py",
		description="dungeon_and_turns 수용 기준 1~6 자동 검증 러너",
	)
	parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
	parser.add_argument("--project", default=str(REPO_ROOT))
	args = parser.parse_args(argv)

	project = Path(args.project).resolve()
	godot = args.godot

	print("=" * 64)
	print("acceptance: dungeon_and_turns 수용 기준 1~6 (Godot 헤드리스)")
	print(f"프로젝트: {project}")
	print("=" * 64)

	if shutil.which(godot) is None and not Path(godot).exists():
		print(f"오류: godot 실행 파일을 찾을 수 없습니다 ({godot!r}). "
			  f"--godot 로 경로를 지정하세요.", file=sys.stderr)
		return 2

	# 1) import — 전역 클래스(DungeonGenerator/Grid/Player/TurnManager) 캐시 보장 (멱등)
	try:
		imp = _run_godot(godot, project, "--import")
	except subprocess.TimeoutExpired:
		print("오류: 임포트 타임아웃 (300s)", file=sys.stderr)
		return 2
	if imp.returncode != 0:
		print("오류: 임포트 실패 — 수용 테스트를 실행할 수 없습니다.", file=sys.stderr)
		print(imp.stderr.strip(), file=sys.stderr)
		return 2

	# 2) 수용 테스트 스크립트 실행
	try:
		res = _run_godot(godot, project, "--script", ACCEPT_SCRIPT)
	except subprocess.TimeoutExpired:
		print("오류: 수용 테스트 타임아웃 (300s)", file=sys.stderr)
		return 2

	out = res.stdout
	checks = [ln for ln in out.splitlines() if ln.startswith(("[PASS]", "[FAIL]"))]
	failed = [ln for ln in checks if ln.startswith("[FAIL]")]
	passed_marker = "ACCEPT_RESULT: PASS" in out

	# 개별 체크 출력
	for ln in checks:
		print(f"  {ln}")

	# 수용 기준별 매핑 요약
	print("-" * 64)
	print("수용 기준별 결과:")
	all_ok = True
	for label, prefix in CRITERIA.items():
		group = [ln for ln in checks if prefix in ln]
		group_fail = [ln for ln in group if ln.startswith("[FAIL]")]
		ok = bool(group) and not group_fail
		all_ok = all_ok and ok
		badge = "PASS" if ok else "FAIL"
		print(f"  [{badge}] {label}  ({len(group)}개 체크)")

	ok = passed_marker and res.returncode == 0 and not failed and all_ok
	print("-" * 64)
	if ok:
		print(f"결과: 전체 통과 ({len(checks)}개 체크)")
		return 0
	print(f"결과: 실패 (실패 체크 {len(failed)}건, ACCEPT_RESULT={'PASS' if passed_marker else 'FAIL'}, "
		  f"exit={res.returncode})")
	if not checks:
		print(out.strip()[-1000:] or res.stderr.strip()[-1000:], file=sys.stderr)
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
