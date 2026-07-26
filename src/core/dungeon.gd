class_name Dungeon
extends Node2D
## 던전 런타임: 생성 → 타일 렌더 → 승탑자·계단 배치 → 몬스터 스폰 → 카메라.
##
## Spec A: DungeonGenerator 로 시드 던전을 생성해 타일을 Sprite2D 로 렌더하고, Grid 에
## 타일을 주입, TurnManager 로 Player 를 configure 한다. Spec B: Combat 을 시드 스트림과
## 배선하고, 시작 방을 제외한 방 바닥에 몬스터를 **시드 결정적**으로 스폰해 씬·grid·
## turn_manager(점유 + 레지스트리)에 등록한다(수용 기준 7·9).
##
## progression_and_clear(Spec C) 확장: **층별 재생성**(`regenerate` — 시드는 기저 시드+
## 층수에서 파생해 결정적, `floor_seed`), 승탑자의 **계단(STAIRS_UP) 도달 판정**
## (`player_on_stairs_up`), 그리고 **HP·성장 이월**(재생성 시 `reset_player_stats=false`
## 로 능력치를 유지 — 층 사이 무상 회복 없음, 수용 기준 7)을 더한다. 매 build 끝에
## `rebuilt` 를 방출해 게임 컨트롤러(game.gd)가 새 turn_manager·스킬 쿨다운 연결 등을
## 재배선하게 한다. 돌파 트리거(계단 위 확인 입력) 판정은 game.gd 가 이 판정을 써서 한다.
##
## 맵/스폰 파라미터는 데이터(NORMAL_PARAMS / NORMAL_SPAWN)이며 RNG 는 던전 시드에서
## 파생한 스트림만 쓴다(전역 무시드 randi 금지). 장르/밸런스 상수를 코드에 박지 않는다.
## spec: docs/specs/dungeon_and_turns.md, docs/specs/monsters_and_combat.md, docs/specs/progression_and_clear.md (dungeon.gd 역할).

## 한 층 build 가 끝난 직후 방출(최초·재생성 공통). game.gd 가 새 turn_manager 배선·
## 상태창 바인딩·스킬 쿨다운 연결을 여기서 (재)수행한다.
signal rebuilt

## 층수 → 시드 파생 보폭(밸런스 아님, 층 시퀀스 분리용 큰 소수). floor 1 = 기저 시드.
const FLOOR_SEED_STRIDE: int = 1_000_003

## 스폰 몬스터 씬(루트 Monster). 종류별 스프라이트는 씬이 들고 configure 가 고른다.
const MonsterScene: PackedScene = preload("res://scenes/monster.tscn")

## 노멀 난이도 스폰 파라미터(밸런스의 단일 데이터 출처 — 코드 로직에 상수 금지).
## 쥐가 더 흔하도록 types 를 가중(무리 성향은 다수 스폰으로 표현).
const NORMAL_SPAWN: Dictionary = {
	"per_room_min": 1,
	"per_room_max": 2,
	"types": ["dungeon_rat", "dungeon_rat", "slime"],
}

## 던전 시드 → 파생 RNG 스트림 상수(밸런스 아님, 스트림 분리용).
const COMBAT_STREAM_OFFSET: int = 1009
const SPAWN_STREAM_OFFSET: int = 2003
## 유효 셀이 없을 때의 센티넬(방 내부 셀은 항상 ≥0).
const INVALID_CELL: Vector2i = Vector2i(-1, -1)

## 타일 텍스처(씬에서 placeholder ext_resource 로 주입 → art reskin 이 교체).
@export var floor_texture: Texture2D
@export var wall_texture: Texture2D
@export var stairs_up_texture: Texture2D

## 생성 시드(데이터). 같은 시드 → 같은 던전 + 같은 몬스터 배치(수용 기준 7).
## 층별 재생성 시 game.gd 가 `floor_seed(기저, 층수)` 로 파생한 값을 넣는다.
@export var dungeon_seed: int = 1337
## 생성 파라미터(비우면 노멀 난이도 기본값 사용).
@export var params: Dictionary = {}
## 타일 크기(px). Grid·Player·Monster 와 공유.
@export var tile_size: int = 16

## 다음 build 에서 승탑자 능력치를 초기화할지(Spec C). 최초/재시작=true, 층 돌파=false
## (레벨·EXP·HP 이월 — 무상 회복 없음). regenerate 가 설정한다.
var reset_player_stats: bool = true

var grid: Grid = null
var turn_manager: TurnManager = null
var result: Dictionary = {}

@onready var _tiles_root: Node2D = $Tiles
@onready var _monsters_root: Node2D = $Monsters
@onready var _combat: Combat = $Combat
@onready var _player: Player = $Player


func _ready() -> void:
	build()


## 던전을 생성·렌더하고 승탑자·몬스터를 배치한다. (재생성에도 재사용 가능)
## _ready 가 아직 돌지 않아 @onready 참조가 비어 있어도(테스트가 직접 build 호출 등)
## 자식 노드를 방어적으로 해석해 안전하게 동작한다.
func build() -> void:
	if _tiles_root == null:
		_tiles_root = $Tiles
	if _monsters_root == null:
		_monsters_root = $Monsters
	if _combat == null:
		_combat = $Combat as Combat
	if _player == null:
		_player = $Player as Player

	var p: Dictionary = params if not params.is_empty() else DungeonGenerator.NORMAL_PARAMS
	var generator := DungeonGenerator.new()
	result = generator.generate(p, dungeon_seed)

	var tiles: Array = result["tiles"]

	# Grid: 던전 타일을 walkable 판정 소스로 주입.
	grid = Grid.new(tile_size, int(result["width"]), int(result["height"]))
	grid.configure_tiles(tiles, DungeonGenerator.WALKABLE_TILES)

	_render_tiles(tiles)

	# Combat: 던전 시드에서 파생한 전용 스트림으로 데미지 롤(재현성).
	_combat.rng = Rng.new(dungeon_seed + COMBAT_STREAM_OFFSET)

	# 턴 매니저(적 페이즈 실행자 + 점유 소유자). 재생성 대비 기존 것을 정리(점유·레지스트리
	# 리셋). 새 매니저를 만들어 게임 컨트롤러가 rebuilt 에서 다시 배선한다.
	if is_instance_valid(turn_manager):
		turn_manager.queue_free()
	turn_manager = TurnManager.new()
	turn_manager.name = "TurnManager"
	add_child(turn_manager)
	turn_manager.configure_combat(_player, grid, _combat)

	# 승탑자를 시작 계단(내려온 곳)에 배치하고 문맥을 주입 + 점유 등록.
	# reset_player_stats=false 면 레벨·EXP·HP 이월(층 돌파 — 무상 회복 없음, 수용 기준 7).
	if _player != null:
		_player.tile_size = tile_size
		_player.configure(grid, result["start"], turn_manager, _combat, reset_player_stats)
		turn_manager.set_occupant(_player.cell, _player)

	_spawn_monsters()

	# 배선 완료 신호 — game.gd 가 새 turn_manager·상태창·스킬 쿨다운을 (재)연결한다.
	rebuilt.emit()


## 기저 시드와 층수로 그 층의 결정적 시드를 만든다(floor 1 = 기저 시드). 같은 기저 시드 →
## 같은 층 시퀀스 재현(수용 기준 8). 층별로 보폭을 곱해 겹치지 않는 시드를 준다.
static func floor_seed(base_seed: int, floor: int) -> int:
	return base_seed + maxi(0, floor - 1) * FLOOR_SEED_STRIDE


## 지정 시드로 층을 재생성한다. `carry_stats`=true 면 승탑자 능력치를 이월(층 돌파),
## false 면 초기화(재시작/새 런). build 가 새 던전·몬스터·turn_manager 를 만들고 rebuilt 방출.
func regenerate(seed_value: int, carry_stats: bool) -> void:
	dungeon_seed = seed_value
	reset_player_stats = not carry_stats
	build()


## 승탑자가 지금 올라가는 계단(STAIRS_UP) 칸 위에 있는가 — 돌파 입력의 성립 조건(수용 기준 6·10).
func player_on_stairs_up() -> bool:
	if grid == null or _player == null:
		return false
	return grid.tile_at(_player.cell) == DungeonGenerator.Tile.STAIRS_UP


## 게임 컨트롤러가 승탑자·전투 노드를 안전하게 참조하기 위한 접근자(노드 경로 대신).
func get_player() -> Player:
	if _player == null:
		_player = $Player as Player
	return _player


func get_combat() -> Combat:
	if _combat == null:
		_combat = $Combat as Combat
	return _combat


func _render_tiles(tiles: Array) -> void:
	# 기존 타일 스프라이트 정리(재생성 대비).
	for child in _tiles_root.get_children():
		child.queue_free()
	for y in tiles.size():
		var row: Array = tiles[y]
		for x in row.size():
			var tex: Texture2D = _texture_for(int(row[x]))
			if tex == null:
				continue
			var sprite := Sprite2D.new()
			sprite.texture = tex
			# 셀 중앙 = 셀×타일 크기(Player·Monster 도 동일 지점에 중앙 배치되어 정렬됨).
			sprite.position = Vector2(x, y) * tile_size
			_tiles_root.add_child(sprite)


func _texture_for(tile_type: int) -> Texture2D:
	match tile_type:
		DungeonGenerator.Tile.WALL:
			return wall_texture
		DungeonGenerator.Tile.STAIRS_UP:
			return stairs_up_texture
		# FLOOR 및 STAIRS_DOWN(내려온 계단=시작) → 바닥 텍스처.
		_:
			return floor_texture


# ---------------------------------------------------------------------------
# 몬스터 스폰 (시드 결정적)
# ---------------------------------------------------------------------------
func _spawn_monsters() -> void:
	# 재생성 대비 기존 몬스터 정리.
	for child in _monsters_root.get_children():
		child.queue_free()

	var spawn_rng := Rng.new(dungeon_seed + SPAWN_STREAM_OFFSET)
	var rooms: Array = result.get("rooms", [])
	var start_cell: Vector2i = result.get("start", Vector2i.ZERO)
	var types: Array = NORMAL_SPAWN["types"]
	var per_min: int = int(NORMAL_SPAWN["per_room_min"])
	var per_max: int = int(NORMAL_SPAWN["per_room_max"])

	# 시작 방(rooms[0])은 제외 — 승탑자가 안전하게 시작한다.
	for i in range(1, rooms.size()):
		var room: Rect2i = rooms[i]
		var count: int = spawn_rng.roll(per_min, per_max)
		for _n in count:
			var cell: Vector2i = _pick_free_cell(room, spawn_rng, start_cell)
			if cell == INVALID_CELL:
				continue
			var type_id: String = str(types[spawn_rng.roll(0, types.size() - 1)])
			_add_monster(type_id, cell)


## 방 안에서 비어있는(walkable + 비점유, 시작 칸 제외) 바닥 셀을 시드로 하나 고른다.
## 후보를 행 우선(결정적) 수집 후 rng 인덱스로 선택 → 같은 시드 → 같은 셀.
func _pick_free_cell(room: Rect2i, rng: Rng, start_cell: Vector2i) -> Vector2i:
	var candidates: Array[Vector2i] = []
	for y in range(room.position.y, room.position.y + room.size.y):
		for x in range(room.position.x, room.position.x + room.size.x):
			var c := Vector2i(x, y)
			if c == start_cell:
				continue
			if not grid.is_walkable(c):
				continue
			if turn_manager.is_occupied(c):
				continue
			candidates.append(c)
	if candidates.is_empty():
		return INVALID_CELL
	var idx: int = rng.roll(0, candidates.size() - 1)
	return candidates[idx]


func _add_monster(type_id: String, cell: Vector2i) -> void:
	var monster := MonsterScene.instantiate() as Monster
	monster.configure(type_id, cell, tile_size)
	_monsters_root.add_child(monster)
	turn_manager.register_monster(monster)
