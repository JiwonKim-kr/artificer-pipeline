extends CanvasLayer
## 상태창 HUD — 시스템이 승탑자에게 보여주는 인터페이스(progression_and_clear, Spec C, §1).
##
## 화면 고정(CanvasLayer)으로 **HP · 레벨(LV) · 경험치(EXP 현재/다음) · 현재 층수 · 강타
## 상태(획득/준비/쿨다운)**를 텍스트/바로 표시한다. 아트 에셋 불필요(무료). core 스탯을
## **읽기만** 하며, 매 프레임 폴링으로 값 변화(피격·레벨업·돌파)를 즉시 반영한다(수용 기준 3).
##
## UI 코드는 src/ui/(AI 자유 영역) — 게임 로직·데이터를 바꾸지 않는다. 소스가 바인딩되기
## 전(부팅 직후)에는 대기 문구를 보여 크래시 없이 동작한다.
## spec: docs/specs/progression_and_clear.md (status_window 역할).

var _player: Player = null
var _game: Node = null            # Game (런 상태 — 층수)
var _skill: Skill = null
var _progression: Progression = null

@onready var _hp_label: Label = $Panel/Margin/VBox/HpLabel
@onready var _lv_label: Label = $Panel/Margin/VBox/LvLabel
@onready var _exp_label: Label = $Panel/Margin/VBox/ExpLabel
@onready var _floor_label: Label = $Panel/Margin/VBox/FloorLabel
@onready var _skill_label: Label = $Panel/Margin/VBox/SkillLabel


## 게임 컨트롤러가 데이터 소스를 주입한다(읽기 전용 참조). build/재생성마다 호출돼도 안전.
func bind(player: Player, game: Node, skill: Skill, progression: Progression) -> void:
	_player = player
	_game = game
	_skill = skill
	_progression = progression


func _process(_delta: float) -> void:
	_refresh()


func _refresh() -> void:
	if _player == null or _player.stats == null:
		if _hp_label != null:
			_hp_label.text = "시스템 연결 중…"
		return
	var s: Stats = _player.stats
	_hp_label.text = "HP  %d / %d" % [maxi(0, s.hp), s.max_hp]
	_lv_label.text = "LV  %d   ATK %d-%d" % [s.level, s.attack_min, s.attack_max]
	if _progression != null:
		_exp_label.text = "EXP  %d / %d" % [s.exp, _progression.exp_to_next(s.level)]
	else:
		_exp_label.text = "EXP  %d" % s.exp
	if _game != null:
		_floor_label.text = "층  %d / %d" % [int(_game.floor), int(_game.victory_floor())]
	else:
		_floor_label.text = "층  -"
	_skill_label.text = "강타: %s" % _skill_status_text()


func _skill_status_text() -> String:
	if _skill == null or not _skill.acquired:
		return "미획득"
	if _skill.armed:
		return "준비"
	if _skill.cooldown > 0:
		return "쿨다운 %d" % _skill.cooldown
	return "사용 가능"
