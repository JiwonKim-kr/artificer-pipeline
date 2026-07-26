class_name Game
extends Node
## 런 상태 컨트롤러 + 시스템(상태창·성장·돌파·사망)의 배선 허브 — progression_and_clear(Spec C).
##
## lore 의 **시스템**(승탑자에게 부여되는 규칙 체계)을 노드로 구현한다: 현재 **층수**를
## 관리하고, Spec B 의 승탑자 `died` 를 받아 **게임오버**(입력 차단)로, 계단 위 **돌파
## 입력**을 다음 층으로, **재시작**을 새 런(층1·레벨1·HP최대·새 던전·진행 초기화)으로,
## **10층 돌파**를 1층계 완주(승리)로 전환한다. 성장·스킬은 순수 로직(Progression/Skill)에
## 위임하고, 이 노드는 그것들을 dungeon/combat/player/turn_manager 와 연결한다.
##
## **SE 앵커(code_event 지점)**: stats·skill 은 씬 노드가 아닌 순수 컴포넌트라 se attach
## 브리지를 붙일 수 없다. 그래서 이 노드(scenes/dungeon.tscn::Game)가 run-level 이벤트의
## 시그널 소유자다 — `on_level_up`/`on_floor_clear`/`on_game_over`/`on_skill_use` 가 각각
## `leveled_up`/`floor_cleared`/`run_ended`/`skill_triggered` 를 방출하고, se attach 가
## 그 시그널에 효과음을 연결한다(Spec B 의 combat/monster/player 와 동일 방식 — src/core 는
## SE 를 모른다). 성장·강타의 발생 자체는 stats.leveled_up·skill.skill_used 를 관측해 안다.
##
## 밸런스(승리 층수·시작 층 등)는 노멀 데이터(`NORMAL_RUN`) — 코드 상수 금지(CLAUDE.md).
## spec: docs/specs/progression_and_clear.md (game.gd 역할).

## --- SE code_event 앵커 시그널 (se attach 가 이 시그널들에 브리지를 붙인다) -----------
## 레벨업 순간(효과음: se:level_up). `on_level_up` 이 낸다.
signal leveled_up
## 층 돌파 순간(효과음: se:floor_clear). `on_floor_clear` 이 낸다.
signal floor_cleared
## 게임오버 순간(효과음: se:game_over). `on_game_over` 이 낸다.
signal run_ended
## 강타 발동(강화 공격 성립) 순간(효과음: se:skill_use). `on_skill_use` 가 낸다.
signal skill_triggered

## 노멀 난이도 런 데이터(밸런스의 단일 출처 — 코드 상수 금지).
##  · start_floor: 새 런 시작 층. · victory_floor: 이 층을 돌파하면 1층계 완주(승리).
const NORMAL_RUN: Dictionary = {
	"start_floor": 1,
	"victory_floor": 10,
}

## 재시작 시 기저 시드 파생 보폭(밸런스 아님) — 새 런마다 다른 던전 시퀀스를 결정적으로 준다.
const RESTART_SEED_STRIDE: int = 7_400_003

## 사용할 런 데이터. 기본은 노멀.
var data: Dictionary = NORMAL_RUN
## 현재 층수(관찰·상태창 표시용). start_floor 에서 시작.
var floor: int = 1
## 게임오버 상태(입력 차단, 게임오버 화면).
var game_over: bool = false
## 승리 상태(1층계 완주).
var won: bool = false

# --- 성장·스킬 (순수 로직, 런 내내 지속; 재시작 시 초기화) ---
var progression: Progression = null
var skill: Skill = null

# --- 씬 참조 (dungeon.tscn 구조 기준; 없으면 안전하게 no-op) ---
var _dungeon: Dungeon = null
var _player: Player = null
var _combat: Combat = null
var _status_window: Node = null
var _game_over_ui: Node = null

# --- 시드 상태 ---
var _initial_base_seed: int = 0
var _base_seed: int = 0
var _run_index: int = 0
var _base_captured: bool = false


func _ready() -> void:
	floor = int(data.get("start_floor", 1))
	progression = Progression.new()
	skill = Skill.new()

	_dungeon = get_parent() as Dungeon
	if _dungeon == null:
		return  # 씬 구조가 다르면(단독 테스트 등) 배선을 생략 — 크래시 없음.
	_player = _dungeon.get_player()
	_combat = _dungeon.get_combat()
	_status_window = get_node_or_null("../StatusWindow")
	_game_over_ui = get_node_or_null("../GameOver")

	# 지속 객체 신호는 한 번만 연결한다(던전 재생성과 무관하게 유지).
	if not _dungeon.rebuilt.is_connected(_on_dungeon_rebuilt):
		_dungeon.rebuilt.connect(_on_dungeon_rebuilt)
	if _player != null:
		_player.died.connect(_on_player_died)
		_player.confirm_pressed.connect(_on_confirm_pressed)
		_player.skill_requested.connect(_on_skill_requested)
	skill.skill_used.connect(_on_skill_used)
	if _game_over_ui != null and _game_over_ui.has_signal("restart_requested"):
		_game_over_ui.restart_requested.connect(restart)


## 한 층 build 가 끝날 때마다(최초·재생성) 새 turn_manager·상태창·combat 훅을 (재)배선한다.
func _on_dungeon_rebuilt() -> void:
	if _dungeon == null:
		return
	# 최초 build 의 시드를 기저로 캡처(floor 1 = 기저 시드).
	if not _base_captured:
		_initial_base_seed = _dungeon.dungeon_seed
		_base_seed = _initial_base_seed
		_base_captured = true

	# combat 훅(강타 강화 + 처치 EXP) — combat 은 지속 노드이므로 매번 주입해도 안전.
	if _combat != null:
		_combat.skill = skill
		_combat.progression = progression

	# 스킬 쿨다운을 턴 경계에 연결 — turn_manager 는 build 마다 새로 만들어지므로 재연결.
	var tm: TurnManager = _dungeon.turn_manager
	if tm != null and not tm.turn_advanced.is_connected(_on_turn_advanced):
		tm.turn_advanced.connect(_on_turn_advanced)

	# 레벨업 관측 — stats 는 재시작 시 새로 만들어지므로 재연결(중복 방지 가드).
	if _player != null and _player.stats != null:
		if not _player.stats.leveled_up.is_connected(_on_stats_leveled_up):
			_player.stats.leveled_up.connect(_on_stats_leveled_up)

	# 상태창에 소스 바인딩(폴링 갱신).
	if _status_window != null and _status_window.has_method("bind"):
		_status_window.bind(_player, self, skill, progression)


# ---------------------------------------------------------------------------
# 입력 의도 처리 (player 가 낸 시그널)
# ---------------------------------------------------------------------------
func _on_confirm_pressed() -> void:
	request_breakthrough()


func _on_skill_requested() -> void:
	# 강타 활성화(턴 미소비). 획득 전/쿨다운 중이면 activate 가 false 로 무효(수용 기준 11).
	if skill != null:
		skill.activate()


# ---------------------------------------------------------------------------
# 돌파 (등반) / 승리
# ---------------------------------------------------------------------------
## 승탑자가 계단 위에서 돌파를 시도한다. 계단이 아니면 아무 일도 하지 않는다(수용 기준 10).
## 계단이면: 층 돌파 SE 방출 → 10층이면 승리, 아니면 다음 층 생성(HP·성장 이월).
func request_breakthrough() -> void:
	if game_over or won or _dungeon == null:
		return
	if not _dungeon.player_on_stairs_up():
		return
	on_floor_clear()
	if floor >= victory_floor():
		_win()
	else:
		floor += 1
		_dungeon.regenerate(Dungeon.floor_seed(_base_seed, floor), true)  # carry_stats


func _win() -> void:
	won = true
	if _player != null:
		_player.input_enabled = false
	if _game_over_ui != null and _game_over_ui.has_method("show_victory"):
		_game_over_ui.show_victory(floor)


# ---------------------------------------------------------------------------
# 사망 / 게임오버 / 재시작
# ---------------------------------------------------------------------------
func _on_player_died() -> void:
	if game_over or won:
		return
	game_over = true
	if _player != null:
		_player.input_enabled = false  # 던전 입력 차단(수용 기준 4)
	if _game_over_ui != null and _game_over_ui.has_method("show_game_over"):
		_game_over_ui.show_game_over(floor)
	on_game_over()


## 새 런을 시작한다 — 층수 start_floor, 레벨 1·HP 최대·새 던전(진행 초기화, 수용 기준 5).
## 기저 시드를 파생해 이전 런과 다른(그러나 결정적인) 던전 시퀀스를 준다(로그라이크 새 던전).
func restart() -> void:
	_run_index += 1
	_base_seed = _initial_base_seed + _run_index * RESTART_SEED_STRIDE
	floor = int(data.get("start_floor", 1))
	game_over = false
	won = false
	if skill != null:
		skill.reset()
	if _game_over_ui != null and _game_over_ui.has_method("hide_screen"):
		_game_over_ui.hide_screen()
	if _dungeon != null:
		_dungeon.regenerate(Dungeon.floor_seed(_base_seed, floor), false)  # reset stats
	if _player != null:
		_player.input_enabled = true


# ---------------------------------------------------------------------------
# 성장·스킬 관측 → SE 앵커 중계
# ---------------------------------------------------------------------------
func _on_stats_leveled_up(new_level: int) -> void:
	# 레벨 도달 시 강타 획득 판정(데이터 조건). 획득 전에는 강타 무효(수용 기준 11).
	if skill != null:
		skill.check_acquire(new_level)
	on_level_up()


func _on_skill_used() -> void:
	on_skill_use()


func _on_turn_advanced(_turn: int) -> void:
	if skill != null:
		skill.tick_cooldown()  # 쿨다운 턴마다 1 감소(turn_manager 연동)


func victory_floor() -> int:
	return int(data.get("victory_floor", 10))


# ---------------------------------------------------------------------------
# SE code_event 지점 — 각 메서드는 정확히 1개의 선언 시그널을 방출(se attach 유도 규칙).
# ---------------------------------------------------------------------------
func on_level_up() -> void:
	leveled_up.emit()


func on_floor_clear() -> void:
	floor_cleared.emit()


func on_game_over() -> void:
	run_ended.emit()


func on_skill_use() -> void:
	skill_triggered.emit()
