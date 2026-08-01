extends Control
## 「태엽 인간」 1턴 수직 슬라이스 UI 컨트롤러.
## 데스크(정적 배경) → 모니터 클릭 → 전체화면 CRT OS UI(정보원·원고작성·댓글·게이지).
## 원고 작성 = 문장 블록 취사(넣을지 말지). 유리/불리는 노출하지 않음(플레이어 판단).
## 로직은 TurnManager(코어)에 위임. 마우스/클릭 전용. spec: docs/specs/turn_loop_vertical_slice.md

const DESK_BG := "res://assets/art/ui/main/desk_bg.png"
const GAUGE_TEX := "res://assets/art/ui/gauge/opinion_needle.png"
const WINDOW_FRAME := "res://assets/art/ui/window/frame.png"
const CRT_SHADER := "res://src/ui/shaders/crt_screen.gdshader"

const ENDINGS := {
	"성공": "표결일. 부동층이 찬성으로 돌아섰다. 「노동 근대화법」은 통과됐다.",
	"실패": "표결일. 끝내 여론을 돌리지 못했다. 법안은 보류됐다.",
	"발각파탄": "당신의 왜곡이 들통났다. 기자 자격을 잃고 편집국을 떠난다.",
	"배신파탄": "의뢰를 저버린 대가. 모르겐社가 등을 돌리고, 당신은 편집국에서 쫓겨난다.",
}

## 성공 엔딩의 후일담(정직/냉혹). turn_manager.epilogue() 가 고른다.
const EPILOGUES := {
	"정직": "당신은 짜맞춘 진실로 이겼다. 무엇을 지면에서 뺐는지는, 당신만 안다.",
	"냉혹": "형 테오의 이름은 끝내 지면에 오르지 않았다. 제 가족은 지키고 남의 삶은 팔았다. 거울 속 얼굴이 낯설다.",
}

# ---------- SE 시그널 (se attach 가 code_event 로 구독) ----------
## 이 시그널들은 게임 로직에 영향을 주지 않는다. se_emitter 브리지가 구독해
## 효과음만 재생한다(src/core 무지 원칙). 매니페스트 code_event 의 메서드명은
## 이 시그널명과 동일하게 지정한다(se_attach.derive_signal 규칙 ①).
signal monitor_powered       # 모니터 켜기 → CRT 전원 인
signal article_published     # 발행 → 타자기 카춘크
signal distortion_detected   # 이번 턴 신규 발각 → 스팅어
signal ending_reached        # 엔딩 도달
signal clue_found            # 책상에서 형 테오 흔적 발견

var _tm: TurnManager
var _desk: Control
var _screen: Control
var _os: Control
var _block_checks: Array = []  # [{cb: CheckBox, id: String}]
var _comments_box: VBoxContainer
var _needle: Line2D
var _status_label: Label
var _turn_label: Label
var _pub_button: Button
var _pressure_label: Label
var _branch_label: Label
var _blocks_box: VBoxContainer
var _desk_search_btn: Button
var _desk_note: Label
var _f16_shown: bool = false

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_apply_font()
	_tm = TurnManager.new(1)
	_build_desk()
	_build_screen()
	_screen.visible = false

func _res(path: String) -> Resource:
	return load(path) if ResourceLoader.exists(path) else null

## 한글 폰트를 런타임에 테마로 적용한다(자식 UI 전파). project.godot 의 custom_font 로
## 지정하면 콜드 임포트(첫 스캔) 시 폰트가 아직 임포트되기 전에 로드돼 ERROR 로그를
## 남기므로(웹 콜드 빌드·CI 오탐), 임포트가 끝난 런타임에 적용한다. 웹 export 필수:
## 시스템 폰트 폴백이 없어 한글이 두부(□)가 되는 것을 막는다(docs/web-export.md).
func _apply_font() -> void:
	var font := _res("res://assets/fonts/neodgm.ttf")
	if font is Font:
		var t := Theme.new()
		t.default_font = font
		theme = t

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

	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	_desk.add_child(box)
	var btn := Button.new()
	btn.name = "MonitorButton"
	btn.text = "모니터 켜기"
	btn.custom_minimum_size = Vector2(220, 56)
	btn.pressed.connect(_enter_screen)
	box.add_child(btn)
	_desk_search_btn = Button.new()
	_desk_search_btn.text = "책상 뒤지기"
	_desk_search_btn.custom_minimum_size = Vector2(220, 44)
	_desk_search_btn.pressed.connect(_search_desk)
	box.add_child(_desk_search_btn)
	_desk_note = Label.new()
	_desk_note.add_theme_color_override("font_color", Color(0.7, 0.85, 0.7))
	_desk_note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_desk_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_desk_note)

func _enter_screen() -> void:
	_desk.visible = false
	_screen.visible = true
	monitor_powered.emit()

func _exit_screen() -> void:
	_screen.visible = false
	_desk.visible = true

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and (event as InputEventKey).keycode == KEY_ESCAPE:
		if _screen != null and _screen.visible:
			_exit_screen()
		elif _desk != null and _desk.visible:
			_enter_screen()

func _search_desk() -> void:
	if _tm.discover_theo():
		clue_found.emit()
		_refresh_blocks()
		_desk_note.text = "책상 CRT 수신함에서 형 테오의 흔적을 찾았다. (원고에 추가됨)"
		if _desk_search_btn != null:
			_desk_search_btn.disabled = true
	else:
		_desk_note.text = "책상엔 더 뒤질 게 없다."

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
	_os = os
	os.add_child(_make_informant(Vector2(20, 48), Vector2(340, 320)))
	os.add_child(_make_editor(Vector2(376, 48), Vector2(430, 540)))
	os.add_child(_make_comments(Vector2(822, 48), Vector2(310, 400)))
	os.add_child(_make_gauge(Vector2(20, 376), Vector2(340, 268)))
	var back := Button.new()
	back.name = "BackButton"
	back.text = "← 데스크 (Esc)"
	back.position = Vector2(12, 10)
	back.custom_minimum_size = Vector2(150, 30)
	back.pressed.connect(_exit_screen)
	os.add_child(back)

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
	# 창 크롬: 브라스 프레임 텍스처를 9-slice(StyleBoxTexture)로 늘린다.
	# 텍스처 512² 중 테두리 약 96px 이 장식부라 그만큼 마진으로 잡아 모서리를 보존한다.
	var frame_tex := _res(WINDOW_FRAME)
	if frame_tex is Texture2D:
		var sb := StyleBoxTexture.new()
		sb.texture = frame_tex
		# 9-slice 마진: 창이 340px 대인데 96(텍스처 장식 실폭)을 쓰면 모서리만으로
		# 폭을 다 먹어 본문이 넘친다. 44 로 줄여 테두리 질감만 살린다.
		sb.set_texture_margin_all(44.0)
		# 본문은 테두리 안쪽으로. 상단은 프레임 타이틀바 장식을 피해 더 크게 잡는다.
		sb.content_margin_left = 30.0
		sb.content_margin_right = 30.0
		sb.content_margin_top = 46.0
		sb.content_margin_bottom = 26.0
		panel.add_theme_stylebox_override("panel", sb)
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
	_turn_label = Label.new()
	_turn_label.add_theme_color_override("font_color", Color(0.8, 0.9, 1.0))
	vb.add_child(_turn_label)
	_update_turn_label()
	var hint := Label.new()
	hint.text = "실을 문장에 체크. 무엇을 넣고 빼느냐로 기사가 정해집니다."
	hint.modulate = Color(0.7, 0.75, 0.7)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(hint)

	_blocks_box = VBoxContainer.new()
	vb.add_child(_blocks_box)
	_refresh_blocks()

	var pub := Button.new()
	pub.text = "발행"
	pub.custom_minimum_size = Vector2(0, 40)
	pub.pressed.connect(_on_publish)
	vb.add_child(pub)
	_pub_button = pub

	_status_label = Label.new()
	_status_label.add_theme_color_override("font_color", Color(1.0, 0.7, 0.5))
	_status_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_status_label)
	_pressure_label = Label.new()
	_pressure_label.add_theme_color_override("font_color", Color(0.95, 0.4, 0.35))
	_pressure_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_pressure_label)
	_branch_label = Label.new()
	_branch_label.add_theme_color_override("font_color", Color(0.7, 0.7, 0.55))
	_branch_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(_branch_label)
	return panel

## 취사 가능한 문장 블록을 현재 상태(F15 발견·F16 개폐 반영)로 다시 그린다.
func _refresh_blocks() -> void:
	if _blocks_box == null:
		return
	for c in _blocks_box.get_children():
		_blocks_box.remove_child(c)
		c.free()
	_block_checks.clear()
	var facts: Dictionary = _tm.content.get("facts", {})
	var last_fact := ""
	for b in _tm.get_blocks():
		if b["fact"] != last_fact:
			last_fact = str(b["fact"])
			var fh := Label.new()
			fh.text = "[%s]" % str((facts.get(last_fact, {}) as Dictionary).get("title", last_fact))
			fh.add_theme_color_override("font_color", Color(0.55, 0.8, 0.95))
			_blocks_box.add_child(fh)
		var cb := CheckBox.new()
		cb.text = str(b["text"])
		cb.button_pressed = true
		_blocks_box.add_child(cb)
		_block_checks.append({"cb": cb, "id": str(b["id"])})

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
	var det_before: int = _tm.model.detections.size()
	var result := _tm.publish({"included_ids": included})
	article_published.emit()
	if _tm.model.detections.size() > det_before:
		distortion_detected.emit()  # 이번 턴에 왜곡이 새로 들통났다
	_render_comments(result["comments"])
	var snap: Dictionary = result["snapshot"]
	_set_needle(float(snap["tvMacro"]))
	var swing: float = float(snap["xs"]["sns_swing"])
	var reported: Array = result["reported_facts"]
	var report_txt: String = "미보도" if reported.is_empty() else "보도 %d건" % reported.size()
	_status_label.text = "%s · 논조 %s(δ=%.2f) · 부동층 %d%%" % [
		report_txt, str(result["frame_label"]), float(result["distortion"]), int(round(swing * 100.0)),
	]
	if _pressure_label != null:
		_pressure_label.text = str(result["pressure_hint"])
	if _branch_label != null and str(result["branch_hint"]) != "":
		_branch_label.text = str(result["branch_hint"])
	if bool(result["f16_unlocked"]) and not _f16_shown:
		_f16_shown = true
		_refresh_blocks()  # F16 취재선 열림 → 새 문장 블록 등장
	if bool(result["over"]):
		_show_ending(str(result["ending"]), str(result.get("epilogue", "")))
	else:
		_update_turn_label()

func _update_turn_label() -> void:
	if _turn_label != null and _tm != null:
		_turn_label.text = "턴 %d / %d" % [_tm.model.turn + 1, _tm.max_turns]

func _show_ending(ending: String, epi: String = "") -> void:
	ending_reached.emit()
	if _pub_button != null:
		_pub_button.disabled = true
	var panel := PanelContainer.new()
	panel.name = "EndingOverlay"
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.custom_minimum_size = Vector2(660, 200)
	var vb := VBoxContainer.new()
	panel.add_child(vb)
	var title := Label.new()
	var title_suffix: String = "  ·  %s" % epi if epi != "" else ""
	title.text = "—  %s%s  —" % [ending, title_suffix]
	title.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	title.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	vb.add_child(title)
	var body := Label.new()
	body.text = str(ENDINGS.get(ending, ""))
	body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	body.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	vb.add_child(body)
	# 성공 엔딩이면 정직/냉혹 후일담을 한 줄 덧붙인다.
	if epi != "" and EPILOGUES.has(epi):
		var epi_label := Label.new()
		epi_label.text = str(EPILOGUES[epi])
		epi_label.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		epi_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		epi_label.add_theme_color_override("font_color", Color(0.72, 0.78, 0.85))
		vb.add_child(epi_label)
	if _os != null:
		_os.add_child(panel)

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
