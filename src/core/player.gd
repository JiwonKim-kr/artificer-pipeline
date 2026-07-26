class_name Player
extends Actor
## 그리드 위를 **턴제**로 이동하는 승탑자 컨트롤러(Actor 상속).
##
## Spec A: 방향 입력 → grid.walkable 판정 → (성공 시) 좌표 1칸 + turn_manager 에 턴 1
## 소비. 제자리 대기는 좌표 불변 + 턴 1. 벽/경계는 좌표 불변 + 턴 미소비. 시각 보간은
## 턴 판정과 분리(즉시 소비, position 은 목표 셀로 lerp 후 스냅 — 정지 시 항상 정렬).
##
## Spec B: 이동 대상 칸에 **적대 개체(몬스터)** 가 있으면 이동 대신 combat 에 범프 공격을
## 위임하고 1턴 소비한다(수용 기준 1). 피격/사망 이벤트 훅을 열어 둔다:
## `on_hurt`(se:player_hurt 지점, `hurt` 방출) / `on_death`(`died` 방출 — 게임오버는
## Spec C 가 연결). 점유(occupancy)는 TurnManager 가 단일 관리한다.
##
## combat/turn_manager 미주입(Spec A 테스트) 시 범프·점유 로직은 비활성 → 하위 호환.
## spec: docs/specs/dungeon_and_turns.md, docs/specs/monsters_and_combat.md.

## 한 칸 이동이 확정된 지점(턴 소비 직후) 방출. `on_step_complete` 가 낸다.
signal step_completed(cell: Vector2i)
## 승탑자 피격 시 방출(효과음: se:player_hurt 연결 지점). `on_hurt` 가 낸다.
signal hurt
## 승탑자 HP 0 이하 시 1회 방출(게임오버 처리는 Spec C). `on_death` 가 낸다.
signal died

## 방향 입력 액션 → 방향 벡터. 액션은 project.godot [input] 에 정의된다.
const DIRECTIONS: Dictionary = {
	"move_up": Vector2i(0, -1),
	"move_down": Vector2i(0, 1),
	"move_left": Vector2i(-1, 0),
	"move_right": Vector2i(1, 0),
}
## 제자리 대기 입력 액션(1턴 소비, 좌표 불변).
const WAIT_ACTION: String = "move_wait"

## 승탑자 노멀 능력치(밸런스 데이터 — 코드 로직에 상수 금지). 범프 공격이 이 범위를 쓴다.
const NORMAL_PLAYER: Dictionary = {
	"hp": 20, "attack_min": 2, "attack_max": 4,
}

@export var tile_size: int = 16
@export var move_duration: float = 0.12             # 한 칸 시각 보간 시간(초). 0 이면 즉시 스냅.

var grid: Grid = null
var turn_manager: TurnManager = null
var _combat: Combat = null

# 시각 보간 상태(턴 로직과 분리 — 턴은 이 상태를 기다리지 않는다).
var _visual_moving: bool = false
var _move_from: Vector2 = Vector2.ZERO
var _move_to: Vector2 = Vector2.ZERO
var _move_elapsed: float = 0.0


## Grid·시작 셀·(선택)TurnManager·(선택)Combat 을 주입하고 월드 좌표를 정렬한다.
## 던전 런타임(Dungeon)이나 테스트가 호출한다. combat 이 주입되면 범프/점유가 활성화된다.
func configure(
	p_grid: Grid, p_start_cell: Vector2i,
	p_turn_manager: TurnManager = null, p_combat: Combat = null,
) -> void:
	grid = p_grid
	tile_size = p_grid.tile_size
	cell = p_start_cell
	faction = Faction.PLAYER
	stats = Stats.from_data(NORMAL_PLAYER)
	if p_turn_manager != null:
		turn_manager = p_turn_manager
	if p_combat != null:
		_combat = p_combat
	_visual_moving = false
	_move_elapsed = 0.0
	position = grid.cell_to_world(cell)


## 현재 시각 보간 진행 중인지(턴 판정과 무관, 렌더 상태일 뿐).
func is_visual_moving() -> bool:
	return _visual_moving


## 한 칸 이동을 시도한다.
##  - 대상 칸에 적대 개체가 있으면 이동 대신 **범프 공격**(1턴 소비) → true.
##  - 빈 walkable 칸이면 좌표 1칸 갱신 + 점유 이동 + 턴 1 소비 → true.
##  - 벽/경계/(비적대)점유로 막히면 좌표 불변 + 턴 미소비 → false.
func attempt_move(direction: Vector2i) -> bool:
	if grid == null:
		return false
	var target: Vector2i = cell + direction

	# 범프: 대상 칸에 적대 개체 → 공격(이동 대신), 1턴 소비. (combat 문맥이 있을 때만)
	if _combat != null and turn_manager != null:
		var occupant: Actor = turn_manager.occupant_at(target)
		if occupant != null and is_hostile_to(occupant):
			_combat.resolve_bump(self, occupant)
			_consume_turn()
			return true

	if not grid.is_walkable(target):
		return false                      # 수용기준(A) 4: 벽/경계 → 좌표 불변 + 턴 미소비
	# 비적대 개체로 점유된 칸이면 이동 불가(겹침 금지 — 수용 기준 9).
	if turn_manager != null and _combat != null and turn_manager.is_occupied(target):
		return false

	var from: Vector2i = cell
	cell = target                         # 수용기준(A) 3: 그리드 좌표 정확히 1칸
	if turn_manager != null and _combat != null:
		turn_manager.move_occupant(self, from, cell)
	_start_visual_move()                  # 시각 보간(턴과 분리)
	_consume_turn()                       # 수용기준(A) 3: 턴 카운터 +1
	on_step_complete()
	return true


## 제자리 대기: 좌표를 바꾸지 않고 턴만 1 소비한다.
func wait() -> bool:
	_consume_turn()
	return true


func _consume_turn() -> void:
	if turn_manager != null:
		turn_manager.consume_turn()


## 한 칸 이동이 확정된 code_event 지점(se:player_step 은 이 step_completed 에 붙는다).
func on_step_complete() -> void:
	step_completed.emit(cell)


## 피격 이벤트 훅(Actor.on_hurt override). se:player_hurt code_event —
## combat 이 데미지 적용 후 호출하고, se attach 가 이 `hurt` 시그널에 효과음을 붙인다.
func on_hurt() -> void:
	hurt.emit()


## 사망 이벤트 훅(Actor.on_death override). HP 0 이하 시 combat 이 호출 → `died` 1회.
## 게임오버 화면·재시작은 Spec C 가 이 신호에 연결한다(이 spec 은 방출까지).
func on_death() -> void:
	died.emit()


func _ready() -> void:
	# 씬 단독 실행 대비 방어. 던전 런타임은 _ready 이후 configure() 로 실제 문맥을 주입한다.
	pass


func _process(delta: float) -> void:
	_poll_input()
	if _visual_moving:
		_advance_visual(delta)


func _poll_input() -> void:
	# 턴제: 눌린 순간(just_pressed)마다 1행동. 보간 진행 중에도 입력을 막지 않는다.
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
	position = grid.cell_to_world(cell)   # 정지 시 정확히 셀×타일 정렬
	_visual_moving = false
	_move_elapsed = 0.0
