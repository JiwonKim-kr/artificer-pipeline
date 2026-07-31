extends Control
## 「태엽 인간」 1턴 수직 슬라이스 UI 컨트롤러.
## 데스크(정적 배경) → 모니터 클릭 → 전체화면 CRT OS UI(정보원·원고작성·댓글·게이지).
## 원고 작성 = 문장 블록 취사(넣을지 말지). 유리/불리는 노출하지 않음(플레이어 판단).
## 로직은 TurnManager(코어)에 위임. 마우스/클릭 전용. spec: docs/specs/turn_loop_vertical_slice.md

const DESK_BG := "res://assets/art/ui/main/PLACEHOLDER_desk_bg.png"
const GAUGE_TEX := "res://assets/art/ui/gauge/PLACEHOLDER_opinion_needle.png"
const CRT_SHADER := "res://src/ui/shaders/crt_screen.gdshader"

var _tm: TurnManager
var _desk: Control
var _screen: Control
var _block_checks: Array = []  # [{cb: CheckBox, id: String}]
var _comments_box: VBoxContainer
var _needle: Line2D
var _status_label: Label

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_tm = TurnManager.new(1)
	_build_desk()
	_build_screen()
	_screen.visible = false

func _res(path: String) -> Resource:
	return load(path) if ResourceLoader.exists(path) else null

# ---------- 데스크 상태 ----------
func _build_desk() -> void:
	_desk = Control.new()
	_desk.name = "DeskView"
	_desk.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_desk)

	var bg := TextureRect.new()
	bg.name = "Background"
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_COVERED
	var tex := _res(DESK_BG)
	if tex != null:
		bg.texture = tex
	else:
		var cr := ColorRect.new()
		cr.color = Color(0.14, 0.10, 0.07)
		cr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		_desk.add_child(cr)
	_desk.add_child(bg)

	var btn := Button.new()
	btn.name = "MonitorButton"
	btn.text = "모니터 켜기"
	btn.custom_minimum_size = Vector2(220, 64)
	btn.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	btn.pressed.connect(_enter_screen)
	_desk.add_child(btn)

func _enter_screen() -> void:
	_desk.visible = false
	_screen.visible = true

# ---------- 스크린 상태 (CRT OS) ----------
func _build_screen() -> void:
	_screen = Control.new()
	_screen.name = "ScreenState"
	_screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_screen)

	var scr_bg := ColorRect.new()
	scr_bg.color = Color(0.03, 0.05, 0.03)
	scr_bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_screen.add_child(scr_bg)

	var os := Control.new()
	os.name = "ScreenOS"
	os.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_screen.add_child(os)
	os.add_child(_make_informant(Vector2(20, 20), Vector2(340, 320)))
	os.add_child(_make_editor(Vector2(376, 20), Vector2(430, 540)))
	os.add_child(_make_comments(Vector2(822, 20), Vector2(310, 400)))
	os.add_child(_make_gauge(Vector2(20, 356), Vector2(340, 272)))

	var bbc := BackBufferCopy.new()
	bbc.copy_mode = BackBufferCopy.COPY_MODE_VIEWPORT
	_screen.add_child(bbc)

	var crt := ColorRect.new()
	crt.name = "CrtOverlay"
	crt.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	crt.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sh := _res(CRT_SHADER)
	if sh != null:
		var mat := ShaderMaterial.new()
		mat.shader = sh
		crt.material = mat
	_screen.add_child(crt)

func _window(pos: Vector2, size: Vector2, title: String) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = pos
	panel.custom_minimum_size = size
	panel.size = size
	var vb := VBoxContainer.new()
	panel.add_child(vb)
	var t := Label.new()
	t.text = "▍ " + title
	t.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	vb.add_child(t)
	vb.add_child(HSeparator.new())
	panel.set_meta("body", vb)
	return panel

func _body_of(panel: Node) -> VBoxContainer:
	return panel.get_meta("body") as VBoxContainer

# 정보원: 입수 정보(전부 진실). 유리/불리 태그는 노출하지 않음 — 판단은 플레이어 몫.
func _make_informant(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "정보원 — 입수 정보")
	var vb := _body_of(panel)
	var facts: Dictionary = _tm.content.get("facts", {})
	for fid in facts:
		var f: Dictionary = facts[fid]
		var head := Label.new()
		head.text = "· %s" % str(f.get("title", ""))
		head.add_theme_color_override("font_color", Color(0.6, 0.9, 0.7))
		vb.add_child(head)
		for frag in f.get("fragments", []):
			var l := Label.new()
			l.text = "   %s" % str(frag.get("text", ""))
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			vb.add_child(l)
	return panel

# 원고 작성: 각 문장 블록을 넣을지 말지 토글. 필수 없음. 전부 빼면 미보도.
func _make_editor(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "원고 작성 — 실을 문장 선택")
	var vb := _body_of(panel)
	var hint := Label.new()
	hint.text = "실을 문장에 체크. 무엇을 넣고 빼느냐로 기사가 정해집니다."
	hint.modulate = Color(0.7, 0.75, 0.7)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(hint)

	_block_checks.clear()
	var last_fact := ""
	for b in _tm.get_blocks():
		if b["fact"] != last_fact:
			last_fact = b["fact"]
			var facts: Dictionary = _tm.content.get("facts", {})
			var fh := Label.new()
			fh.text = "[%s]" % str(facts.get(last_fact, {}).get("title", last_fact))
			fh.add_theme_color_override("font_color", Color(0.55, 0.8, 0.95))
			vb.add_child(fh)
		var cb := CheckBox.new()
		cb.text = str(b["text"])
		cb.button_pressed = true  # 기본 전부 포함(정직 기준선)
		vb.add_child(cb)
		_block_checks.append({"cb": cb, "id": str(b["id"])})

	var pub := Button.new()
	pub.text = "발행"
	pub.custom_minimum_size = Vector2(0, 40)
	pub.pressed.connect(_on_publish)
	vb.add_child(pub)

	_status_label = Label.new()
	_status_label.add_theme_color_override("font_color", Color(1.0, 0.7, 0.5))
	_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_status_label)
	return panel

func _make_comments(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "댓글")
	_comments_box = _body_of(panel)
	var hint := Label.new()
	hint.text = "발행하면 여론 반응이 달립니다."
	hint.modulate = Color(0.7, 0.7, 0.7)
	_comments_box.add_child(hint)
	return panel

func _make_gauge(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "여론 게이지 (거시·부정확)")
	var vb := _body_of(panel)
	var dial := Control.new()
	dial.custom_minimum_size = Vector2(0, 190)
	vb.add_child(dial)
	var tex := _res(GAUGE_TEX)
	if tex != null:
		var tr := TextureRect.new()
		tr.texture = tex
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		dial.add_child(tr)
	_needle = Line2D.new()
	_needle.points = PackedVector2Array([Vector2(0, 0), Vector2(0, -85)])
	_needle.width = 4.0
	_needle.default_color = Color(1.0, 0.5, 0.2)
	_needle.position = Vector2(160, 180)
	dial.add_child(_needle)
	_set_needle(0.5)
	return panel

func _set_needle(macro: float) -> void:
	if _needle != null:
		_needle.rotation = deg_to_rad((macro - 0.5) * 120.0)  # 0.5=수직, 우=찬성, 좌=반대

# ---------- 발행 ----------
func _on_publish() -> void:
	var included: Array = []
	for entry in _block_checks:
		if (entry["cb"] as CheckBox).button_pressed:
			included.append(entry["id"])
	var result := _tm.publish({"included_ids": included})
	_render_comments(result["comments"])
	var snap: Dictionary = result["snapshot"]
	_set_needle(float(snap["tvMacro"]))
	var swing: float = float(snap["xs"]["sns_swing"])
	var reported: Array = result["reported_facts"]
	var report_txt: String = "미보도" if reported.is_empty() else "보도 %d건" % reported.size()
	_status_label.text = "턴 %d · %s · 논조 %s(δ=%.2f) · 부동층 %d%%%s" % [
		int(snap["turn"]), report_txt, str(result["frame_label"]), float(result["distortion"]),
		int(round(swing * 100.0)), "  ★목표 달성!" if bool(result["won"]) else "",
	]

func _render_comments(comments: Array) -> void:
	for c in _comments_box.get_children():
		c.queue_free()
	if comments.is_empty():
		var none := Label.new()
		none.text = "…반응이 뜸하다."
		none.modulate = Color(0.6, 0.6, 0.6)
		_comments_box.add_child(none)
		return
	for c in comments:
		var l := Label.new()
		l.text = "[%s] %s" % [str(c.get("seg", "")), str(c.get("text", ""))]
		l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_comments_box.add_child(l)
