class_name DungeonGenerator
extends RefCounted
## 시드 기반 방-복도형 던전 생성기 (결정적, 도달성 보장).
##
## 지하 미궁 한 층(lore/canon/world.md: 1~10층 첫 층계 「지하 미궁」)을 절차적으로
## 생성한다. 여러 직사각형 방을 배치하고, **각 방을 직전 방과 복도로 연결**해
## 방들이 하나의 사슬(chain)로 이어지게 만든다 → 카브된 모든 바닥은 시작 방에서
## 도달 가능하다(고립 방 없음, 수용 기준 1).
##
## 맵 크기·방 개수·방 크기 범위는 코드에 상수로 박지 않고 **파라미터(딕셔너리)**로
## 받는다(장르/밸런스 데이터화 — CLAUDE.md/HANDOFF §6-3). 노멀 난이도 기본값은
## NORMAL_PARAMS 로 한 곳에 모아 둔다.
## spec: docs/specs/dungeon_and_turns.md (Spec A).

## 타일 종류. WALL 만 비-보행, 나머지는 보행 가능.
enum Tile { WALL, FLOOR, STAIRS_UP, STAIRS_DOWN }

## 보행 가능한 타일 종류(Grid walkable 판정에 주입).
const WALKABLE_TILES: Array[int] = [Tile.FLOOR, Tile.STAIRS_UP, Tile.STAIRS_DOWN]

## 노멀 난이도 생성 파라미터(데이터 — 이 사전이 유일한 밸런스 출처).
## 다른 난이도가 생기면 별도 사전으로 추가하고 generate() 에 주입한다.
const NORMAL_PARAMS: Dictionary = {
	"map_width": 40,
	"map_height": 24,
	"max_rooms": 8,
	"room_min_size": 5,
	"room_max_size": 9,
}

## 시드로 던전을 생성한다.
## 반환: {
##   "tiles":  Array[Array[int]]  (tiles[y][x] = Tile),
##   "width":  int, "height": int,
##   "start":  Vector2i  (내려온 계단 = 승탑자 시작),
##   "exit":   Vector2i  (올라가는 계단 = 다음 층 출구, 돌파 동작은 Spec C),
##   "rooms":  Array[Rect2i],
## }
func generate(params: Dictionary, seed_value: int) -> Dictionary:
	var width: int = int(params.get("map_width", NORMAL_PARAMS["map_width"]))
	var height: int = int(params.get("map_height", NORMAL_PARAMS["map_height"]))
	var max_rooms: int = int(params.get("max_rooms", NORMAL_PARAMS["max_rooms"]))
	var room_min: int = int(params.get("room_min_size", NORMAL_PARAMS["room_min_size"]))
	var room_max: int = int(params.get("room_max_size", NORMAL_PARAMS["room_max_size"]))

	var rng := RandomNumberGenerator.new()
	rng.seed = seed_value

	# 전부 벽으로 초기화.
	var tiles: Array = []
	for y in height:
		var row: Array[int] = []
		for x in width:
			row.append(Tile.WALL)
		tiles.append(row)

	var rooms: Array[Rect2i] = []
	for _i in max_rooms:
		var w: int = rng.randi_range(room_min, room_max)
		var h: int = rng.randi_range(room_min, room_max)
		# 1타일 경계는 항상 벽으로 남겨 둔다(맵 가장자리 보행 방지).
		if width - w - 1 < 1 or height - h - 1 < 1:
			continue
		var rx: int = rng.randi_range(1, width - w - 1)
		var ry: int = rng.randi_range(1, height - h - 1)
		var new_room := Rect2i(rx, ry, w, h)

		# 1타일 여백을 두고 겹치면 폐기(연결하지 않으므로 고립 바닥이 생기지 않는다).
		var overlaps := false
		for r in rooms:
			if _rooms_overlap(new_room, r, 1):
				overlaps = true
				break
		if overlaps:
			continue

		_carve_room(tiles, new_room)

		# 직전 방과 복도로 연결 → 방들이 하나의 사슬로 이어진다(도달성 보장).
		if not rooms.is_empty():
			var prev := _room_center(rooms[rooms.size() - 1])
			var cur := _room_center(new_room)
			if rng.randi() % 2 == 0:
				_carve_h_corridor(tiles, prev.x, cur.x, prev.y)
				_carve_v_corridor(tiles, prev.y, cur.y, cur.x)
			else:
				_carve_v_corridor(tiles, prev.y, cur.y, prev.x)
				_carve_h_corridor(tiles, prev.x, cur.x, cur.y)

		rooms.append(new_room)

	# 방이 하나도 안 나온 극단(파라미터 이상) 방어: 중앙에 최소 방 1개 강제.
	if rooms.is_empty():
		var fallback := Rect2i(width / 2 - 1, height / 2 - 1, 2, 2)
		_carve_room(tiles, fallback)
		rooms.append(fallback)

	var start := _room_center(rooms[0])
	var exit := _room_center(rooms[rooms.size() - 1])
	tiles[start.y][start.x] = Tile.STAIRS_DOWN
	tiles[exit.y][exit.x] = Tile.STAIRS_UP

	return {
		"tiles": tiles,
		"width": width,
		"height": height,
		"start": start,
		"exit": exit,
		"rooms": rooms,
	}


## 벽 좌표 목록(Grid blocked-cell 경로용, 타일 주입을 쓰지 않는 소비자를 위해 제공).
func collect_walls(tiles: Array) -> Array[Vector2i]:
	var walls: Array[Vector2i] = []
	for y in tiles.size():
		var row: Array = tiles[y]
		for x in row.size():
			if int(row[x]) == Tile.WALL:
				walls.append(Vector2i(x, y))
	return walls


## 정수 중심(내림). Rect2i.get_center 대신 명시 계산으로 결정성/이식성 확보.
func _room_center(r: Rect2i) -> Vector2i:
	return Vector2i(r.position.x + r.size.x / 2, r.position.y + r.size.y / 2)


## pad 만큼 여백을 두고 두 방이 겹치는지.
func _rooms_overlap(a: Rect2i, b: Rect2i, pad: int) -> bool:
	return (
		a.position.x - pad < b.position.x + b.size.x
		and a.position.x + a.size.x + pad > b.position.x
		and a.position.y - pad < b.position.y + b.size.y
		and a.position.y + a.size.y + pad > b.position.y
	)


func _carve_room(tiles: Array, r: Rect2i) -> void:
	for y in range(r.position.y, r.position.y + r.size.y):
		for x in range(r.position.x, r.position.x + r.size.x):
			tiles[y][x] = Tile.FLOOR


func _carve_h_corridor(tiles: Array, x1: int, x2: int, y: int) -> void:
	var height: int = tiles.size()
	if y < 0 or y >= height:
		return
	var width: int = tiles[0].size()
	for x in range(mini(x1, x2), maxi(x1, x2) + 1):
		if x >= 0 and x < width:
			tiles[y][x] = Tile.FLOOR


func _carve_v_corridor(tiles: Array, y1: int, y2: int, x: int) -> void:
	var height: int = tiles.size()
	if height == 0:
		return
	var width: int = tiles[0].size()
	if x < 0 or x >= width:
		return
	for y in range(mini(y1, y2), maxi(y1, y2) + 1):
		if y >= 0 and y < height:
			tiles[y][x] = Tile.FLOOR
