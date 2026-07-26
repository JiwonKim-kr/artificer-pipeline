extends CanvasLayer
## 게임오버 · 승리 화면 — progression_and_clear(Spec C, §3·§4).
##
## 승탑자 사망 시 **게임오버**를, 10층 돌파(1층계 완주) 시 **승리**를 텍스트로 덮어 표시하고
## **재시작 입력**(확인 키)을 받아 `restart_requested` 를 방출한다(게임 컨트롤러가 새 런을
## 시작). 평소엔 숨겨져 있어 던전을 가리지 않는다. 아트 에셋 불필요(무료).
##
## UI 코드는 src/ui/(AI 자유 영역) — 게임 로직·데이터를 바꾸지 않는다.
## spec: docs/specs/progression_and_clear.md (game_over 역할).

## 재시작(확인) 입력 시 방출. game.gd 가 받아 새 런을 시작한다.
signal restart_requested

## 재시작 입력 액션(project.godot [input]). 던전 입력은 게임오버 시 차단되므로 충돌 없음.
const CONFIRM_ACTION: String = "confirm"

@onready var _root: Control = $Root
@onready var _title: Label = $Root/Center/VBox/TitleLabel
@onready var _hint: Label = $Root/Center/VBox/HintLabel


func _ready() -> void:
	hide_screen()


## 게임오버 화면을 표시한다(도달 층수 포함).
func show_game_over(reached_floor: int) -> void:
	_title.text = "게임 오버"
	_title.add_theme_color_override("font_color", Color(0.93, 0.35, 0.35, 1))
	_hint.text = "%d층에서 쓰러졌다.\n확인 키로 재시작" % reached_floor
	_root.visible = true


## 승리 화면(1층계 완주)을 표시한다.
func show_victory(cleared_floor: int) -> void:
	_title.text = "1층계 돌파!"
	_title.add_theme_color_override("font_color", Color(0.6, 0.92, 0.86, 1))
	_hint.text = "지하 미궁 %d층 완주.\n확인 키로 재시작" % cleared_floor
	_root.visible = true


## 화면을 숨긴다(재시작·초기 상태).
func hide_screen() -> void:
	if _root != null:
		_root.visible = false


func _process(_delta: float) -> void:
	if _root == null or not _root.visible:
		return
	if InputMap.has_action(CONFIRM_ACTION) and Input.is_action_just_pressed(CONFIRM_ACTION):
		restart_requested.emit()
