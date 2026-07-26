extends SceneTree
## 승인 spec `progression_and_clear`(Spec C)의 수용 기준 1~12 를 헤드리스로 검증한다.
## (수용 기준 13 「던전+상태창 렌더」는 play_test --screenshot 스테이지가 담당 — 이 밖.)
##
## 두 단계로 나눈다:
##  · `_initialize` — 순수 로직(강타·성장·EXP 곡선·처치 EXP·시드 결정성)을 직접 검증하고,
##    통합용 씬(던전 전체·상태창)을 트리에 올려 둔다. (SceneTree _initialize 의 동기
##    컨텍스트에서는 add_child 로도 _ready 가 즉시 실행되지 않으므로 — 실게임/스크린샷
##    하니스처럼 프레임을 넘겨야 build·배선이 일어난다.)
##  · `_process` — 몇 프레임 뒤(_ready 완료) 런/사망/재시작/돌파/이월/승리/상태창을
##    검증한다. 이 시점의 메서드 호출(돌파·재시작·재생성)은 모두 동기로 처리된다.
##
## 실행: godot --headless --path <repo> --script res://pipeline/tests/acceptance_progression_clear.gd
## 결과: 마지막 줄 ACCEPT_RESULT: PASS | FAIL + 종료 코드.
## spec: docs/specs/progression_and_clear.md

const StatsScript := preload("res://src/core/stats.gd")
const RngScript := preload("res://src/core/rng.gd")
const ActorScript := preload("res://src/core/actor.gd")
const CombatScript := preload("res://src/core/combat.gd")
const MonsterScript := preload("res://src/core/monster.gd")
const TurnManagerScript := preload("res://src/core/turn_manager.gd")
const PlayerScript := preload("res://src/core/player.gd")
const GridScript := preload("res://src/core/grid.gd")
const GeneratorScript := preload("res://src/core/dungeon_generator.gd")
const ProgressionScript := preload("res://src/core/progression.gd")
const SkillScript := preload("res://src/core/skill.gd")
const GameScript := preload("res://src/core/game.gd")
const DungeonScript := preload("res://src/core/dungeon.gd")
const DungeonScene := preload("res://scenes/dungeon.tscn")
const StatusWindowScene := preload("res://scenes/ui/status_window.tscn")

const TILE: int = 16
const F_PLAYER := ActorScript.Faction.PLAYER
const F_ENEMY := ActorScript.Faction.ENEMY

var _fail: int = 0
var _to_free: Array[Node] = []

# 통합 단계 상태(프레임 게이팅).
var _frames: int = 0
var _ran_integration: bool = false
var _d6: Node = null      # 돌파/이월/계단아님
var _d4: Node = null      # 게임오버/재시작
var _d9: Node = null      # 10층 승리
var _sw: Node = null      # 상태창


func _check(label: String, cond: bool) -> void:
	if cond:
		print("[PASS] %s" % label)
	else:
		_fail += 1
		print("[FAIL] %s" % label)


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


func _tiles_sig(tiles: Array) -> String:
	var parts: PackedStringArray = []
	for row: Array in tiles:
		for v in row:
			parts.append(str(int(v)))
	return "|".join(parts)


# ===========================================================================
# 1단계: 순수 로직 (_initialize)
# ===========================================================================
func _initialize() -> void:
	print("== acceptance: progression_and_clear (수용 기준 1~12) ==")

	# --- AC11 강타 획득 조건 (획득 전 활성화 무효) ---------------------------
	var sk = SkillScript.new()
	_check("AC11 강타 초기: 미획득", not sk.acquired)
	_check("AC11 획득 전 can_activate=false", not sk.can_activate())
	_check("AC11 획득 전 activate() → false(무효)", sk.activate() == false and not sk.armed)
	_check("AC11 획득 레벨(2) 미만은 미획득", sk.check_acquire(1) == false and not sk.acquired)

	# --- AC12 강타 획득/강화/쿨다운 (순수 로직) ------------------------------
	_check("AC12 획득 레벨 도달 → 새로 획득(true)", sk.check_acquire(2) == true and sk.acquired)
	_check("AC12 획득 후 can_activate=true", sk.can_activate())
	_check("AC12 activate() → true, 준비 상태", sk.activate() == true and sk.armed)
	_check("AC12 준비 중 재활성화 무효(activate=false)", sk.activate() == false)
	var enh: int = sk.consume_for_attack(3)
	_check("AC12 강화 데미지 = round(3×2.0)=6", enh == 6)
	_check("AC12 강화 공격 후 준비 해제", not sk.armed)
	_check("AC12 강화 공격 성립 → 쿨다운 시작(=%d)" % sk.cooldown_max(), sk.cooldown == sk.cooldown_max())
	_check("AC12 쿨다운 중 재활성화 불가", not sk.can_activate())
	var cd_ok: bool = true
	for _i in sk.cooldown_max():
		if sk.can_activate():
			cd_ok = false
		sk.tick_cooldown()
	_check("AC12 쿨다운 경과 전엔 계속 재활성화 불가", cd_ok)
	_check("AC12 쿨다운 0 도달", sk.cooldown == 0)
	_check("AC12 쿨다운 경과 후 재활성화 가능", sk.can_activate() and sk.activate() == true)

	# --- AC2 EXP 곡선 · 다중 레벨업 연쇄 (순수 로직) -------------------------
	var prog = ProgressionScript.new()
	var st = StatsScript.from_data(PlayerScript.NORMAL_PLAYER)  # hp20 atk2-4 lv1 exp0
	var levels: int = prog.add_exp(st, 20)  # 임계치 5,10 통과, 잉여 5
	_check("AC2 다중 레벨업 연쇄: 20 EXP → 2레벨 상승", levels == 2 and st.level == 3)
	_check("AC2 잉여 EXP 이월(20-5-10=5)", st.exp == 5)
	_check("AC2 최대 HP 데이터대로 증가(20 + 2×5 = 30)", st.max_hp == 30)
	_check("AC2 공격력 데이터대로 증가(2-4 → 4-6)", st.attack_min == 4 and st.attack_max == 6)
	_check("AC2 레벨업 회복 정책: 최대치까지 회복", st.hp == st.max_hp)
	var st2 = StatsScript.from_data(PlayerScript.NORMAL_PLAYER)
	st2.hp = 3
	prog.add_exp(st2, 5)
	_check("AC2 회복: 손상 상태에서 레벨업 → HP 최대(%d)" % st2.max_hp, st2.hp == st2.max_hp and st2.level == 2)
	var st3 = StatsScript.from_data(PlayerScript.NORMAL_PLAYER)
	_check("AC2 임계치 미만 → 레벨 유지·EXP 누적", prog.add_exp(st3, 3) == 0 and st3.level == 1 and st3.exp == 3)

	# --- AC1 처치 → EXP 부여 (combat 연결) ----------------------------------
	var tm1 = TurnManagerScript.new()
	_to_free.append(tm1)
	var combat1 = CombatScript.new()
	combat1.rng = RngScript.new(1)
	combat1.progression = ProgressionScript.new()
	_to_free.append(combat1)
	var grid1 = _make_grid(_room_map(7, 5))
	var player1 = _make_player(grid1, Vector2i(1, 1), tm1, combat1)
	var rat1 = _make_monster("dungeon_rat", Vector2i(2, 1), tm1)
	rat1.stats.hp = 1
	player1.attempt_move(Vector2i(1, 0))  # 범프 → 처치
	_check("AC1 미궁 쥐 처치 → EXP += 보상(2) (=%d)" % player1.stats.exp,
		player1.stats.exp == 2 and rat1.is_dead())
	# 슬라임 보상(5)은 정확히 레벨1 임계치(5)라 처치 시 레벨업(2)으로 나타난다 → 보상 반영 확인.
	var tm1b = TurnManagerScript.new()
	_to_free.append(tm1b)
	var combat1b = CombatScript.new()
	combat1b.rng = RngScript.new(1)
	combat1b.progression = ProgressionScript.new()
	_to_free.append(combat1b)
	var grid1b = _make_grid(_room_map(7, 5))
	var player1b = _make_player(grid1b, Vector2i(1, 1), tm1b, combat1b)
	var slime1 = _make_monster("slime", Vector2i(2, 1), tm1b)
	slime1.stats.hp = 1
	player1b.attempt_move(Vector2i(1, 0))
	_check("AC1 슬라임 처치 → 보상(5) 부여(임계치 도달 → 레벨2)",
		player1b.stats.level == 2 and player1b.stats.exp == 0)

	# --- AC12(통합) 강타 강화가 범프 데미지에 반영 --------------------------
	var seed_e: int = 4242
	var c_base = CombatScript.new()
	c_base.rng = RngScript.new(seed_e)
	c_base.skill = SkillScript.new()  # 미획득/비준비 → 강화 없음
	_to_free.append(c_base)
	var atk_b = _make_actor(F_PLAYER, 100, 2, 4, Vector2i.ZERO)
	var def_b = _make_actor(F_ENEMY, 100000, 0, 0, Vector2i.ZERO)
	var base_dmg: int = c_base.resolve_bump(atk_b, def_b)
	var c_arm = CombatScript.new()
	c_arm.rng = RngScript.new(seed_e)
	var sk_arm = SkillScript.new()
	sk_arm.check_acquire(2)
	sk_arm.activate()
	c_arm.skill = sk_arm
	_to_free.append(c_arm)
	var atk_a = _make_actor(F_PLAYER, 100, 2, 4, Vector2i.ZERO)
	var def_a = _make_actor(F_ENEMY, 100000, 0, 0, Vector2i.ZERO)
	var enh_dmg: int = c_arm.resolve_bump(atk_a, def_a)
	_check("AC12 통합: 강화 공격 = base×2 (base=%d, enh=%d)" % [base_dmg, enh_dmg],
		enh_dmg == base_dmg * 2 and base_dmg >= 2)
	_check("AC12 통합: 강화 후 쿨다운 시작 + 준비 해제",
		sk_arm.cooldown == sk_arm.cooldown_max() and not sk_arm.armed)

	# --- AC8 같은 기저 시드 → 층별 던전 결정성 ------------------------------
	_check("AC8 floor_seed(base,1) == base", DungeonScript.floor_seed(1000, 1) == 1000)
	_check("AC8 floor_seed 층별 파생(2 != 3)",
		DungeonScript.floor_seed(1000, 2) != DungeonScript.floor_seed(1000, 3))
	var gen = GeneratorScript.new()
	var params: Dictionary = GeneratorScript.NORMAL_PARAMS
	var f2a: Dictionary = gen.generate(params, DungeonScript.floor_seed(555, 2))
	var f2b: Dictionary = gen.generate(params, DungeonScript.floor_seed(555, 2))
	var f3: Dictionary = gen.generate(params, DungeonScript.floor_seed(555, 3))
	var f2c: Dictionary = gen.generate(params, DungeonScript.floor_seed(999, 2))
	_check("AC8 같은 기저·같은 층 → 던전 완전 동일(결정성)", _tiles_sig(f2a.tiles) == _tiles_sig(f2b.tiles))
	_check("AC8 같은 기저·다른 층 → 던전 다름(층 시퀀스)", _tiles_sig(f2a.tiles) != _tiles_sig(f3.tiles))
	_check("AC8 다른 기저 → 던전 다름(기저 시드 반영)", _tiles_sig(f2a.tiles) != _tiles_sig(f2c.tiles))

	# --- 통합 씬을 트리에 올린다(_ready 는 다음 프레임들에서 실행) -----------
	_d6 = DungeonScene.instantiate(); _d6.dungeon_seed = 20260726; get_root().add_child(_d6)
	_d4 = DungeonScene.instantiate(); _d4.dungeon_seed = 31313; get_root().add_child(_d4)
	_d9 = DungeonScene.instantiate(); _d9.dungeon_seed = 90909; get_root().add_child(_d9)
	_sw = StatusWindowScene.instantiate(); get_root().add_child(_sw)


# ===========================================================================
# 2단계: 통합 (_process — _ready 완료 후)
# ===========================================================================
func _process(_delta: float) -> bool:
	if _ran_integration:
		return true
	_frames += 1
	if _frames < 4:
		return false  # _ready(build + game 배선) 가 끝나도록 몇 프레임 넘긴다
	_ran_integration = true
	_run_integration()
	_finish()
	return true


func _run_integration() -> void:
	# --- AC3 상태창 갱신 (값 변화 반영) -------------------------------------
	var up = PlayerScript.new()
	up.stats = StatsScript.from_data(PlayerScript.NORMAL_PLAYER)
	_to_free.append(up)
	var ug = GameScript.new()  # 트리 밖 스텁: floor/victory_floor 만 사용
	ug.floor = 2
	_to_free.append(ug)
	_sw.bind(up, ug, SkillScript.new(), ProgressionScript.new())
	_sw._refresh()
	_check("AC3 상태창 HP 표시", _sw._hp_label.text.contains("20") and _sw._hp_label.text.contains("HP"))
	_check("AC3 상태창 LV 표시", _sw._lv_label.text.contains("1"))
	_check("AC3 상태창 EXP 표시(현재/다음)", _sw._exp_label.text.contains("/"))
	_check("AC3 상태창 층수 표시(현재 2)", _sw._floor_label.text.contains("2"))
	up.stats.hp = 12
	_sw._refresh()
	_check("AC3 HP 변화(12) 즉시 반영", _sw._hp_label.text.contains("12"))
	up.stats.level = 3
	_sw._refresh()
	_check("AC3 LV 변화(3) 즉시 반영", _sw._lv_label.text.contains("3"))

	# --- AC6·AC7·AC10 돌파 / 이월 / 계단 아님 -------------------------------
	var g6 = _d6.get_node("Game")
	var p6 = _d6.get_node("Player")
	_check("AC6 사전: build 완료(던전 생성됨)", not _d6.result.is_empty())
	_check("AC6 사전: 최초 층 == 1", g6.floor == 1)
	# 계단 아닌 곳(시작=STAIRS_DOWN)에서 돌파 → 무효(AC10)
	p6.cell = _d6.result["start"]
	var floor_before10: int = g6.floor
	g6.request_breakthrough()
	_check("AC10 계단(STAIRS_UP) 아님에서 돌파 → 무변화", g6.floor == floor_before10)
	# 성장 상태를 부여해 이월 검증 준비
	p6.stats.level = 4; p6.stats.exp = 3
	p6.stats.max_hp = 40; p6.stats.hp = 17
	p6.stats.attack_min = 6; p6.stats.attack_max = 9
	p6.cell = _d6.result["exit"]
	_check("AC6 사전: 승탑자가 STAIRS_UP 위", _d6.player_on_stairs_up())
	g6.request_breakthrough()
	_check("AC6 돌파 → 층수 +1 (2)", g6.floor == 2)
	_check("AC6 돌파 → 시작 지점 배치", p6.cell == _d6.result["start"])
	_check("AC6 돌파 → 새 던전 생성(결과 갱신)", not _d6.result.is_empty())
	_check("AC7 돌파 후 레벨 이월(4)", p6.stats.level == 4)
	_check("AC7 돌파 후 EXP 이월(3)", p6.stats.exp == 3)
	_check("AC7 돌파 후 HP 이월(17, 무상 회복 없음)", p6.stats.hp == 17 and p6.stats.max_hp == 40)
	_check("AC7 돌파 후 공격력 이월(6-9)", p6.stats.attack_min == 6 and p6.stats.attack_max == 9)

	# --- AC4·AC5 게임오버(입력 차단) / 재시작(초기화) -----------------------
	var g4 = _d4.get_node("Game")
	var p4 = _d4.get_node("Player")
	p4.stats.level = 5
	p4.stats.hp = 0
	p4.on_death()  # died → game._on_player_died
	_check("AC4 HP 0 → 게임오버 상태 전환", g4.game_over == true)
	_check("AC4 게임오버 → 던전 입력 차단(input_enabled=false)", p4.input_enabled == false)
	var cell_go: Vector2i = p4.cell
	p4._poll_input()  # 입력 차단 → 좌표 불변
	_check("AC4 게임오버 후 이동 입력이 승탑자를 움직이지 않음", p4.cell == cell_go)
	g4.restart()
	_check("AC5 재시작 → 층수 1", g4.floor == 1)
	_check("AC5 재시작 → 게임오버 해제", g4.game_over == false)
	_check("AC5 재시작 → 레벨 1", p4.stats.level == 1)
	_check("AC5 재시작 → HP 최대·EXP 0(진행 초기화)", p4.stats.hp == p4.stats.max_hp and p4.stats.exp == 0)
	_check("AC5 재시작 → 입력 재개", p4.input_enabled == true)
	_check("AC5 재시작 → 새 던전(시작 지점 배치)", p4.cell == _d4.result["start"])

	# --- AC9 10층 돌파 → 승리 -----------------------------------------------
	var g9 = _d9.get_node("Game")
	var p9 = _d9.get_node("Player")
	var vf: int = g9.victory_floor()
	var breaks: int = 0
	while not g9.won and breaks < vf + 3:
		p9.cell = _d9.result["exit"]
		g9.request_breakthrough()
		breaks += 1
	_check("AC9 10층 돌파 → 승리 상태", g9.won == true)
	_check("AC9 승리 시 층수 == 승리 조건(%d)" % vf, g9.floor == vf)
	_check("AC9 정확히 %d회 돌파로 완주" % vf, breaks == vf)


func _finish() -> void:
	if is_instance_valid(_d6): _d6.free()
	if is_instance_valid(_d4): _d4.free()
	if is_instance_valid(_d9): _d9.free()
	if is_instance_valid(_sw): _sw.free()
	for n in _to_free:
		if is_instance_valid(n):
			n.free()
	if _fail == 0:
		print("ACCEPT_RESULT: PASS")
		quit(0)
	else:
		print("ACCEPT_RESULT: FAIL (%d건)" % _fail)
		quit(1)
