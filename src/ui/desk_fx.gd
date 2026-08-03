@tool
extends Control
## 데스크 hover 시각 효과 — 에디터에서 직접 튜닝하는 오버레이.
##   ScreenGlow : 모니터 화면 발광(Add 블렌드 앰버)
##   DrawerShadow : 서랍 살짝 열림 그림자
## 실행 시 main.gd 가 이 씬을 인스턴스하고, 핫스팟 hover 에 따라 set_screen_on()/set_drawer_open() 호출.
##
## ▶ 에디터에서 튜닝하는 법:
##   1) scenes/desk_fx.tscn 을 더블클릭해 연다(배경 desk_bg 가 참고로 보임).
##   2) 인스펙터에서 아래 Preview 를 켜면 효과가 즉시 미리보기됨.
##   3) ScreenGlow / DrawerShadow 노드를 2D 뷰에서 드래그해 위치·크기 조절,
##      또는 아래 색/강도 값을 슬라이더로 조절. 저장하면 게임에 반영.

@export_group("Preview (에디터 전용)")
## 켜면 에디터에서 화면 발광을 미리 본다(실행에는 영향 없음).
@export var preview_screen_on := false:
	set(v):
		preview_screen_on = v
		_apply()
## 켜면 에디터에서 서랍 그림자를 미리 본다.
@export var preview_drawer_open := false:
	set(v):
		preview_drawer_open = v
		_apply()

@export_group("화면 발광")
@export var screen_glow_color := Color(1.0, 0.72, 0.40):
	set(v):
		screen_glow_color = v
		_apply()
## 발광 강도(= 오버레이 불투명도). 0=꺼짐, 1=최대.
@export_range(0.0, 1.0) var screen_glow_energy := 0.6:
	set(v):
		screen_glow_energy = v
		_apply()

@export_group("서랍 그림자")
@export_range(0.0, 1.0) var drawer_shadow_alpha := 0.5:
	set(v):
		drawer_shadow_alpha = v
		_apply()

var _screen_on := false
var _drawer_on := false

func _ready() -> void:
	if not Engine.is_editor_hint():
		# 런타임에는 에디터용 배경 참조를 숨긴다(실게임 desk_bg 가 이미 깔려 있음).
		var bg := get_node_or_null("EditorBg")
		if bg != null:
			bg.visible = false
	_apply()

## main.gd 가 hover 에 따라 호출.
func set_screen_on(on: bool) -> void:
	_screen_on = on
	_apply()

func set_drawer_open(on: bool) -> void:
	_drawer_on = on
	_apply()

func _apply() -> void:
	var glow := get_node_or_null("ScreenGlow")
	if glow != null:
		var on_s := _screen_on or (Engine.is_editor_hint() and preview_screen_on)
		glow.color = screen_glow_color
		glow.self_modulate = Color(1, 1, 1, screen_glow_energy if on_s else 0.0)
	var drawer := get_node_or_null("DrawerShadow")
	if drawer != null:
		var on_d := _drawer_on or (Engine.is_editor_hint() and preview_drawer_open)
		drawer.self_modulate = Color(1, 1, 1, drawer_shadow_alpha if on_d else 0.0)
