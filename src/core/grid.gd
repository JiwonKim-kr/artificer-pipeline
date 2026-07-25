class_name Grid
extends RefCounted
## 그리드(타일) 좌표 ↔ 월드 좌표 변환과 이동 가능 판정.
##
## 두 가지 데이터 소스를 지원한다(기존 인터페이스 유지 + 던전 확장):
##   1) 차단 셀 집합(blocked) — 초기 player_movement 방식. `_init(...)` 로 주입.
##   2) 던전 타일 격자(tiles) + 보행 가능 타일 종류 — Spec A 던전 방식.
##      `configure_tiles(tiles, walkable_types)` 로 주입하면 walkable 판정이
##      타일 데이터를 따른다(맵 크기도 타일 격자에서 도출).
##
## 맵 데이터는 항상 **주입**받는다. 장르/스타일 상수를 코드에 박지 않는다
## (파이프라인 범용성 — CLAUDE.md/HANDOFF §6-3).
## spec: docs/specs/dungeon_and_turns.md (grid.gd 확장), docs/specs/player_movement.md.

var tile_size: int = 16
var map_width: int = 0
var map_height: int = 0
var _blocked: Dictionary = {}          # Vector2i -> true (차단 셀 집합, 소스 1)
var _tiles: Array = []                 # tiles[y][x] = int (던전 타일, 소스 2)
var _walkable_types: Dictionary = {}   # tile_type(int) -> true

func _init(
	p_tile_size: int = 16,
	p_map_width: int = 0,
	p_map_height: int = 0,
	p_blocked: Array = [],
) -> void:
	tile_size = p_tile_size
	map_width = p_map_width
	map_height = p_map_height
	for c in p_blocked:
		_blocked[Vector2i(c)] = true

## 던전 타일 격자를 주입한다(소스 2 활성화). 맵 크기는 격자에서 도출한다.
## walkable_types 에 없는 타일 종류는 모두 비-보행(blocked)으로 간주한다.
func configure_tiles(tiles: Array, walkable_types: Array) -> void:
	_tiles = tiles
	map_height = tiles.size()
	map_width = (tiles[0] as Array).size() if map_height > 0 else 0
	_walkable_types.clear()
	for t in walkable_types:
		_walkable_types[int(t)] = true

## 셀의 타일 종류를 반환. 타일 소스가 없거나 경계 밖이면 -1.
func tile_at(cell: Vector2i) -> int:
	if _tiles.is_empty() or not is_within_bounds(cell):
		return -1
	return int(_tiles[cell.y][cell.x])

## 맵 경계 안(0..width-1, 0..height-1)인지.
func is_within_bounds(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < map_width and cell.y < map_height

## 차단 타일인지. 타일 격자가 있으면 격자 기준, 없으면 차단 셀 집합 기준.
func is_blocked(cell: Vector2i) -> bool:
	if not _tiles.is_empty():
		if not is_within_bounds(cell):
			return true
		return not _walkable_types.has(int(_tiles[cell.y][cell.x]))
	return _blocked.has(cell)

## 이동 가능(경계 안 + 비차단)인지.
func is_walkable(cell: Vector2i) -> bool:
	return is_within_bounds(cell) and not is_blocked(cell)

## 그리드 좌표 → 월드 좌표(셀 × 타일 크기). 항상 정수 배수로 정렬된다.
func cell_to_world(cell: Vector2i) -> Vector2:
	return Vector2(cell.x * tile_size, cell.y * tile_size)

## 월드 좌표 → 그리드 좌표(내림).
func world_to_cell(world: Vector2) -> Vector2i:
	if tile_size == 0:
		return Vector2i.ZERO
	return Vector2i(int(floor(world.x / tile_size)), int(floor(world.y / tile_size)))
