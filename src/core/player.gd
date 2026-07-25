class_name Player
extends Node2D
## 그리드 위를 **턴제(turn-based)**로 이동하는 승탑자 컨트롤러.
##
## 이 Spec A 에서 기존 실시간 폴링+보간 이동을 턴제로 개편했다:
##   방향 입력 → grid.walkable 판정 → (성공 시) 좌표 1칸 갱신 + turn_manager 에
##   행동 제출(턴 1 소비). 제자리 대기 입력은 좌표를 바꾸지 않고 턴만 1 소비한다.
##   벽/경계로의 입력은 좌표 불변 + 턴 미소비다.
##
## 시각적 짧은 보간은 **턴 판정과 분리**된다: 턴은 즉시 소비되고(보간 완료를
## 기다리지 않음), position 은 목표 셀로 부드럽게 lerp 되다가 도달 시 셀×타일에
## 정확히 스냅된다(정지 시 항상 정렬 — 수용 기준 6).
##
## 타일 크기·맵 데이터는 코드에 하드코딩하지 않고 주입(configure)받는다.
## spec: docs/specs/dungeon_and_turns.md (수용 기준 3~6).

## 한 칸 이동이 확정된 지점(턴 소비 직후) 방출. `on_step_complete` 가 이 신호를 낸다.
signal step_completed(cell: Vector2i)

## 방향 입력 액션 → 방향 벡터. 액션은 project.godot [input] 에 정의된다.
const DIRECTIONS: Dictionary = {
	"move_up": Vector2i(0, -1),
	"move_down": Vector2i(0, 1),
	"move_left": Vector2i(-1, 0),
	"move_right": Vector2i(1, 0),
}
## 제자리 대기 입력 액션(1턴 소비, 좌표 불변).
const WAIT_ACTION: String = "move_wait"

@export var tile_size: int = 16
@export var move_duration: float = 0.12             # 한 칸 시각 보간 시간(초). 0 이면 즉시 스냅.

var grid: Grid = null
var turn_manager: TurnManager = null
var cell: Vector2i = Vector2i.ZERO

# 시각 보간 상태(턴 로직과 분리 — 턴은 이 상태를 기다리지 않는다).
var _visual_moving: bool = false
var _move_from: Vector2 = Vector2.ZERO
var _move_to: Vector2 = Vector2.ZERO
var _move_elapsed: float = 0.0


## Grid·시작 셀·(선택)TurnManager 를 주입하고 월드 좌표를 정렬한다.
## 던전 런타임(Dungeon)이나 테스트가 호출한다.
func configure(p_grid: Grid, p_start_cell: Vector2i, p_turn_manager: TurnManager = null) -> void:
	grid = p_grid
	tile_size = p_grid.tile_size
	cell = p_start_cell
	if p_turn_manager != null:
		turn_manager = p_turn_manager
	_visual_moving = false
	_move_elapsed = 0.0
	position = grid.cell_to_world(cell)


## 현재 시각 보간 진행 중인지(턴 판정과 무관, 렌더 상태일 뿐).
func is_visual_moving() -> bool:
	return _visual_moving


## 한 칸 이동을 시도한다. 성공 시 좌표 1칸 갱신 + 턴 1 소비 후 true,
## 벽/경계로 막히면 좌표 불변 + 턴 미소비로 false.
func attempt_move(direction: Vector2i) -> bool:
	if grid == null:
		return false
	var target: Vector2i = cell + direction
	if not grid.is_walkable(target):
		return false                      # 수용기준 4: 벽/경계 → 좌표 불변 + 턴 미소비
	cell = target                         # 수용기준 3: 그리드 좌표 정확히 1칸
	_start_visual_move()                  # 시각 보간(턴과 분리)
	_consume_turn()                       # 수용기준 3: 턴 카운터 +1
	on_step_complete()
	return true


## 제자리 대기: 좌표를 바꾸지 않고 턴만 1 소비한다(수용 기준 5).
func wait() -> bool:
	_consume_turn()
	return true


func _consume_turn() -> void:
	if turn_manager != null:
		turn_manager.consume_turn()


## 한 칸 이동이 확정된 code_event 지점. `se attach` 가 발소리 SE(se:player_step)를
## 이 메서드의 방출 신호(step_completed)에 연결한다(매니페스트 requested_by).
func on_step_complete() -> void:
	step_completed.emit(cell)


func _ready() -> void:
	# 씬으로 단독 실행되는 경우를 대비한 방어. 던전 런타임은 _ready 이후 configure() 로
	# 실제 grid/turn_manager 를 주입한다(자식 _ready 가 부모보다 먼저 도므로 덮어써도 안전).
	pass


func _process(delta: float) -> void:
	_poll_input()
	if _visual_moving:
		_advance_visual(delta)


func _poll_input() -> void:
	# 턴제: 눌린 순간(just_pressed)마다 1행동. 보간 진행 중에도 입력을 막지 않는다
	# (턴은 보간을 기다리지 않는다). 방향과 대기 중 하나만 처리.
	for action in DIRECTIONS:
		if InputMap.has_action(action) and Input.is_action_just_pressed(action):
			attempt_move(DIRECTIONS[action])
			return
	if InputMap.has_action(WAIT_ACTION) and Input.is_action_just_pressed(WAIT_ACTION):
		wait()


func _start_visual_move() -> void:
	_move_from = position
	_move_to = grid.cell_to_world(cell)
	_move_elapsed = 0.0
	_visual_moving = true
	if move_duration <= 0.0:
		_snap_to_cell()                   # 즉시 이동(보간 없음) 설정 시


func _advance_visual(delta: float) -> void:
	_move_elapsed += delta
	var t: float = 1.0
	if move_duration > 0.0:
		t = clampf(_move_elapsed / move_duration, 0.0, 1.0)
	position = _move_from.lerp(_move_to, t)
	if t >= 1.0:
		_snap_to_cell()


func _snap_to_cell() -> void:
	position = grid.cell_to_world(cell)   # 수용기준 6: 정지 시 정확히 셀×타일 정렬
	_visual_moving = false
	_move_elapsed = 0.0
