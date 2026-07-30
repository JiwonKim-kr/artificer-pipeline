class_name Grid
extends RefCounted
## 그리드(타일) 좌표 ↔ 월드 좌표 변환과 이동 가능 판정.
##
## 맵 데이터(타일 크기·맵 크기·차단 셀)는 생성 시 **주입**받는다. 장르/스타일
## 상수를 코드에 박지 않는다(파이프라인 범용성 — CLAUDE.md/HANDOFF §6-3).
## [sample_game 픽스처] 파이프라인 자체 테스트용 그리드 로직(원래 spec: player_movement, 제거됨).

var tile_size: int = 16
var map_width: int = 0
var map_height: int = 0
var _blocked: Dictionary = {}  # Vector2i -> true (차단 셀 집합)

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

## 맵 경계 안(0..width-1, 0..height-1)인지.
func is_within_bounds(cell: Vector2i) -> bool:
	return cell.x >= 0 and cell.y >= 0 and cell.x < map_width and cell.y < map_height

## 차단 타일인지.
func is_blocked(cell: Vector2i) -> bool:
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
