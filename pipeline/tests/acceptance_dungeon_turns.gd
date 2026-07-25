extends SceneTree
## 승인 spec `dungeon_and_turns`(Spec A)의 수용 기준 1~6 을 헤드리스로 검증한다.
##
## 스모크(게이트 #2)·스크린샷은 "씬이 로드/렌더되는가"(수용 기준 7)만 보므로,
## 생성 도달성·결정성·턴 판정·정렬은 이 테스트가 책임진다. 핵심 스크립트를
## preload 로 직접 인스턴스화하므로 씬/글로벌 클래스 캐시에 의존하지 않는다.
##
## 실행: godot --headless --path <repo> --script res://pipeline/tests/acceptance_dungeon_turns.gd
## 결과: 마지막 줄 ACCEPT_RESULT: PASS | FAIL + 종료 코드.
## spec: docs/specs/dungeon_and_turns.md

const GeneratorScript := preload("res://src/core/dungeon_generator.gd")
const GridScript := preload("res://src/core/grid.gd")
const PlayerScript := preload("res://src/core/player.gd")
const TurnManagerScript := preload("res://src/core/turn_manager.gd")

const TILE: int = 16
const WALL := GeneratorScript.Tile.WALL
const FLOOR := GeneratorScript.Tile.FLOOR

var _fail: int = 0


func _check(label: String, cond: bool) -> void:
	if cond:
		print("[PASS] %s" % label)
	else:
		_fail += 1
		print("[FAIL] %s" % label)


# --- 던전 도달성/결정성 헬퍼 ------------------------------------------------
func _floor_count(tiles: Array) -> int:
	var c: int = 0
	for y in tiles.size():
		var row: Array = tiles[y]
		for x in row.size():
			if int(row[x]) != WALL:
				c += 1
	return c


## 시작점에서 4방향 flood-fill 로 도달 가능한 비-벽 셀 수.
func _reachable_count(tiles: Array, start: Vector2i) -> int:
	var h: int = tiles.size()
	var w: int = (tiles[0] as Array).size() if h > 0 else 0
	var seen: Dictionary = {}
	var stack: Array[Vector2i] = [start]
	seen[start] = true
	var dirs: Array[Vector2i] = [Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)]
	while not stack.is_empty():
		var c: Vector2i = stack.pop_back()
		for d in dirs:
			var n: Vector2i = c + d
			if n.x < 0 or n.y < 0 or n.x >= w or n.y >= h:
				continue
			if seen.has(n):
				continue
			if int((tiles[n.y] as Array)[n.x]) == WALL:
				continue
			seen[n] = true
			stack.append(n)
	return seen.size()


func _tiles_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	for y in a.size():
		var ra: Array = a[y]
		var rb: Array = b[y]
		if ra.size() != rb.size():
			return false
		for x in ra.size():
			if int(ra[x]) != int(rb[x]):
				return false
	return true


## 5x5 벽 테두리 + 내부 바닥, (2,2) 에 벽 하나. 이동/대기/차단 테스트용.
func _walled_tiles() -> Array:
	var W := WALL
	var F := FLOOR
	return [
		[W, W, W, W, W],
		[W, F, F, F, W],
		[W, F, W, F, W],
		[W, F, F, F, W],
		[W, W, W, W, W],
	]


func _make_player(tiles: Array, start: Vector2i, tm: Object) -> Object:
	var grid = GridScript.new(TILE, 0, 0)
	grid.configure_tiles(tiles, GeneratorScript.WALKABLE_TILES)
	var p = PlayerScript.new()
	p.move_duration = 0.0            # 즉시 스냅 — 정지 시 정렬을 바로 검증(수용 기준 6)
	p.configure(grid, start, tm)
	return p


func _initialize() -> void:
	print("== acceptance: dungeon_and_turns (수용 기준 1~6) ==")

	# --- AC1 도달성 + AC2 결정성 (실제 생성기, 여러 시드) --------------------
	var generator = GeneratorScript.new()
	for seed_value in [1, 1337, 99999]:
		var r1: Dictionary = generator.generate(GeneratorScript.NORMAL_PARAMS, seed_value)
		var tiles1: Array = r1["tiles"]
		var start1: Vector2i = r1["start"]
		var total: int = _floor_count(tiles1)
		var reach: int = _reachable_count(tiles1, start1)
		_check("AC1 seed=%d 모든 바닥이 시작점에서 도달 (%d/%d)" % [seed_value, reach, total],
			reach == total and total > 0)
		# 시작/출구는 비-벽(보행 가능) 이어야 한다.
		_check("AC1 seed=%d 시작=계단(비-벽)" % seed_value,
			int((tiles1[start1.y] as Array)[start1.x]) != WALL)

		# AC2: 같은 시드로 다시 생성 → 완전히 동일
		var r2: Dictionary = generator.generate(GeneratorScript.NORMAL_PARAMS, seed_value)
		_check("AC2 seed=%d 재생성 타일 배치 동일(결정성)" % seed_value,
			_tiles_equal(tiles1, r2["tiles"]))
		_check("AC2 seed=%d 시작/출구 좌표 동일" % seed_value,
			r1["start"] == r2["start"] and r1["exit"] == r2["exit"])

	# 서로 다른 시드는 (거의) 다른 던전 — 시드가 실제로 반영됨을 확인
	var da: Dictionary = generator.generate(GeneratorScript.NORMAL_PARAMS, 1)
	var db: Dictionary = generator.generate(GeneratorScript.NORMAL_PARAMS, 2)
	_check("AC2 다른 시드 → 다른 배치(시드 반영)", not _tiles_equal(da["tiles"], db["tiles"]))

	# --- AC3 이동=+1 / AC6 정렬 ---------------------------------------------
	var tiles := _walled_tiles()
	var tm3 = TurnManagerScript.new()
	var p3 = _make_player(tiles, Vector2i(1, 1), tm3)
	_check("AC3 초기 턴 카운터 0", tm3.turn_count == 0)
	var moved: bool = p3.attempt_move(Vector2i(1, 0))   # (1,1)→(2,1) 바닥
	_check("AC3 유효 이동 → true", moved)
	_check("AC3 그리드 좌표 +x 1칸 (2,1)", p3.cell == Vector2i(2, 1))
	_check("AC3 턴 카운터 정확히 1", tm3.turn_count == 1)
	_check("AC6 정지 시 월드=셀×타일 (32,16)", p3.position == Vector2(2 * TILE, 1 * TILE))
	# 한 칸 더(아래로): (2,1)→(2,2) 는 벽이므로 아래(2,2)는 막힘 → 대신 (2,1)→(3,1)? (3,1) 바닥
	p3.attempt_move(Vector2i(1, 0))                      # (2,1)→(3,1)
	_check("AC3 연속 이동 후 (3,1)", p3.cell == Vector2i(3, 1))
	_check("AC3 연속 이동 후 턴=2", tm3.turn_count == 2)
	_check("AC6 연속 이동 후에도 정렬 (48,16)", p3.position == Vector2(3 * TILE, 1 * TILE))

	# --- AC4 벽/경계 → 좌표 불변 + 턴 미소비 --------------------------------
	var tm4 = TurnManagerScript.new()
	var p4 = _make_player(tiles, Vector2i(1, 2), tm4)    # (1,2) 바닥, 오른쪽 (2,2)=벽
	var blocked_wall: bool = p4.attempt_move(Vector2i(1, 0))  # → (2,2) 벽
	_check("AC4 벽으로 이동 → false", not blocked_wall)
	_check("AC4 벽 → 좌표 불변 (1,2)", p4.cell == Vector2i(1, 2))
	_check("AC4 벽 → 턴 미소비 (0)", tm4.turn_count == 0)
	_check("AC6 차단 후에도 정렬 (16,32)", p4.position == Vector2(1 * TILE, 2 * TILE))

	# 맵 경계(out of bounds): 벽 없는 작은 격자에서 격자 밖으로
	var open_tiles: Array = [[FLOOR, FLOOR], [FLOOR, FLOOR]]
	var tm4b = TurnManagerScript.new()
	var p4b = _make_player(open_tiles, Vector2i(0, 0), tm4b)
	var oob: bool = p4b.attempt_move(Vector2i(0, -1))    # (0,-1) 경계 밖
	_check("AC4 경계 밖 이동 → false", not oob)
	_check("AC4 경계 밖 → 좌표 불변 (0,0)", p4b.cell == Vector2i(0, 0))
	_check("AC4 경계 밖 → 턴 미소비 (0)", tm4b.turn_count == 0)

	# --- AC5 대기 → 좌표 불변 + 턴 +1 --------------------------------------
	var tm5 = TurnManagerScript.new()
	var p5 = _make_player(tiles, Vector2i(1, 1), tm5)
	var before_cell: Vector2i = p5.cell
	var waited: bool = p5.wait()
	_check("AC5 대기 → true", waited)
	_check("AC5 대기 → 좌표 불변", p5.cell == before_cell)
	_check("AC5 대기 → 턴 카운터 1", tm5.turn_count == 1)
	_check("AC6 대기 후에도 정렬 (16,16)", p5.position == Vector2(1 * TILE, 1 * TILE))
	# 대기 후 이동 정상 누적
	p5.attempt_move(Vector2i(1, 0))
	_check("AC5 대기+이동 → 턴 2", tm5.turn_count == 2)

	# --- 적 페이즈 훅: enemy_phase 신호가 턴마다 방출되는가(Spec B 연결점) ----
	var tm6 = TurnManagerScript.new()
	var counter := StepCounter.new()
	tm6.enemy_phase.connect(counter.on_phase)
	tm6.consume_turn()
	tm6.consume_turn()
	_check("적 페이즈 훅(enemy_phase) 턴당 1회 방출", counter.count == 2)

	# --- step_completed code_event (se attach 연결점) -----------------------
	var tm7 = TurnManagerScript.new()
	var p7 = _make_player(tiles, Vector2i(1, 1), tm7)
	var steps := StepCounter.new()
	p7.step_completed.connect(steps.on_step_cell)
	p7.attempt_move(Vector2i(1, 0))
	_check("step_completed 1회 방출(발소리 SE 연결 지점)", steps.count == 1)

	if _fail == 0:
		print("ACCEPT_RESULT: PASS")
		quit(0)
	else:
		print("ACCEPT_RESULT: FAIL (%d건)" % _fail)
		quit(1)


## 신호 호출 횟수 카운터(람다 캡처 대신 명시 객체).
class StepCounter:
	extends RefCounted
	var count: int = 0
	func on_phase(_turn: int) -> void:
		count += 1
	func on_step_cell(_cell: Vector2i) -> void:
		count += 1
