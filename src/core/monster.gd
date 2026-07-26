class_name Monster
extends Actor
## 몬스터 개체 — Actor(그리드 개체) 를 상속. 종류별 데이터로 파라미터화.
##
## 능력치(HP·공격력)·aggro 범위·이동력은 **노멀 난이도 데이터 사전**(`NORMAL_MONSTERS`)
## 에서만 온다 — 장르/밸런스 상수를 로직에 박지 않는다(CLAUDE.md). 미궁 쥐는 약하고
## 빠르며(무리는 다수 스폰으로 표현), 슬라임은 맷집이 세고 **격턴 이동**(move_period)
## 으로 느리다. AI 는 그리디 접근(MonsterAi, 순수 함수) — 인접 시 공격, aggro 밖은 대기.
##
## 처치 시 `on_death`(se:enemy_death code_event)가 `died` 시그널을 방출하고,
## TurnManager 가 이를 받아 개체를 제거한다(수용 기준 2). se attach 는 이 시그널에
## 처치 효과음을 붙인다 — src/core 는 SE 를 모른다.
## spec: docs/specs/monsters_and_combat.md (monster.gd 역할, se 표 on_death).

## 처치 순간 방출(효과음: se:enemy_death 연결 지점 + TurnManager 제거 트리거).
signal died(monster: Monster)

## 노멀 난이도 몬스터 데이터(밸런스의 단일 출처 — 코드 로직에 상수 금지).
## lore/canon/glossary.md: 미궁 쥐(약함·무리) / 슬라임(느림·맷집).
const NORMAL_MONSTERS: Dictionary = {
	"dungeon_rat": {
		"hp": 3, "attack_min": 1, "attack_max": 2,
		"aggro_range": 6, "move_period": 1,
	},
	"slime": {
		"hp": 8, "attack_min": 1, "attack_max": 1,
		"aggro_range": 4, "move_period": 2,
	},
}

## 종류별 스프라이트(씬에서 placeholder 로 주입 → art reskin 이 교체).
@export var rat_texture: Texture2D
@export var slime_texture: Texture2D

## 종류 식별자(NORMAL_MONSTERS 키). 스폰 시 configure 로 설정.
var type_id: String = "dungeon_rat"
## 타일 크기(px). 그리드↔월드 정렬용(그리드와 공유).
var tile_size: int = 16
## aggro 범위(체비쇼프). 이 안이면 접근, 밖이면 대기(데이터).
var aggro_range: int = 0
## 이동 주기(격턴 이동 표현). 1=매턴, 2=격턴(슬라임). 데이터.
var move_period: int = 1

# 이동 게이트(느림 표현). move_period 에 도달할 때만 실제 이동.
var _move_gate: int = 0


## 종류·셀·타일 크기를 주입해 스탯/스프라이트/월드좌표를 설정한다(스폰이 호출).
func configure(p_type_id: String, p_cell: Vector2i, p_tile_size: int) -> void:
	type_id = p_type_id if NORMAL_MONSTERS.has(p_type_id) else "dungeon_rat"
	faction = Faction.ENEMY
	cell = p_cell
	tile_size = p_tile_size
	var data: Dictionary = NORMAL_MONSTERS[type_id]
	stats = Stats.from_data(data)
	aggro_range = int(data.get("aggro_range", 0))
	move_period = maxi(1, int(data.get("move_period", 1)))
	_move_gate = 0
	position = Vector2(cell) * float(tile_size)
	_apply_sprite()


## 종류에 맞는 스프라이트를 Sprite2D 에 반영한다(instantiate 직후 호출 가능 —
## 자식은 add_child 전에도 존재하므로 get_node_or_null 로 접근).
func _apply_sprite() -> void:
	var sprite := get_node_or_null("Sprite2D") as Sprite2D
	if sprite == null:
		return
	var tex: Texture2D = slime_texture if type_id == "slime" else rat_texture
	if tex != null:
		sprite.texture = tex


## 적 페이즈 1회 행동: 인접이면 공격, aggro 안이면 한 칸 접근, 그 외 대기.
## 이동/공격 판정과 점유 갱신은 TurnManager 를 통해 이뤄진다(겹침 금지).
func act(turn_manager: TurnManager, player: Actor, grid: Grid, combat: Combat) -> void:
	if is_dead() or player == null:
		return

	# 인접(직교) → 범프 공격(이동력과 무관하게 항상 가능).
	if MonsterAi.is_adjacent(cell, player.cell):
		combat.resolve_bump(self, player)
		return

	# aggro 범위 밖 → 대기.
	if MonsterAi.chebyshev(cell, player.cell) > aggro_range:
		return

	# 느림(격턴/낮은 이동력): 이동 주기에 도달할 때만 실제로 움직인다.
	_move_gate += 1
	if _move_gate < move_period:
		return
	_move_gate = 0

	var is_free := func(c: Vector2i) -> bool: return turn_manager.is_cell_free(c, grid)
	var step: Vector2i = MonsterAi.choose_move(cell, player.cell, is_free)
	if step == Vector2i.ZERO:
		return  # 벽/개체로 막힘 → 제자리(수용 기준 4)

	var target: Vector2i = cell + step
	turn_manager.move_occupant(self, cell, target)
	cell = target
	position = Vector2(cell) * float(tile_size)


## 처치 이벤트 훅(Actor.on_death override). se:enemy_death code_event 지점 —
## se attach 가 이 `died` 시그널에 효과음을 붙인다. TurnManager 는 제거를 수행.
func on_death() -> void:
	died.emit(self)
