class_name Player
extends Node2D
## 그리드 위에서 4방향(상·하·좌·우) 한 칸씩 이동하는 플레이어 컨트롤러.
##
## 입력 → 그리드 좌표 갱신 → 월드 좌표 보간. 이동 가능 판정은 Grid 에 위임한다.
## 타일 크기·맵 데이터는 코드에 하드코딩하지 않고 export(주입 데이터)로 받는다
## (장르 상수 금지 — CLAUDE.md/HANDOFF §6-3).
## [sample_game 픽스처] 파이프라인 자체 테스트용. 예전 검증 데모의 player 로직으로,
## 저장소에서 제거되고 이 픽스처로만 남는다(원래 spec: player_movement, 함께 제거됨).

## 한 칸 이동이 완료된 지점. `se attach` 가 발소리 SE 를 연결하는 code_event.
signal step_completed(cell: Vector2i)

## 입력 액션 이름 → 방향 벡터. 액션은 project.godot [input] 에 정의된다.
const DIRECTIONS: Dictionary = {
	"move_up": Vector2i(0, -1),
	"move_down": Vector2i(0, 1),
	"move_left": Vector2i(-1, 0),
	"move_right": Vector2i(1, 0),
}

@export var tile_size: int = 16
@export var map_size: Vector2i = Vector2i.ZERO      # (가로, 세로) 셀 수
@export var blocked_cells: Array[Vector2i] = []     # 차단 타일 목록
@export var start_cell: Vector2i = Vector2i.ZERO    # 시작 셀
@export var move_duration: float = 0.12             # 한 칸 이동 시간(초)

var grid: Grid = null
var cell: Vector2i = Vector2i.ZERO

var _moving: bool = false
var _move_from: Vector2 = Vector2.ZERO
var _move_to: Vector2 = Vector2.ZERO
var _move_elapsed: float = 0.0

func _ready() -> void:
	# 씬으로 실행될 때: export 로 주입된 맵 데이터로 Grid 를 구성한다.
	# (테스트/Main 은 configure() 로 직접 주입할 수 있다.)
	if grid == null:
		var built := Grid.new(tile_size, map_size.x, map_size.y, blocked_cells)
		configure(built, start_cell)

## Grid 와 시작 셀을 주입하고 월드 좌표를 정렬한다.
func configure(p_grid: Grid, p_start_cell: Vector2i) -> void:
	grid = p_grid
	tile_size = p_grid.tile_size
	cell = p_start_cell
	_moving = false
	_move_elapsed = 0.0
	position = grid.cell_to_world(cell)

func is_moving() -> bool:
	return _moving

## 한 칸 이동을 시도한다. 시작하면 true, 무시/차단이면 false.
func try_move(direction: Vector2i) -> bool:
	if _moving:
		return false                      # 수용기준 2: 이동 중 새 입력은 무시(반칸 끊김 없음)
	if grid == null:
		return false
	var target: Vector2i = cell + direction
	if not grid.is_walkable(target):
		return false                      # 수용기준 3: 경계 밖/차단 → 좌표 불변
	cell = target                         # 수용기준 1: 그리드 좌표 정확히 1칸 변경
	_move_from = position
	_move_to = grid.cell_to_world(cell)
	_move_elapsed = 0.0
	_moving = true
	if move_duration <= 0.0:
		_finish_move()                    # 즉시 이동(보간 없음) 설정 시
	return true

func _process(delta: float) -> void:
	if _moving:
		_advance_move(delta)
	else:
		_poll_input()

func _poll_input() -> void:
	for action in DIRECTIONS:
		if InputMap.has_action(action) and Input.is_action_just_pressed(action):
			try_move(DIRECTIONS[action])
			return

func _advance_move(delta: float) -> void:
	_move_elapsed += delta
	var t: float = 1.0
	if move_duration > 0.0:
		t = clampf(_move_elapsed / move_duration, 0.0, 1.0)
	position = _move_from.lerp(_move_to, t)
	if t >= 1.0:
		_finish_move()

func _finish_move() -> void:
	position = _move_to                   # 수용기준 4: 정확히 셀×타일 크기에 정렬(반칸 정지 없음)
	_moving = false
	_move_elapsed = 0.0
	on_step_complete()

## 한 칸 이동 완료 지점. se attach 의 연결 대상(code_event: on_step_complete).
func on_step_complete() -> void:
	step_completed.emit(cell)
