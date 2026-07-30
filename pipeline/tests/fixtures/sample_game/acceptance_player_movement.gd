extends SceneTree
## [sample_game 픽스처] 파이프라인 자체 테스트용 수용 기준 검증 스크립트.
## 예전 검증 데모(player_movement)의 수용 기준 1~4 를 헤드리스로 확인한다. 데모는
## 저장소에서 제거되고 이 픽스처로만 남는다(main = 게임 없는 파이프라인 정본).
##
## 스모크(게이트 #2)가 확인하지 못하는 "이동/차단/경계/정렬" 행위를 Player 를
## 직접 인스턴스화해 검증한다. Grid/Player 스크립트를 preload 로 직접 사용하므로
## 씬/글로벌 클래스 캐시에 의존하지 않는다.
##
## 실행: sample_game.install() 이 이 파일을 복제본의
##   res://pipeline/tests/acceptance_player_movement.gd 로 깔고,
##   run_acceptance_player_movement.py --project <복제본> 이 호출한다.
## 결과: 마지막 줄에 ACCEPT_RESULT: PASS | FAIL 를 출력하고 종료 코드로도 알린다.

const GridScript := preload("res://src/core/grid.gd")
const PlayerScript := preload("res://src/core/player.gd")

const TILE: int = 16

var _fail: int = 0

## 신호(step_completed) 호출 횟수 카운터 — 람다 캡처 대신 명시적 객체로.
class StepCounter:
	extends RefCounted
	var count: int = 0
	func on_step(_cell: Vector2i) -> void:
		count += 1


func _check(label: String, cond: bool) -> void:
	if cond:
		print("[PASS] %s" % label)
	else:
		_fail += 1
		print("[FAIL] %s" % label)


func _make_player(w: int, h: int, blocked: Array, start: Vector2i) -> Node2D:
	var grid := GridScript.new(TILE, w, h, blocked)
	var p: Node2D = PlayerScript.new()
	p.move_duration = 0.1
	p.configure(grid, start)
	return p


## 이동 완료까지 충분한 delta 로 한 번에 진행시킨다.
func _complete_move(p: Node2D) -> void:
	p._advance_move(p.move_duration + 1.0)


func _initialize() -> void:
	print("== acceptance: player_movement (수용기준 1~4) ==")

	# --- AC1: 방향 입력 1회 → 그 방향으로 정확히 1칸 ---------------------
	var p1 := _make_player(5, 5, [], Vector2i(2, 2))
	_check("AC1 우 입력 → 이동 시작(true)", p1.try_move(Vector2i(1, 0)))
	_check("AC1 우 → 그리드 좌표 +x 1칸 (3,2)", p1.cell == Vector2i(3, 2))
	_complete_move(p1)
	_check("AC1 상 입력 → -y 1칸 (3,1)", p1.try_move(Vector2i(0, -1)) and p1.cell == Vector2i(3, 1))
	_complete_move(p1)
	_check("AC1 하 입력 → +y 1칸 (3,2)", p1.try_move(Vector2i(0, 1)) and p1.cell == Vector2i(3, 2))
	_complete_move(p1)
	_check("AC1 좌 입력 → -x 1칸 (2,2)", p1.try_move(Vector2i(-1, 0)) and p1.cell == Vector2i(2, 2))
	_complete_move(p1)

	# --- AC2: 이동 중 새 입력은 현재 이동을 반 칸에서 끊지 않음 -----------
	var p2 := _make_player(5, 5, [], Vector2i(2, 2))
	p2.try_move(Vector2i(1, 0))                       # 이동 시작(완료 전)
	_check("AC2 이동 중 상태 true", p2.is_moving())
	var interrupted: bool = p2.try_move(Vector2i(0, 1))  # 이동 중 새 입력
	_check("AC2 이동 중 새 입력 거부(false)", interrupted == false)
	_check("AC2 목표 셀 불변 (3,2) — 반칸 끊김 없음", p2.cell == Vector2i(3, 2))
	_complete_move(p2)
	_check("AC2 이동 완료 후 정지", not p2.is_moving())

	# --- AC3: 경계 밖/차단 셀로의 입력은 좌표 불변 -----------------------
	var p3 := _make_player(3, 3, [Vector2i(1, 0)], Vector2i(0, 0))
	_check("AC3 경계 밖(좌) 입력 거부(false)", p3.try_move(Vector2i(-1, 0)) == false)
	_check("AC3 경계 밖 → 좌표 불변 (0,0)", p3.cell == Vector2i(0, 0))
	_check("AC3 차단 타일(1,0) 입력 거부(false)", p3.try_move(Vector2i(1, 0)) == false)
	_check("AC3 차단 → 좌표 불변 (0,0)", p3.cell == Vector2i(0, 0))
	_check("AC3 거부 시 이동 아님", not p3.is_moving())

	# --- AC4: 월드 좌표는 항상 셀×타일 크기 정렬(정지 시 반칸 없음) ------
	var p4 := _make_player(5, 5, [], Vector2i(1, 1))
	_check("AC4 초기 정렬 (16,16)", p4.position == Vector2(1 * TILE, 1 * TILE))
	p4.try_move(Vector2i(1, 0))
	p4._advance_move(p4.move_duration * 0.5)          # 이동 절반 진행
	_check("AC4 이동 중(반칸)엔 목표에 미정렬", p4.position != Vector2(2 * TILE, 1 * TILE))
	_complete_move(p4)
	_check("AC4 정지 시 정확 정렬 (32,16)", p4.position == Vector2(2 * TILE, 1 * TILE))
	_check("AC4 정지 시 월드 == 셀×타일", p4.position == Vector2(p4.cell.x * TILE, p4.cell.y * TILE))

	# --- 코드 이벤트: on_step_complete → step_completed 방출(se attach 대상) --
	var p5 := _make_player(5, 5, [], Vector2i(2, 2))
	var counter := StepCounter.new()
	p5.step_completed.connect(counter.on_step)
	p5.try_move(Vector2i(1, 0))
	_complete_move(p5)
	_check("step_completed 1회 방출(발소리 SE 연결 지점)", counter.count == 1)

	if _fail == 0:
		print("ACCEPT_RESULT: PASS")
		quit(0)
	else:
		print("ACCEPT_RESULT: FAIL (%d건)" % _fail)
		quit(1)
