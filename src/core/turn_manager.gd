class_name TurnManager
extends Node
## 턴 경계(turn boundary) 관리자.
##
## 로그라이크의 근본 구조: 한 번의 유효한 플레이어 행동(이동 1칸 또는 대기)이
## **1턴**을 소비한다. 이 Spec A 에는 적이 없으므로 턴은 "플레이어 행동 카운터"로만
## 존재하지만, Spec B 의 적 행동이 끼어들 **적 페이즈 훅**을 지금 남겨 둔다.
##
## - 이동 실패(벽/경계)는 턴을 소비하지 않는다 → 실패 시 consume_turn 을 호출하지
##   않는 것은 **호출자(Player)의 책임**이다(TurnManager 는 유효 행동만 받는다).
## - 적 페이즈는 신호(`enemy_phase`)와 가상 메서드(`_run_enemy_phase`) 두 경로로
##   열어 둔다. Spec B 는 둘 중 편한 쪽으로 적 행동을 채운다(현재는 no-op).
## spec: docs/specs/dungeon_and_turns.md (turn_manager.gd 역할).

## 한 턴이 소비되어 카운터가 증가한 직후 방출. 인자는 새 턴 번호.
signal turn_advanced(turn: int)

## 플레이어 페이즈 종료 후의 적 페이즈 진입점(Spec B 채움). 현재는 hook 만.
signal enemy_phase(turn: int)

## 소비된 총 턴 수(= 유효 플레이어 행동 횟수).
var turn_count: int = 0


## 유효한 플레이어 행동이 일어났을 때 호출한다. 턴 카운터를 1 올리고
## 적 페이즈 훅을 실행한 뒤 새 턴 번호를 돌려준다.
## (이동 실패 시에는 호출하지 않는다 — 수용 기준 4: 턴 미소비.)
func consume_turn() -> int:
	turn_count += 1
	turn_advanced.emit(turn_count)
	_run_enemy_phase()
	return turn_count


## 적 페이즈 훅. Spec B 가 override 하여 적 이동/공격을 채운다.
## Spec A 에서는 신호만 방출(no-op)한다.
func _run_enemy_phase() -> void:
	enemy_phase.emit(turn_count)


## 새 층 진입 등에서 턴 카운터를 초기화한다.
func reset() -> void:
	turn_count = 0
