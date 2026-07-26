extends SceneTree
## 승인 spec `monsters_and_combat`(Spec B)의 수용 기준 1~9 를 헤드리스로 검증한다.
## (수용 기준 10 「메인 씬 렌더」는 play_test --screenshot 스테이지가 담당 — 이 밖.)
##
## 전투·AI·사망 신호·결정성은 순수 로직/노드로 직접 인스턴스화해 검증한다. 핵심
## 스크립트를 preload 로 직접 만들어 씬/전역 클래스 캐시에 덜 의존하게 한다.
##
## 실행: godot --headless --path <repo> --script res://pipeline/tests/acceptance_monsters_combat.gd
## 결과: 마지막 줄 ACCEPT_RESULT: PASS | FAIL + 종료 코드.
## spec: docs/specs/monsters_and_combat.md

const StatsScript := preload("res://src/core/stats.gd")
const RngScript := preload("res://src/core/rng.gd")
const ActorScript := preload("res://src/core/actor.gd")
const CombatScript := preload("res://src/core/combat.gd")
const MonsterAiScript := preload("res://src/core/monster_ai.gd")
const MonsterScript := preload("res://src/core/monster.gd")
const TurnManagerScript := preload("res://src/core/turn_manager.gd")
const PlayerScript := preload("res://src/core/player.gd")
const GridScript := preload("res://src/core/grid.gd")
const GeneratorScript := preload("res://src/core/dungeon_generator.gd")
const DungeonScene := preload("res://scenes/dungeon.tscn")

const TILE: int = 16
const F_PLAYER := ActorScript.Faction.PLAYER
const F_ENEMY := ActorScript.Faction.ENEMY

var _fail: int = 0
var _to_free: Array[Node] = []


func _check(label: String, cond: bool) -> void:
	if cond:
		print("[PASS] %s" % label)
	else:
		_fail += 1
		print("[FAIL] %s" % label)


# --- 신호 카운터 --------------------------------------------------------------
class Counter:
	extends RefCounted
	var count: int = 0
	func tick() -> void:
		count += 1


# --- 헬퍼 --------------------------------------------------------------------
func _room_map(w: int, h: int) -> Array:
	var wall := GeneratorScript.Tile.WALL
	var floor_tile := GeneratorScript.Tile.FLOOR
	var t: Array = []
	for y in h:
		var row: Array[int] = []
		for x in w:
			if x == 0 or y == 0 or x == w - 1 or y == h - 1:
				row.append(wall)
			else:
				row.append(floor_tile)
		t.append(row)
	return t


func _make_grid(tiles: Array) -> Object:
	var g = GridScript.new(TILE, 0, 0)
	g.configure_tiles(tiles, GeneratorScript.WALKABLE_TILES)
	return g


func _make_actor(faction: int, hp: int, amin: int, amax: int, cell: Vector2i) -> Object:
	var a = ActorScript.new()
	a.faction = faction
	a.stats = StatsScript.new(hp, amin, amax)
	a.cell = cell
	_to_free.append(a)
	return a


func _make_player(grid: Object, start: Vector2i, tm: Object, combat: Object) -> Object:
	var p = PlayerScript.new()
	p.move_duration = 0.0
	p.configure(grid, start, tm, combat)
	tm.set_occupant(p.cell, p)
	_to_free.append(p)
	return p


func _make_monster(type_id: String, cell: Vector2i, tm: Object) -> Object:
	var m = MonsterScript.new()
	m.configure(type_id, cell, TILE)
	tm.register_monster(m)
	_to_free.append(m)
	return m


# --- AC8 결정성: 데미지 시퀀스 -------------------------------------------------
func _damage_sequence(seed_value: int, n: int) -> Array:
	var attacker = _make_actor(F_PLAYER, 100, 2, 4, Vector2i.ZERO)
	var combat = CombatScript.new()
	combat.rng = RngScript.new(seed_value)
	_to_free.append(combat)
	var seq: Array = []
	for _i in n:
		var defender = _make_actor(F_ENEMY, 100000, 0, 0, Vector2i.ZERO)  # 죽지 않게 큰 HP
		seq.append(combat.resolve_bump(attacker, defender))
	return seq


func _in_range(seq: Array, lo: int, hi: int) -> bool:
	for v in seq:
		if int(v) < lo or int(v) > hi:
			return false
	return true


# --- AC3 결정성: 적 페이즈 총 데미지 -------------------------------------------
func _enemy_phase_damage(seed_value: int) -> int:
	var grid = _make_grid(_room_map(7, 5))
	var tm = TurnManagerScript.new()
	_to_free.append(tm)
	var combat = CombatScript.new()
	combat.rng = RngScript.new(seed_value)
	_to_free.append(combat)
	var player = _make_player(grid, Vector2i(3, 2), tm, combat)
	tm.configure_combat(player, grid, combat)
	for c in [Vector2i(2, 2), Vector2i(4, 2), Vector2i(3, 1)]:
		_make_monster("dungeon_rat", c, tm)
	var before: int = player.stats.hp
	tm.consume_turn()
	return before - player.stats.hp


# --- AC7 스폰 시그니처(전체 던전 씬 인스턴스화) --------------------------------
func _spawn_signature(seed_value: int) -> Array:
	var inst = DungeonScene.instantiate()
	inst.dungeon_seed = seed_value
	# _ready 는 SceneTree _initialize 의 동기 컨텍스트에서 즉시 실행되지 않으므로
	# (실게임·스크린샷 하니스는 프레임을 넘겨 _ready 실행) build 를 직접 호출한다.
	# build 는 자식 노드를 방어적으로 해석하므로 트리에 넣지 않아도 안전하다.
	inst.build()
	var sig: Array = []
	var monsters_root: Node = inst.get_node("Monsters")
	for m in monsters_root.get_children():
		sig.append([m.cell, m.type_id])
	inst.free()
	return sig


func _sig_equal(a: Array, b: Array) -> bool:
	if a.size() != b.size():
		return false
	for i in a.size():
		if a[i][0] != b[i][0] or a[i][1] != b[i][1]:
			return false
	return true


func _initialize() -> void:
	print("== acceptance: monsters_and_combat (수용 기준 1~9) ==")

	# --- AC1 범프 공격: 이동 대신 공격 + 데미지 [min,max] + 1턴 -----------------
	var grid1 = _make_grid(_room_map(7, 5))
	var tm1 = TurnManagerScript.new()
	_to_free.append(tm1)
	var combat1 = CombatScript.new()
	combat1.rng = RngScript.new(7)
	_to_free.append(combat1)
	var player1 = _make_player(grid1, Vector2i(1, 1), tm1, combat1)
	tm1.configure_combat(player1, grid1, combat1)
	var rat1 = _make_monster("dungeon_rat", Vector2i(2, 1), tm1)
	var rat_hp_before: int = rat1.stats.hp
	var bumped: bool = player1.attempt_move(Vector2i(1, 0))   # 오른쪽 = rat 칸 → 범프
	_check("AC1 범프 → 행동 성공(true)", bumped)
	_check("AC1 범프 시 승탑자는 이동하지 않음(좌표 불변)", player1.cell == Vector2i(1, 1))
	_check("AC1 범프 → 1턴 소비", tm1.turn_count == 1)
	var rat_delta: int = rat_hp_before - rat1.stats.hp
	# 승탑자 공격력 [2,4] (NORMAL_PLAYER)
	_check("AC1 몬스터 HP가 [2,4] 범위 값만큼 감소 (delta=%d)" % rat_delta,
		rat_delta >= 2 and rat_delta <= 4)

	# --- AC2 처치 → 제거 + walkable 복귀 --------------------------------------
	var grid2 = _make_grid(_room_map(7, 5))
	var tm2 = TurnManagerScript.new()
	_to_free.append(tm2)
	var combat2 = CombatScript.new()
	combat2.rng = RngScript.new(1)
	_to_free.append(combat2)
	var killer = _make_actor(F_PLAYER, 100, 99, 99, Vector2i(1, 1))
	var rat2 = _make_monster("dungeon_rat", Vector2i(2, 1), tm2)
	_check("AC2 사전: 몬스터 점유 등록됨", tm2.occupant_at(Vector2i(2, 1)) == rat2)
	combat2.resolve_bump(killer, rat2)     # 치명타
	_check("AC2 처치 → 사망 판정", rat2.is_dead())
	_check("AC2 처치 → 레지스트리 제거(live=0)", tm2.live_monster_count() == 0)
	_check("AC2 처치 → 점유 해제(칸 비었음)", tm2.occupant_at(Vector2i(2, 1)) == null)
	_check("AC2 처치 → 그 칸 walkable/free 복귀", tm2.is_cell_free(Vector2i(2, 1), grid2))

	# --- AC3 적 페이즈: 살아있는 몬스터 전원 1회 행동 + AC5 승탑자 피격 ---------
	var d3a: int = _enemy_phase_damage(5)
	_check("AC3 적 페이즈: 인접 몬스터 3마리 각 1회 공격 → 승탑자 HP 총 [3,6] 감소 (delta=%d)" % d3a,
		d3a >= 3 and d3a <= 6)
	_check("AC5 몬스터 인접 공격 → 승탑자 HP가 [몬스터 min,max] 범위만큼 감소(합 [3,6])",
		d3a >= 3 and d3a <= 6)
	var d3b: int = _enemy_phase_damage(5)
	_check("AC3/8 적 페이즈 결정성(같은 시드 → 같은 총 데미지: %d==%d)" % [d3a, d3b], d3a == d3b)

	# --- AC4 그리디 접근(순수 함수) + 실제 몬스터 이동 ------------------------
	var rs_line = MonsterAiScript.ranked_steps(Vector2i(1, 1), Vector2i(5, 1))
	_check("AC4 그리디 주축(x) 후보 1개", rs_line.size() == 1 and rs_line[0] == Vector2i(1, 0))
	var rs_diag = MonsterAiScript.ranked_steps(Vector2i(1, 1), Vector2i(5, 3))
	_check("AC4 대각 대상: 주축 x → 보조 y 순", rs_diag.size() == 2
		and rs_diag[0] == Vector2i(1, 0) and rs_diag[1] == Vector2i(0, 1))
	var all_free := func(_c: Vector2i) -> bool: return true
	_check("AC4 choose_move 주축 선택",
		MonsterAiScript.choose_move(Vector2i(1, 1), Vector2i(5, 1), all_free) == Vector2i(1, 0))
	var block_23 := func(c: Vector2i) -> bool: return c != Vector2i(2, 1)
	_check("AC4 주축 막힘 + 보조 없음(직선) → 대기(ZERO)",
		MonsterAiScript.choose_move(Vector2i(1, 1), Vector2i(5, 1), block_23) == Vector2i.ZERO)
	_check("AC4 주축 막힘 → 보조축 우회",
		MonsterAiScript.choose_move(Vector2i(1, 1), Vector2i(5, 3), block_23) == Vector2i(0, 1))

	# 실제 몬스터: aggro 안 → 1칸 접근 / aggro 밖 → 제자리
	var grid4 = _make_grid(_room_map(9, 5))
	var tm4 = TurnManagerScript.new()
	_to_free.append(tm4)
	var combat4 = CombatScript.new()
	combat4.rng = RngScript.new(3)
	_to_free.append(combat4)
	var player4 = _make_player(grid4, Vector2i(6, 2), tm4, combat4)
	var rat4 = _make_monster("dungeon_rat", Vector2i(1, 2), tm4)  # chebyshev 5 ≤ aggro 6
	rat4.act(tm4, player4, grid4, combat4)
	_check("AC4 aggro 안 미궁 쥐 → 승탑자 방향 1칸 접근 (2,2)", rat4.cell == Vector2i(2, 2))
	_check("AC4 접근 후 점유 이동 반영",
		tm4.occupant_at(Vector2i(2, 2)) == rat4 and not tm4.is_occupied(Vector2i(1, 2)))

	var grid4b = _make_grid(_room_map(9, 5))
	var tm4b = TurnManagerScript.new()
	_to_free.append(tm4b)
	var combat4b = CombatScript.new()
	combat4b.rng = RngScript.new(3)
	_to_free.append(combat4b)
	var player4b = _make_player(grid4b, Vector2i(7, 2), tm4b, combat4b)
	var slime4 = _make_monster("slime", Vector2i(1, 2), tm4b)  # chebyshev 6 > aggro 4
	slime4.act(tm4b, player4b, grid4b, combat4b)
	_check("AC4 aggro 밖 슬라임 → 접근 안 함(제자리)", slime4.cell == Vector2i(1, 2))

	# 슬라임 격턴 이동(느림): 2번의 act 마다 1칸
	var gridS = _make_grid(_room_map(9, 5))
	var tmS = TurnManagerScript.new()
	_to_free.append(tmS)
	var combatS = CombatScript.new()
	combatS.rng = RngScript.new(9)
	_to_free.append(combatS)
	var playerS = _make_player(gridS, Vector2i(5, 2), tmS, combatS)  # chebyshev 4 ≤ aggro 4
	var slimeS = _make_monster("slime", Vector2i(1, 2), tmS)
	slimeS.act(tmS, playerS, gridS, combatS)
	_check("슬라임 격턴: 1번째 act 대기(이동 없음)", slimeS.cell == Vector2i(1, 2))
	slimeS.act(tmS, playerS, gridS, combatS)
	_check("슬라임 격턴: 2번째 act 에 1칸 이동 (2,2)", slimeS.cell == Vector2i(2, 2))
	slimeS.act(tmS, playerS, gridS, combatS)
	_check("슬라임 격턴: 3번째 act 다시 대기", slimeS.cell == Vector2i(2, 2))

	# --- AC6 승탑자 사망 → died 1회 -------------------------------------------
	var grid6 = _make_grid(_room_map(7, 5))
	var tm6 = TurnManagerScript.new()
	_to_free.append(tm6)
	var combat6 = CombatScript.new()
	combat6.rng = RngScript.new(2)
	_to_free.append(combat6)
	var player6 = _make_player(grid6, Vector2i(3, 2), tm6, combat6)
	var death_counter := Counter.new()
	player6.died.connect(death_counter.tick)
	var big6 = _make_actor(F_ENEMY, 100, 100, 100, Vector2i(2, 2))
	combat6.resolve_bump(big6, player6)   # 치명타
	_check("AC6 승탑자 HP 0 이하 → died 신호 1회 방출", death_counter.count == 1)
	_check("AC6 승탑자 사망 판정", player6.is_dead())

	# --- AC8 데미지 범위 + 시드 재현성 ----------------------------------------
	var seqA: Array = _damage_sequence(11, 24)
	var seqB: Array = _damage_sequence(11, 24)
	var seqC: Array = _damage_sequence(12, 24)
	_check("AC8 데미지가 항상 [2,4] 범위 안", _in_range(seqA, 2, 4))
	_check("AC8 같은 시드·같은 순서 → 동일 데미지 시퀀스(재현성)", seqA == seqB)
	_check("AC8 다른 시드 → 데미지 시퀀스 다름(시드 반영)", seqA != seqC)

	# --- AC7 스폰 결정성(같은 시드 → 동일 배치) --------------------------------
	var sigA: Array = _spawn_signature(1337)
	var sigB: Array = _spawn_signature(1337)
	var sigC: Array = _spawn_signature(4242)
	_check("AC7 스폰이 실제로 일어남(몬스터 ≥ 1)", sigA.size() >= 1)
	_check("AC7 같은 시드 → 스폰(수·위치·종류) 완전 동일", _sig_equal(sigA, sigB))
	_check("AC7 다른 시드 → 스폰 배치 다름(시드 반영)", not _sig_equal(sigA, sigC))

	# --- AC9 개체 겹침 없음(다중 턴) ------------------------------------------
	var grid9 = _make_grid(_room_map(9, 7))
	var tm9 = TurnManagerScript.new()
	_to_free.append(tm9)
	var combat9 = CombatScript.new()
	combat9.rng = RngScript.new(4)
	_to_free.append(combat9)
	var player9 = _make_player(grid9, Vector2i(4, 3), tm9, combat9)
	tm9.configure_combat(player9, grid9, combat9)
	for c in [Vector2i(1, 1), Vector2i(7, 1), Vector2i(1, 5), Vector2i(7, 5), Vector2i(1, 3)]:
		_make_monster("dungeon_rat", c, tm9)
	var overlap_ok: bool = true
	for _turn in 6:
		tm9.consume_turn()   # 승탑자 정지, 적 페이즈에서 몬스터 접근/공격
		var seen: Dictionary = {}
		seen[player9.cell] = true
		for m in tm9.monsters():
			if not is_instance_valid(m) or m.is_dead():
				continue
			if seen.has(m.cell):
				overlap_ok = false
			seen[m.cell] = true
	_check("AC9 다중 턴 동안 개체 겹침 없음(승탑자·몬스터 모두 고유 셀)", overlap_ok)

	# --- 정리 ---------------------------------------------------------------
	for n in _to_free:
		if is_instance_valid(n):
			n.free()

	if _fail == 0:
		print("ACCEPT_RESULT: PASS")
		quit(0)
	else:
		print("ACCEPT_RESULT: FAIL (%d건)" % _fail)
		quit(1)
