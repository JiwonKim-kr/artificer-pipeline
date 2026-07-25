class_name Dungeon
extends Node2D
## 던전 런타임: 생성 → 타일 렌더 → 승탑자·계단 배치 → 카메라.
##
## _ready 에서 DungeonGenerator 로 시드 기반 던전을 생성하고, 결과 타일 격자를
## Sprite2D 타일로 렌더한다(각 셀 = 셀×타일 크기에 중앙 배치). Grid 에 타일을
## 주입해 walkable 판정을 던전 데이터로 돌리고, TurnManager 를 만들어 Player 에
## grid·시작 셀·turn_manager 를 configure 한다. 카메라는 씬에서 Player 의 자식이라
## 승탑자를 항상 화면 중앙에 둔다(수용 기준 7).
##
## 맵/방 파라미터는 데이터(params 딕셔너리 또는 DungeonGenerator.NORMAL_PARAMS).
## 장르/밸런스 상수를 코드에 박지 않는다.
## spec: docs/specs/dungeon_and_turns.md (dungeon.gd 역할).

## 타일 텍스처(씬에서 placeholder ext_resource 로 주입 → art reskin 이 교체).
@export var floor_texture: Texture2D
@export var wall_texture: Texture2D
@export var stairs_up_texture: Texture2D

## 생성 시드(데이터). 같은 시드 → 같은 던전(수용 기준 2).
@export var dungeon_seed: int = 1337
## 생성 파라미터(비우면 노멀 난이도 기본값 사용).
@export var params: Dictionary = {}
## 타일 크기(px). Grid·Player 와 공유.
@export var tile_size: int = 16

var grid: Grid = null
var turn_manager: TurnManager = null
var result: Dictionary = {}

@onready var _tiles_root: Node2D = $Tiles
@onready var _player: Player = $Player


func _ready() -> void:
	build()


## 던전을 생성·렌더하고 승탑자를 배치한다. (재생성에도 재사용 가능)
func build() -> void:
	var p: Dictionary = params if not params.is_empty() else DungeonGenerator.NORMAL_PARAMS
	var generator := DungeonGenerator.new()
	result = generator.generate(p, dungeon_seed)

	var tiles: Array = result["tiles"]

	# Grid: 던전 타일을 walkable 판정 소스로 주입.
	grid = Grid.new(tile_size, int(result["width"]), int(result["height"]))
	grid.configure_tiles(tiles, DungeonGenerator.WALKABLE_TILES)

	_render_tiles(tiles)

	# 턴 매니저 생성(적 페이즈 훅은 Spec B 에서 채움).
	turn_manager = TurnManager.new()
	turn_manager.name = "TurnManager"
	add_child(turn_manager)

	# 승탑자를 시작 계단(내려온 곳)에 배치하고 그리드·턴매니저를 주입.
	if _player != null:
		_player.tile_size = tile_size
		_player.configure(grid, result["start"], turn_manager)


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
			# 셀 중앙 = 셀×타일 크기(Player 도 동일 지점에 중앙 배치되어 정렬됨).
			sprite.position = Vector2(x, y) * tile_size
			_tiles_root.add_child(sprite)


func _texture_for(tile_type: int) -> Texture2D:
	match tile_type:
		DungeonGenerator.Tile.WALL:
			return wall_texture
		DungeonGenerator.Tile.STAIRS_UP:
			return stairs_up_texture
		# FLOOR 및 STAIRS_DOWN(내려온 계단=시작; 전용 아트는 Spec C 범위) → 바닥 텍스처.
		_:
			return floor_texture
