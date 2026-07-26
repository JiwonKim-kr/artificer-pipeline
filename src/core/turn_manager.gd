class_name TurnManager
extends Node
## 턴 경계(turn boundary) 관리자 + 적 페이즈 실행.
##
## Spec A: 한 번의 유효한 플레이어 행동(이동 1칸/대기/범프 공격)이 **1턴**을 소비하고
## 턴 카운터를 올린다. Spec B: 그 직후의 **적 페이즈**를 이 관리자가 채운다 —
## 등록된 살아있는 몬스터가 **결정적 순서(등록=스폰 순서)**로 1회씩 행동한다.
##
## 또한 그리드 **점유(occupancy)** 의 단일 소유자다: 승탑자·몬스터가 어느 셀을
## 차지하는지 기록해, 범프 판정(플레이어)·개체 회피(AI)·겹침 금지(수용 기준 9)를
## 한 곳에서 보장한다(Grid 는 타일 walkable 만 담당 — Spec A 범위, 미수정).
##
## 전투 문맥(player/grid/combat)이 주입되지 않은 상태(Spec A 테스트 등)에서는 적
## 페이즈가 신호(`enemy_phase`)만 방출하는 no-op 로 남아 하위 호환된다.
## spec: docs/specs/dungeon_and_turns.md, docs/specs/monsters_and_combat.md (적 페이즈 훅).

## 한 턴이 소비되어 카운터가 증가한 직후 방출. 인자는 새 턴 번호.
signal turn_advanced(turn: int)
## 플레이어 페이즈 종료 후의 적 페이즈 진입점(하위 호환 훅). 몬스터 행동 전에 방출.
signal enemy_phase(turn: int)

## 소비된 총 턴 수(= 유효 플레이어 행동 횟수).
var turn_count: int = 0

# --- 전투 문맥(던전 런타임이 주입; 없으면 적 페이즈는 no-op) ---
var _player: Actor = null
var _grid: Grid = null
var _combat: Combat = null

# --- 몬스터 레지스트리(등록=스폰 순서, 결정적 순회) ---
var _monsters: Array[Monster] = []

# --- 점유 맵: Vector2i(cell) -> Actor ---
var _occupants: Dictionary = {}


## 적 페이즈 실행에 필요한 문맥을 주입한다(던전 런타임 전용).
func configure_combat(p_player: Actor, p_grid: Grid, p_combat: Combat) -> void:
	_player = p_player
	_grid = p_grid
	_combat = p_combat


## 유효한 플레이어 행동이 일어났을 때 호출한다. 턴 카운터를 1 올리고 적 페이즈를
## 실행한 뒤 새 턴 번호를 돌려준다. (이동 실패 시에는 호출하지 않는다 — 턴 미소비.)
func consume_turn() -> int:
	turn_count += 1
	turn_advanced.emit(turn_count)
	_run_enemy_phase()
	return turn_count


## 적 페이즈: 하위 호환 신호를 먼저 방출한 뒤, 문맥이 있으면 살아있는 몬스터가
## 결정적 순서로 1회씩 행동한다(이동 또는 공격). 죽은 몬스터는 제외.
func _run_enemy_phase() -> void:
	enemy_phase.emit(turn_count)
	if _player == null or _grid == null or _combat == null:
		return
	# 순회 중 레지스트리 변형(사망 제거 등)에 안전하도록 스냅샷 순회.
	for monster: Monster in _monsters.duplicate():
		if not is_instance_valid(monster) or monster.is_dead():
			continue
		monster.act(self, _player, _grid, _combat)


## 새 층 진입 등에서 턴 카운터를 초기화한다.
func reset() -> void:
	turn_count = 0


# ---------------------------------------------------------------------------
# 몬스터 레지스트리
# ---------------------------------------------------------------------------
## 몬스터를 등록한다(적 페이즈 순회 대상 + 점유 등록 + 사망 시 제거 연결).
func register_monster(monster: Monster) -> void:
	if monster in _monsters:
		return
	_monsters.append(monster)
	set_occupant(monster.cell, monster)
	if not monster.died.is_connected(_on_monster_died):
		monster.died.connect(_on_monster_died)


## 살아있는(유효) 등록 몬스터 수.
func live_monster_count() -> int:
	var n: int = 0
	for m: Monster in _monsters:
		if is_instance_valid(m) and not m.is_dead():
			n += 1
	return n


## 현재 등록된 몬스터 목록(읽기용 사본).
func monsters() -> Array[Monster]:
	return _monsters.duplicate()


## 몬스터 사망 시(monster.on_death → died 신호): 점유 해제 + 레지스트리 제거 +
## 노드 제거. 그 칸은 다시 비어(walkable) 다음 이동/스폰이 쓸 수 있다(수용 기준 2).
func _on_monster_died(monster: Monster) -> void:
	if _occupants.get(monster.cell) == monster:
		_occupants.erase(monster.cell)
	_monsters.erase(monster)
	if monster.is_inside_tree():
		monster.queue_free()


# ---------------------------------------------------------------------------
# 점유(occupancy)
# ---------------------------------------------------------------------------
func set_occupant(cell: Vector2i, actor: Actor) -> void:
	_occupants[cell] = actor


func clear_occupant(cell: Vector2i) -> void:
	_occupants.erase(cell)


## actor 를 from → to 로 옮긴다(from 의 점유가 actor 일 때만 해제).
func move_occupant(actor: Actor, from: Vector2i, to: Vector2i) -> void:
	if from != to and _occupants.get(from) == actor:
		_occupants.erase(from)
	_occupants[to] = actor


## 셀을 차지한 개체(없으면 null).
func occupant_at(cell: Vector2i) -> Actor:
	return _occupants.get(cell)


## 셀이 개체로 점유돼 있는지.
func is_occupied(cell: Vector2i) -> bool:
	return _occupants.has(cell)


## 셀이 이동 가능(타일 walkable + 비점유)인지 — AI 이동 후보 술어.
func is_cell_free(cell: Vector2i, grid: Grid) -> bool:
	return grid.is_walkable(cell) and not _occupants.has(cell)
