#!/usr/bin/env python3
"""player_movement 수용 기준 자동 테스트 러너.

[sample_game 픽스처 러너] 예전 검증 데모의 수용 기준 1~4 를, Godot 헤드리스
SceneTree 스크립트(acceptance_player_movement.gd)로 실제 Player 를 인스턴스화해
검증한다. play test(스모크)가 다루는 것은 기준 5(메인 씬 로드)뿐이므로, 이동/
차단/경계/정렬 행위는 이 러너가 책임진다.

플로우:
  1) godot --headless --import  (전역 클래스 캐시 보장, 멱등)
  2) godot --headless --script <acceptance_player_movement.gd>
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

# 이 러너는 pipeline/tests/fixtures/sample_game/ 로 이전되었다(검증 대상 게임에
# 무관한 픽스처). 항상 --project <복제본> 으로 호출되며, 복제본에는 sample_game.install()
# 이 수용 스크립트를 res://pipeline/tests/acceptance_player_movement.gd 로 깔아 둔다.
FIXTURE_DIR = Path(__file__).resolve().parent
REPO_ROOT = FIXTURE_DIR.parents[3]  # fixtures/sample_game -> fixtures -> tests -> pipeline -> repo
ACCEPT_SCRIPT = "res://pipeline/tests/acceptance_player_movement.gd"

# 각 수용 기준을 검증하는 체크 라벨 접두사 (리포트 매핑용)
CRITERIA = {
	"AC1 (입력 1회 → 그리드 1칸)": "AC1",
	"AC2 (이동 중 입력 무시 — 반칸 끊김 없음)": "AC2",
	"AC3 (경계 밖/차단 → 좌표 불변)": "AC3",
	"AC4 (정지 시 월드=셀×타일 정렬)": "AC4",
}


def _run_godot(godot: str, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[godot, "--headless", "--path", str(project), *args],
		capture_output=True, text=True, timeout=300,
	)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		prog="run_acceptance_player_movement.py",
		description="player_movement 수용 기준 1~4 자동 검증 러너",
	)
	parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
	parser.add_argument("--project", default=str(REPO_ROOT))
	args = parser.parse_args(argv)

	project = Path(args.project).resolve()
	godot = args.godot

	print("=" * 64)
	print("acceptance: player_movement 수용 기준 1~4 (Godot 헤드리스)")
	print(f"프로젝트: {project}")
	print("=" * 64)

	if shutil.which(godot) is None and not Path(godot).exists():
		print(f"오류: godot 실행 파일을 찾을 수 없습니다 ({godot!r}). "
			  f"--godot 로 경로를 지정하세요.", file=sys.stderr)
		return 2

	# 1) import — 전역 클래스(Grid/Player) 캐시 보장 (멱등)
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
		# 마커/체크가 전혀 없으면 원인 파악용으로 stderr/stdout 일부 노출
		print(out.strip()[-1000:] or res.stderr.strip()[-1000:], file=sys.stderr)
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
