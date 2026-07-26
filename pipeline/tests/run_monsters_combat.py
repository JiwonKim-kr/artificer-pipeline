#!/usr/bin/env python3
"""monsters_and_combat(Spec B) 수용 기준 자동 테스트 러너.

승인 spec(docs/specs/monsters_and_combat.md)의 수용 기준 1~9 를, Godot 헤드리스
SceneTree 스크립트(acceptance_monsters_combat.gd)로 검증한다:

  1) 범프 공격  — 인접 몬스터로 이동 → 공격(이동 안 함) + HP [min,max] 감소 + 1턴
  2) 처치       — HP 0 이하 몬스터 즉시 제거 + 그 칸 walkable 복귀
  3) 적 페이즈  — 승탑자 1턴 → 살아있는 몬스터 전원 결정적 순서로 1회 행동
  4) 그리디 AI  — aggro 안 접근 1칸(막히면 대기) / aggro 밖 제자리 / 슬라임 격턴
  5) 피격       — 몬스터 인접 공격 → 승탑자 HP [몬스터 min,max] 감소
  6) 사망 신호  — 승탑자 HP 0 이하 → died 1회 방출
  7) 스폰 결정성 — 같은 시드 → 몬스터 배치 완전 동일
  8) 데미지 범위+재현성 — 항상 [min,max], 같은 시드·순서 → 동일 데미지 시퀀스
  9) 겹침 금지  — 승탑자·몬스터가 같은 칸에 겹치지 않음(다중 턴)

(수용 기준 10 「메인 씬 렌더」는 play_test --screenshot 스테이지가 담당 — 이 밖.)

플로우:
  1) godot --headless --import  (전역 클래스 캐시 보장, 멱등)
  2) godot --headless --script <acceptance_monsters_combat.gd>
  3) [PASS]/[FAIL] 마커 + ACCEPT_RESULT 로 판정 + 수용기준별 매핑 리포트.

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
ACCEPT_SCRIPT = "res://pipeline/tests/acceptance_monsters_combat.gd"

# 각 수용 기준 → 체크 라벨 접두사(리포트 매핑용)
CRITERIA = {
	"AC1 (범프 공격 — 이동 대신 공격 + HP [min,max] 감소 + 1턴)": "AC1",
	"AC2 (처치 — 제거 + 칸 walkable 복귀)": "AC2",
	"AC3 (적 페이즈 — 살아있는 몬스터 전원 1회 행동)": "AC3",
	"AC4 (그리디 접근 — 1칸 접근/막힘 대기/aggro/격턴)": "AC4",
	"AC5 (피격 — 승탑자 HP [몬스터 min,max] 감소)": "AC5",
	"AC6 (사망 신호 — died 1회)": "AC6",
	"AC7 (스폰 결정성 — 같은 시드 동일 배치)": "AC7",
	"AC8 (데미지 범위 + 시드 재현성)": "AC8",
	"AC9 (겹침 금지)": "AC9",
}


def _run_godot(godot: str, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[godot, "--headless", "--path", str(project), *args],
		capture_output=True, text=True, timeout=300,
	)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		prog="run_monsters_combat.py",
		description="monsters_and_combat 수용 기준 1~9 자동 검증 러너",
	)
	parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
	parser.add_argument("--project", default=str(REPO_ROOT))
	args = parser.parse_args(argv)

	project = Path(args.project).resolve()
	godot = args.godot

	print("=" * 64)
	print("acceptance: monsters_and_combat 수용 기준 1~9 (Godot 헤드리스)")
	print(f"프로젝트: {project}")
	print("=" * 64)

	if shutil.which(godot) is None and not Path(godot).exists():
		print(f"오류: godot 실행 파일을 찾을 수 없습니다 ({godot!r}). "
			  f"--godot 로 경로를 지정하세요.", file=sys.stderr)
		return 2

	# 1) import — 전역 클래스 캐시 보장(멱등)
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

	for ln in checks:
		print(f"  {ln}")

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
		print(out.strip()[-1500:] or res.stderr.strip()[-1500:], file=sys.stderr)
	return 1


if __name__ == "__main__":
	raise SystemExit(main())
