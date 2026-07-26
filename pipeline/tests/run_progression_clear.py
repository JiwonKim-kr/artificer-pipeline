#!/usr/bin/env python3
"""progression_and_clear(Spec C) 수용 기준 자동 테스트 러너.

승인 spec(docs/specs/progression_and_clear.md)의 수용 기준 1~12 를, Godot 헤드리스
SceneTree 스크립트(acceptance_progression_clear.gd)로 검증한다:

  1) 처치 EXP    — 몬스터 처치 → 처치자 EXP += 그 개체의 경험치 보상
  2) 레벨업 연쇄 — 임계치 도달 → 레벨 +1·잉여 이월·스탯 증가·회복(다중 레벨업 정확)
  3) 상태창 갱신 — HP/LV/EXP/층수 표시 + 값 변화(피격·레벨업) 즉시 반영
  4) 게임오버    — HP 0 → 게임오버 상태 + 던전 입력 차단(승탑자 안 움직임)
  5) 재시작      — 층1·레벨1·HP최대·새 던전(진행 초기화)
  6) 돌파        — 계단(STAIRS_UP)에서 돌파 → 층수 +1·새 던전·시작 배치
  7) 이월        — 돌파 후 HP·레벨·EXP·능력치 유지(무상 회복 없음)
  8) 시드 결정성 — 같은 기저 시드 → 층별 던전 동일·층 시퀀스 재현
  9) 승리        — 10층 돌파 → 1층계 완주 승리 상태
 10) 돌파 무효   — 계단 아닌 곳 돌파 입력은 무변화
 11) 강타 획득   — 획득 레벨 전에는 활성화 무효
 12) 강타 강화   — 활성화 → 다음 범프 강화 + 쿨다운 + 쿨다운 경과 후 재활성화

(수용 기준 13 「던전+상태창 렌더」는 play_test --screenshot 스테이지가 담당 — 이 밖.)

플로우:
  1) godot --headless --import  (전역 클래스 캐시 보장, 멱등)
  2) godot --headless --script <acceptance_progression_clear.gd>
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
ACCEPT_SCRIPT = "res://pipeline/tests/acceptance_progression_clear.gd"

# 각 수용 기준 → 체크 라벨 접두사(리포트 매핑용)
CRITERIA = {
	"AC1 (처치 EXP — 처치자에게 경험치 보상 부여)": "AC1",
	"AC2 (레벨업 — 임계치·잉여 이월·스탯 증가·회복, 다중 연쇄)": "AC2",
	"AC3 (상태창 — HP/LV/EXP/층수 표시 + 값 변화 반영)": "AC3",
	"AC4 (게임오버 — HP 0 → 상태 전환 + 입력 차단)": "AC4",
	"AC5 (재시작 — 층1·레벨1·HP최대·진행 초기화)": "AC5",
	"AC6 (돌파 — 계단에서 층수 +1·새 던전·시작 배치)": "AC6",
	"AC7 (이월 — 돌파 후 HP·레벨·EXP 유지, 무상 회복 없음)": "AC7",
	"AC8 (시드 결정성 — 같은 기저 시드 층별 동일·층 시퀀스)": "AC8",
	"AC9 (승리 — 10층 돌파 = 1층계 완주)": "AC9",
	"AC10 (돌파 무효 — 계단 아닌 곳 입력 무변화)": "AC10",
	"AC11 (강타 획득 — 획득 레벨 전 활성화 무효)": "AC11",
	"AC12 (강타 강화 — 강화·쿨다운·쿨다운 경과 후 재활성화)": "AC12",
}


def _run_godot(godot: str, project: Path, *args: str) -> subprocess.CompletedProcess[str]:
	return subprocess.run(
		[godot, "--headless", "--path", str(project), *args],
		capture_output=True, text=True, timeout=300,
	)


def main(argv: list[str] | None = None) -> int:
	parser = argparse.ArgumentParser(
		prog="run_progression_clear.py",
		description="progression_and_clear 수용 기준 1~12 자동 검증 러너",
	)
	parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
	parser.add_argument("--project", default=str(REPO_ROOT))
	args = parser.parse_args(argv)

	project = Path(args.project).resolve()
	godot = args.godot

	print("=" * 64)
	print("acceptance: progression_and_clear 수용 기준 1~12 (Godot 헤드리스)")
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
		# 접두사 정확 매칭(AC1 이 AC10/AC11/AC12 를 오포함하지 않도록 경계 확인).
		group = [ln for ln in checks if _has_prefix(ln, prefix)]
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


def _has_prefix(line: str, prefix: str) -> bool:
	"""체크 라벨이 'ACn' 접두사로 시작하는지 — 뒤에 숫자가 이어지면(AC1 vs AC12) 다른 기준."""
	idx = line.find(prefix)
	if idx == -1:
		return False
	after = line[idx + len(prefix):idx + len(prefix) + 1]
	return not after.isdigit()


if __name__ == "__main__":
	raise SystemExit(main())
