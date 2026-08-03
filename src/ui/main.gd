extends Control
## 「태엽 인간」 1턴 수직 슬라이스 UI 컨트롤러.
## 데스크(정적 배경) → 모니터 클릭 → 전체화면 CRT OS UI(정보원·원고작성·댓글·게이지).
## 원고 작성 = 문장 블록 취사(넣을지 말지). 유리/불리는 노출하지 않음(플레이어 판단).
## 로직은 TurnManager(코어)에 위임. 마우스/클릭 전용. spec: docs/specs/turn_loop_vertical_slice.md

const DESK_BG := "res://assets/art/ui/main/desk_bg.png"
const GAUGE_TEX := "res://assets/art/ui/gauge/opinion_needle.png"
# 브라스 프레임 아트(frame.png)는 슬림 크롬 전환으로 창에서는 미사용.
# 매니페스트 art:ui/window/frame 은 유지 — 향후 타이틀 사인/엔딩 액자 재활용 후보.
const WINDOW_FRAME := "res://assets/art/ui/window/frame.png"
const CRT_SHADER := "res://src/ui/shaders/crt_screen.gdshader"
# 책상 뒤지기 클로즈업(선택 에셋): 이미지가 들어오면 자동 사용, 없으면 텍스트 연출만.
const DESK_SEARCH_TEX := "res://assets/art/ui/main/desk_search_closeup.png"
# 데스크 배경에서 모니터 화면의 중심(뷰포트 비율). 줌 인 트랜지션의 초점.
# 현 desk_bg.png 실측: 브라운관 유리면 중심 ≈ (0.51, 0.35).
const MONITOR_FOCUS := Vector2(0.51, 0.35)

# 게임 제목 — 네온사인 컨셉. N 이 지직거리다 꺼지면 GUIDE / LI E 만 남아
# 'LIE 를 GUIDE 한다'는 이중 의미가 드러난다 (SKYHILL 의 H 점멸 → ILL 강조와 같은 기법).
const TITLE_TEXT := "GUIDELINE"
const TITLE_FLICKER_IDX := 7    # 'N' (G0 U1 I2 D3 E4 L5 I6 N7 E8)
const TITLE_SUB := "치차 석간 — 태엽 인간 사건"
const NEON_ON := Color(1.0, 0.38, 0.22)          # 네온 레드오렌지(디젤펑크 가스관 사인)
const NEON_GLOW := Color(1.0, 0.30, 0.12, 0.38)  # 글로우(아웃라인)
const NEON_OFF := Color(0.28, 0.13, 0.10, 0.35)  # 꺼진 관(희미한 유리관 잔상)
const SETTINGS_PATH := "user://settings.cfg"  # 사운드 볼륨 등 사용자 설정 저장

## 댓글 작성자 핸들 풀 — 세그먼트 페르소나(설계 §4·§5)에 맞춘 디젤펑크 톤.
## 렌더 시 랜덤 선택 + 숫자 접미로 변주해 "고정 몇 개" 느낌을 없앤다(표시 전용, 게임 상태 무관).
const HANDLE_POOLS := {
	"sns_against": ["강철형제단", "짤린주조공", "무쇠팔", "톱니밥줄", "해고통보", "녹슨망치", "파업중", "치차노동자", "분노의용접공", "공돌이출신", "빼앗긴자"],
	"old_for": ["치차상공회", "근대화지지", "질서제일", "산업보국", "중산층가장", "진보의증인", "공장주협회", "석간구독자", "합리적시민", "애국시민", "노신사"],
	"sns_swing": ["톱니공", "치차뉴비", "퇴근길시민", "스크롤중", "판단보류", "도시청년", "중립기어", "카페인중독", "그냥시민", "고민중", "어제까진반대"],
	"apathetic": ["월급인상요망", "관심없음", "밥먼저", "퇴근하고싶다", "그런갑다", "출근싫어", "핸드폰만봄", "눈팅중", "무념무상", "지나가던1인"],
}
const HANDLE_FALLBACK := ["치차시민", "익명", "이름없음"]

## 댓글 슬롯 치환값 — 댓글의 topic 기준으로 {키워드}/{대상}/{수치}/{집단}을 채운다
## (설계 댓글뱅크_설계_v0.1 §4). 댓글이 그 주제로 쓰였으므로 topic 기준이 안전하다.
const COMMENT_SLOTS := {
	"생산성": {"수치": "42%", "대상": "모르겐", "키워드": "생산성 42%"},
	"안전": {"수치": "인명사고 0건", "대상": "모르겐", "키워드": "인명사고 제로"},
	"신직종": {"수치": "1,900명", "대상": "재교육원", "키워드": "재교육"},
	"경쟁": {"대상": "노르덴", "키워드": "노르덴 양산"},
	"실업": {"수치": "6,300", "대상": "회사", "키워드": "대량 해고"},
	"임금": {"수치": "30%", "대상": "회사", "키워드": "임금 삭감"},
	"인격": {"대상": "모르겐", "키워드": "일곱이"},
	"무력충돌": {"대상": "강철 손", "키워드": "공장 앞 충돌"},
	"유착": {"대상": "소여 위원장", "키워드": "발의자 유착"},
	"비공개": {"대상": "모르겐", "키워드": "감사 거부"},
}
## topic 에 값이 없을 때(또는 topic=null)의 최후 대체값 — 문장이 어색하지 않게.
const SLOT_FALLBACK := {"키워드": "이번 기사", "대상": "회사", "수치": "그 숫자", "집단": "저쪽 사람들"}

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
signal window_opened         # OS 창 열림 → 팝
signal window_closed         # OS 창 닫힘/내림 → 역팝
signal file_dropped          # 정보 파일을 원고에 실음 → 종이 탁
signal neon_buzz             # 타이틀 네온 지직(점멸 버스트 시작)

var _tm: TurnManager
var _desk: Control
var _screen: Control
var _os: Control
var _draft_ids: Array = []          # 이번 기사에 끌어다 놓은 블록 id (드래그앤드롭, 턴마다 초기화)
var _folder_box: VBoxContainer      # 정보 폴더(파일 목록) 본문
var _draft_box: VBoxContainer       # 원고 창 드롭 영역 본문
var _comments_box: VBoxContainer
var _needle: Line2D
var _status_label: Label
var _turn_label: Label
var _pub_button: Button
var _pressure_label: Label
var _branch_label: Label
var _desk_search_btn: Button
var _desk_note: Label
var _f16_shown: bool = false
var _informant_body: VBoxContainer  # 정보원 패널 스크롤 본문(턴별 갱신 대상)
var _informant_title: Label         # 정보원 패널 타이틀(오늘/누적 카운트 표시)
var _article_box: VBoxContainer     # 발행 기사 오버레이의 스크롤 본문(헤드라인+본문)
var _article_panel: PanelContainer  # 발행 기사 오버레이(발행 시 크게 출력·X 닫기)
var _article_view_btn: Button       # 원고 창의 "기사 다시 보기" 버튼
var _article_history: Array = []     # 발행된 기사 기록 [{reported, frame, body, turn}] — < > 로 탐색
var _article_idx: int = -1           # 현재 보고 있는 기사 인덱스
var _article_nav_label: Label        # 오버레이의 "T3 · 2/5" 표시
var _article_prev_btn: Button
var _article_next_btn: Button
var _settings_panel: PanelContainer # 소리 설정 오버레이
var _se_vol: float = 0.4            # 효과음 볼륨(0~1, 기본 ≈ -8dB)
var _bgm_vol: float = 0.5           # 배경음 볼륨(0~1, BGM 추가 대비)
var _carryover_selected: Array = [] # 「받은 자료」에서 이번 기사에 끌어온 과거 fact id (턴마다 초기화)
var _archive_panel: PanelContainer  # 「받은 자료」 오버레이(과거 정보 열람·선별)
var _archive_body: VBoxContainer
var _archive_btn: Button            # 정보원 패널의 「받은 자료」 버튼(개수 표시)
var _fade_rect: ColorRect           # 데스크↔스크린 트랜지션용 암전 오버레이(최상단)
var _transitioning: bool = false    # 트랜지션 중 입력 무시(중복 클릭·ESC 연타 방지)
var _crt_mat: ShaderMaterial        # CRT 셰이더(파워온 연출에서 파라미터 트윈)
var _needle_rot_base: float = 0.0   # 바늘 목표 회전(트윈 대상). 실제 회전 = base + 떨림
var _needle_excite: float = 0.0     # 발행 직후 동요(떨림 증폭, 시간 감쇠)
var _tube_dims: Array = []          # 닉시관 소등 오버레이 5개 — 켜진 개수 = 여론 레벨
var _title_view: Control            # 타이틀 화면(시작 전)
var _day_card: Control              # 턴 경과(석간 마감→다음 날) 인터스티셜
var _day_label: Label
var _windows: Dictionary = {}       # OS 앱 창: key -> PanelContainer (mail/informant/editor/comments/gauge)
var _dock_btns: Dictionary = {}     # 태스크바 앱 버튼: key -> Button (열림 표시·배지용)
var _mail_list: VBoxContainer       # 수신함 본문(최신이 위)
var _mail_unread: int = 0
var _neon_n: Label                  # 타이틀 네온사인의 점멸 글자(N)
var _neon_rng := RandomNumberGenerator.new()
var _taskbar_day: Label             # 태스크바 우측 "제 N 일" 표시
var _day_stage: int = 0             # 턴 경과 카드 진행 단계(클릭으로 넘김)
var _day_done: Callable             # 카드 종료 후 콜백
var _day_busy: bool = false         # 페이드 중 클릭 무시
var _booted: bool = false           # _ready 완료 후 true — 부팅 중 창 SE 발화 방지

func _ready() -> void:
	set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_apply_font()
	_load_audio_settings()  # 저장된 볼륨을 SE/BGM 버스에 적용(버스는 default_bus_layout.tres)
	_tm = TurnManager.new(1)
	_build_desk()
	_build_screen()
	_screen.visible = false
	_desk.visible = false
	_build_title()  # 시작은 타이틀 화면(신문 제호)에서
	_build_day_card()
	# 트랜지션 암전막: 항상 최상단(CRT 포함 모든 것 위). 평소엔 투명+클릭 통과.
	_fade_rect = ColorRect.new()
	_fade_rect.name = "TransitionFade"
	_fade_rect.color = Color(0, 0, 0, 0)
	_fade_rect.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_fade_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE
	add_child(_fade_rect)
	_booted = true

# ---------- 타이틀 화면 (네온사인 컨셉) ----------
func _build_title() -> void:
	_title_view = Control.new()
	_title_view.name = "TitleView"
	_title_view.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_title_view)
	var bg := ColorRect.new()
	bg.color = Color(0.045, 0.045, 0.06)  # 밤거리 톤
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_title_view.add_child(bg)
	var box := VBoxContainer.new()
	box.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	box.grow_horizontal = Control.GROW_DIRECTION_BOTH
	box.grow_vertical = Control.GROW_DIRECTION_BOTH
	box.add_theme_constant_override("separation", 12)
	_title_view.add_child(box)
	var date_line := Label.new()
	date_line.text = "아이젠 공화국 · 치차  |  노동 근대화법 표결 8일 전"
	date_line.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	date_line.add_theme_color_override("font_color", Color(0.5, 0.5, 0.56))
	box.add_child(date_line)
	# 네온 표지판: 어두운 금속판 위에 글자별 네온관. N(TITLE_FLICKER_IDX)만 지직거리며,
	# 꺼진 순간 GUIDE / LI E — 'LIE' 가 드러난다.
	var sign := PanelContainer.new()
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.07, 0.085)
	sb.border_color = Color(0.30, 0.30, 0.34)
	sb.set_border_width_all(3)
	sb.set_corner_radius_all(6)
	sb.content_margin_left = 40.0
	sb.content_margin_right = 40.0
	sb.content_margin_top = 18.0
	sb.content_margin_bottom = 18.0
	sign.add_theme_stylebox_override("panel", sb)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 4)
	sign.add_child(row)
	for i in TITLE_TEXT.length():
		var l := Label.new()
		l.text = TITLE_TEXT[i]
		l.add_theme_font_size_override("font_size", 84)
		l.add_theme_color_override("font_color", NEON_ON)
		l.add_theme_color_override("font_outline_color", NEON_GLOW)
		l.add_theme_constant_override("outline_size", 14)
		row.add_child(l)
		if i == TITLE_FLICKER_IDX:
			_neon_n = l
	var sign_wrap := CenterContainer.new()
	sign_wrap.add_child(sign)
	box.add_child(sign_wrap)
	var sub := Label.new()
	sub.text = TITLE_SUB
	sub.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	sub.add_theme_font_size_override("font_size", 20)
	sub.add_theme_color_override("font_color", Color(0.62, 0.58, 0.48))
	box.add_child(sub)
	var pad := Control.new()
	pad.custom_minimum_size = Vector2(0, 16)
	box.add_child(pad)
	var start := _desk_button("출근한다", 52)
	start.name = "StartButton"
	start.pressed.connect(_start_game)
	var wrap := CenterContainer.new()
	wrap.add_child(start)
	box.add_child(wrap)
	var hint := Label.new()
	hint.text = "무엇을 싣고, 무엇을 뺄 것인가."
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.add_theme_color_override("font_color", Color(0.45, 0.44, 0.4))
	box.add_child(hint)
	box.modulate = Color(1, 1, 1, 0)
	var tw := create_tween()
	tw.tween_property(box, "modulate:a", 1.0, 0.9).set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tw.tween_callback(_neon_flicker_loop)

## N 네온관 점멸 루프: 켜짐 유지 → 지직(급점멸 2~4회) → 한동안 꺼짐(LIE 노출) → 재점등.
## 매 사이클 난수 재구성이라 기계적으로 반복되지 않는다. 타이틀을 떠나면 스스로 멈춘다.
func _neon_flicker_loop() -> void:
	if _neon_n == null or _title_view == null or not _title_view.visible:
		return
	var tw := create_tween()
	tw.tween_interval(_neon_rng.randf_range(0.9, 2.4))
	tw.tween_callback(neon_buzz.emit)  # 버스트 시작에 지직음
	for i in _neon_rng.randi_range(2, 4):
		tw.tween_callback(_set_neon.bind(false))
		tw.tween_interval(_neon_rng.randf_range(0.03, 0.09))
		tw.tween_callback(_set_neon.bind(true))
		tw.tween_interval(_neon_rng.randf_range(0.04, 0.12))
	tw.tween_callback(_set_neon.bind(false))
	tw.tween_interval(_neon_rng.randf_range(0.8, 1.8))  # 꺼진 동안 'GUIDE LI E' = LIE
	tw.tween_callback(_set_neon.bind(true))
	tw.tween_callback(_neon_flicker_loop)

func _set_neon(on: bool) -> void:
	if _neon_n == null:
		return
	_neon_n.add_theme_color_override("font_color", NEON_ON if on else NEON_OFF)
	_neon_n.add_theme_constant_override("outline_size", 14 if on else 0)

func _start_game() -> void:
	if _transitioning:
		return
	_transitioning = true
	var tw := create_tween()
	tw.tween_property(_fade_rect, "color:a", 1.0, 0.4)
	tw.tween_callback(func() -> void:
		_title_view.visible = false
		_desk.visible = true)
	tw.tween_property(_fade_rect, "color:a", 0.0, 0.5)
	tw.tween_callback(func() -> void: _transitioning = false)

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
	box.add_theme_constant_override("separation", 10)
	_desk.add_child(box)
	var btn := _desk_button("모니터 켜기", 56)
	btn.name = "MonitorButton"
	btn.pressed.connect(_enter_screen)
	box.add_child(btn)
	_desk_search_btn = _desk_button("책상 뒤지기", 44)
	_desk_search_btn.pressed.connect(_search_desk)
	box.add_child(_desk_search_btn)
	_desk_note = Label.new()
	_desk_note.add_theme_color_override("font_color", Color(0.7, 0.85, 0.7))
	_desk_note.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_desk_note.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	box.add_child(_desk_note)

## 데스크 버튼: 기본 테마의 반투명 회색 패널은 디젤펑크 배경과 톤이 어긋난다.
## 황동 테두리 + 어두운 바켈라이트 면으로 스타일 가이드(§2 재질)에 맞춘다.
func _desk_button(label: String, height: int) -> Button:
	var b := Button.new()
	b.text = label
	b.custom_minimum_size = Vector2(232, height)
	var base := StyleBoxFlat.new()
	base.bg_color = Color(0.13, 0.09, 0.06, 0.92)
	base.border_color = Color(0.62, 0.45, 0.20)
	base.set_border_width_all(2)
	base.set_corner_radius_all(3)
	base.set_content_margin_all(8)
	var hover := base.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.22, 0.15, 0.08, 0.96)
	hover.border_color = Color(0.90, 0.66, 0.28)
	var pressed := base.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(0.30, 0.20, 0.10, 0.98)
	b.add_theme_stylebox_override("normal", base)
	b.add_theme_stylebox_override("hover", hover)
	b.add_theme_stylebox_override("pressed", pressed)
	b.add_theme_stylebox_override("focus", hover)
	b.add_theme_color_override("font_color", Color(0.95, 0.82, 0.55))
	b.add_theme_color_override("font_hover_color", Color(1.0, 0.90, 0.66))
	return b

## 모니터 클릭 → 화면 컷 전환 대신 "모니터로 들어가는" 줌 인:
## 데스크를 모니터 초점(MONITOR_FOCUS) 기준으로 확대하며 암전 → CRT 파워온.
func _enter_screen() -> void:
	if _transitioning or (_screen != null and _screen.visible):
		return
	_transitioning = true
	_fade_rect.mouse_filter = Control.MOUSE_FILTER_STOP  # 전환 중 클릭 차단
	_desk.pivot_offset = get_viewport_rect().size * MONITOR_FOCUS
	var tw := create_tween()
	tw.set_parallel(true)
	tw.tween_property(_desk, "scale", Vector2(2.1, 2.1), 0.5) \
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	tw.tween_property(_fade_rect, "color:a", 1.0, 0.45) \
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN)
	tw.chain().tween_callback(func() -> void:
		_desk.visible = false
		_desk.scale = Vector2.ONE
		_screen.visible = true
		monitor_powered.emit()
		_crt_power_on())

## CRT 파워온: 암전에서 밝아지며 2번 깜빡 + 스캔라인·색수차가 과했다가 정상치로 안정.
func _crt_power_on() -> void:
	_screen.modulate = Color(1, 1, 1, 0)
	var tw := create_tween()
	tw.tween_property(_fade_rect, "color:a", 0.0, 0.12)
	tw.parallel().tween_property(_screen, "modulate:a", 0.85, 0.08)
	tw.tween_property(_screen, "modulate:a", 0.25, 0.06)
	tw.tween_property(_screen, "modulate:a", 1.0, 0.16)
	if _crt_mat != null:
		_crt_mat.set_shader_parameter("scanline_strength", 0.85)
		_crt_mat.set_shader_parameter("aberration", 0.012)
		tw.parallel().tween_method(func(v: float) -> void:
			_crt_mat.set_shader_parameter("scanline_strength", lerpf(0.85, 0.25, v))
			_crt_mat.set_shader_parameter("aberration", lerpf(0.012, 0.002, v)),
			0.0, 1.0, 0.55)
	tw.tween_callback(func() -> void:
		_transitioning = false
		_fade_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE)

# ---------- 턴 경과 인터스티셜 (클릭으로 진행) ----------
func _build_day_card() -> void:
	_day_card = Control.new()
	_day_card.name = "DayCard"
	_day_card.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	_day_card.visible = false
	_day_card.mouse_filter = Control.MOUSE_FILTER_STOP  # 아래 UI 클릭 차단 + 카드 자체가 클릭 대상
	_day_card.gui_input.connect(_day_card_input)
	var bg := ColorRect.new()
	bg.color = Color(0, 0, 0, 0.94)
	bg.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	bg.mouse_filter = Control.MOUSE_FILTER_IGNORE
	_day_card.add_child(bg)
	_day_label = Label.new()
	_day_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_day_label.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	_day_label.grow_horizontal = Control.GROW_DIRECTION_BOTH
	_day_label.grow_vertical = Control.GROW_DIRECTION_BOTH
	_day_label.add_theme_font_size_override("font_size", 30)
	_day_label.add_theme_color_override("font_color", Color(0.9, 0.82, 0.62))
	_day_card.add_child(_day_label)
	var hint := Label.new()
	hint.name = "ClickHint"
	hint.text = "— 클릭해서 계속 —"
	hint.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	hint.set_anchors_preset(Control.PRESET_CENTER_BOTTOM)
	hint.offset_top = -70.0
	hint.offset_bottom = -46.0
	hint.grow_horizontal = Control.GROW_DIRECTION_BOTH
	hint.add_theme_color_override("font_color", Color(0.55, 0.52, 0.45))
	_day_card.add_child(hint)
	add_child(_day_card)

## 발행 직후: "석간 마감 → 다음 날" 카드. 자동으로 흐르지 않고 클릭할 때마다 진행된다.
## 엔딩 턴에는 쓰지 않는다(엔딩 오버레이가 우선).
func _show_day_transition(done: Callable) -> void:
	_day_done = done
	_day_stage = 0
	_day_busy = true
	_day_label.text = "— 석간 마감. 윤전기가 돈다 —"
	_day_card.modulate = Color(1, 1, 1, 0)
	_day_card.visible = true
	_day_card.move_to_front()
	var tw := create_tween()
	tw.tween_property(_day_card, "modulate:a", 1.0, 0.3)
	tw.tween_callback(func() -> void: _day_busy = false)

func _day_card_input(ev: InputEvent) -> void:
	if ev is InputEventMouseButton and (ev as InputEventMouseButton).pressed \
			and (ev as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		_day_card_next()

func _day_card_next() -> void:
	if _day_busy or not _day_card.visible:
		return
	if _day_stage == 0:
		_day_stage = 1
		_day_label.text = "제 %d 일 아침  ·  표결까지 %d일" % [
			_tm.model.turn + 1, maxi(_tm.max_turns - _tm.model.turn, 0)]
	else:
		_day_busy = true
		var tw := create_tween()
		tw.tween_property(_day_card, "modulate:a", 0.0, 0.3)
		tw.tween_callback(func() -> void:
			_day_card.visible = false
			_day_busy = false
			if _day_done.is_valid():
				_day_done.call())

## 스크린 → 데스크: 짧은 암전 후 "모니터에서 물러나는" 줌 아웃.
func _exit_screen() -> void:
	if _transitioning or (_desk != null and _desk.visible):
		return
	_transitioning = true
	_fade_rect.mouse_filter = Control.MOUSE_FILTER_STOP
	var tw := create_tween()
	tw.tween_property(_fade_rect, "color:a", 1.0, 0.18)
	tw.tween_callback(func() -> void:
		_screen.visible = false
		_desk.visible = true
		_desk.pivot_offset = get_viewport_rect().size * MONITOR_FOCUS
		_desk.scale = Vector2(1.6, 1.6))
	tw.tween_property(_desk, "scale", Vector2.ONE, 0.4) \
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tw.parallel().tween_property(_fade_rect, "color:a", 0.0, 0.3)
	tw.tween_callback(func() -> void:
		_transitioning = false
		_fade_rect.mouse_filter = Control.MOUSE_FILTER_IGNORE)

func _input(event: InputEvent) -> void:
	if event is InputEventKey and event.pressed and not event.echo and (event as InputEventKey).keycode == KEY_ESCAPE:
		if _transitioning or (_title_view != null and _title_view.visible):
			return
		if _day_card != null and _day_card.visible:  # 턴 경과 카드는 ESC 로도 넘어간다
			_day_card_next()
			return
		# ESC 는 열려 있는 오버레이부터 닫는다(기사 → 받은자료 → 설정 → 화면 전환).
		if _article_panel != null and _article_panel.visible:
			_article_panel.visible = false
			return
		if _archive_panel != null and _archive_panel.visible:
			_archive_panel.visible = false
			return
		if _settings_panel != null and _settings_panel.visible:
			_settings_panel.visible = false
			return
		if _screen != null and _screen.visible:
			_exit_screen()
		elif _desk != null and _desk.visible:
			_enter_screen()

# ---------- 소리 설정 ----------
func _build_settings_panel(parent: Control) -> void:
	var panel := PanelContainer.new()
	panel.name = "SettingsPanel"
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH  # 중심에서 대칭으로 자라 정중앙에 오게
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	panel.custom_minimum_size = Vector2(360, 0)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.08, 0.10, 0.08, 0.96)
	sb.set_border_width_all(2)
	sb.border_color = Color(0.7, 0.55, 0.25)
	sb.set_corner_radius_all(4)
	sb.set_content_margin_all(18)
	panel.add_theme_stylebox_override("panel", sb)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 10)
	panel.add_child(vb)
	var title := Label.new()
	title.text = "▍ 소리 설정"
	title.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	vb.add_child(title)
	vb.add_child(HSeparator.new())
	vb.add_child(_volume_row("효과음", "SE", _se_vol))
	vb.add_child(_volume_row("배경음", "BGM", _bgm_vol))
	var close := Button.new()
	close.text = "닫기"
	close.pressed.connect(func() -> void: panel.visible = false)
	vb.add_child(close)
	panel.visible = false
	parent.add_child(panel)
	_settings_panel = panel

## 볼륨 슬라이더 한 줄(라벨 + 백분율 + HSlider). 값이 바뀌면 버스에 즉시 반영·저장.
func _volume_row(label_text: String, bus_name: String, init_val: float) -> Control:
	var row := VBoxContainer.new()
	var head := Label.new()
	head.text = "%s  %d%%" % [label_text, int(round(init_val * 100.0))]
	row.add_child(head)
	var s := HSlider.new()
	s.min_value = 0.0
	s.max_value = 1.0
	s.step = 0.01
	s.value = init_val
	s.custom_minimum_size = Vector2(300, 22)
	s.value_changed.connect(func(v: float) -> void:
		head.text = "%s  %d%%" % [label_text, int(round(v * 100.0))]
		_on_vol_changed(bus_name, v))
	row.add_child(s)
	return row

func _toggle_settings() -> void:
	if _settings_panel != null:
		_settings_panel.visible = not _settings_panel.visible
		if _settings_panel.visible:
			_settings_panel.move_to_front()

func _on_vol_changed(bus_name: String, v: float) -> void:
	if bus_name == "SE":
		_se_vol = v
	else:
		_bgm_vol = v
	_apply_bus_vol(bus_name, v)
	_save_audio_settings()

## 0~1 볼륨을 버스에 적용(0 근처면 뮤트). 버스가 없으면 조용히 무시.
func _apply_bus_vol(bus_name: String, v: float) -> void:
	var idx: int = AudioServer.get_bus_index(bus_name)
	if idx < 0:
		return
	AudioServer.set_bus_mute(idx, v <= 0.005)
	AudioServer.set_bus_volume_db(idx, linear_to_db(maxf(v, 0.0001)))

func _load_audio_settings() -> void:
	var cfg := ConfigFile.new()
	if cfg.load(SETTINGS_PATH) == OK:
		_se_vol = float(cfg.get_value("audio", "se", _se_vol))
		_bgm_vol = float(cfg.get_value("audio", "bgm", _bgm_vol))
	_apply_bus_vol("SE", _se_vol)
	_apply_bus_vol("BGM", _bgm_vol)

func _save_audio_settings() -> void:
	var cfg := ConfigFile.new()
	cfg.load(SETTINGS_PATH)  # 다른 섹션 보존
	cfg.set_value("audio", "se", _se_vol)
	cfg.set_value("audio", "bgm", _bgm_vol)
	cfg.save(SETTINGS_PATH)

# ---------- 받은 자료(과거 정보 열람·선별) ----------
func _build_archive_panel(parent: Control) -> void:
	var panel := PanelContainer.new()
	panel.name = "ArchivePanel"
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH  # 중심에서 대칭으로 자라 정중앙에 오게
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	panel.custom_minimum_size = Vector2(560, 460)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.07, 0.09, 0.07, 0.97)
	sb.set_border_width_all(2)
	sb.border_color = Color(0.7, 0.55, 0.25)
	sb.set_corner_radius_all(4)
	sb.set_content_margin_all(18)
	panel.add_theme_stylebox_override("panel", sb)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 8)
	panel.add_child(vb)
	var title := Label.new()
	title.text = "▍ 받은 자료 — 지난 정보를 이 기사에 끌어오기"
	title.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	vb.add_child(title)
	vb.add_child(HSeparator.new())
	_archive_body = _scroll_body(vb)
	var close := Button.new()
	close.text = "닫기"
	close.pressed.connect(func() -> void: panel.visible = false)
	vb.add_child(close)
	panel.visible = false
	parent.add_child(panel)
	_archive_panel = panel

func _toggle_archive() -> void:
	if _archive_panel == null:
		return
	_archive_panel.visible = not _archive_panel.visible
	if _archive_panel.visible:
		_refresh_archive()
		_archive_panel.move_to_front()

## 「받은 자료」 목록을 다시 그린다: 과거(오늘 아님) 가용 사실 + 기사에 넣기/빼기 토글.
func _refresh_archive() -> void:
	if _archive_body == null:
		return
	for c in _archive_body.get_children():
		c.queue_free()
	var facts: Dictionary = _tm.content.get("facts", {})
	var cur_turn: int = _cur_turn()
	var any := false
	for fid in _available_fact_ids():
		var f: Dictionary = facts.get(fid, {})
		if _is_today_fact(f, cur_turn):
			continue  # 오늘 것은 정보원 패널에 이미 있음
		any = true
		var picked: bool = _carryover_selected.has(fid)
		var row := VBoxContainer.new()
		var head := Label.new()
		head.text = "↩ 이월 T%d  %s" % [int(f.get("turn", 0)), str(f.get("title", ""))]
		head.add_theme_color_override("font_color", Color(0.7, 0.8, 0.95))
		row.add_child(head)
		for frag in f.get("fragments", []):
			var l := Label.new()
			l.text = str(frag.get("text", ""))
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			l.modulate = Color(0.85, 0.85, 0.8)
			row.add_child(l)
		var btn := Button.new()
		btn.text = "기사에서 빼기" if picked else "이 기사에 넣기"
		btn.pressed.connect(func() -> void: _toggle_carryover(fid))
		row.add_child(btn)
		row.add_child(HSeparator.new())
		_archive_body.add_child(row)
	if not any:
		var none := Label.new()
		none.text = "아직 이월된 자료가 없습니다."
		none.modulate = Color(0.65, 0.65, 0.6)
		_archive_body.add_child(none)

func _toggle_carryover(fid: String) -> void:
	if _carryover_selected.has(fid):
		_carryover_selected.erase(fid)
	else:
		_carryover_selected.append(fid)
	_refresh_blocks()   # 원고 창에 즉시 반영
	_refresh_archive()  # 버튼 라벨 갱신

func _search_desk() -> void:
	if _transitioning:
		return
	if _tm.discover_theo():
		clue_found.emit()
		_refresh_blocks()
		_refresh_informant()  # F15 단서가 정보원 패널에도 등장
		_desk_rummage_fx("책상 CRT 수신함에서 형 테오의 흔적을 찾았다. (원고에 추가됨)", true)
		if _desk_search_btn != null:
			_desk_search_btn.disabled = true
	else:
		_desk_rummage_fx("책상엔 더 뒤질 게 없다.", false)

## 책상 뒤지기 연출: 서랍 쪽으로 시선이 쏠리는 살짝 줌 + 노트 타자기 출력.
## 클로즈업 이미지(DESK_SEARCH_TEX)가 들어오면 발견 시 잠깐 띄운다(에셋 수급 대비 훅).
func _desk_rummage_fx(note: String, found: bool) -> void:
	# 아래쪽(서랍)으로 훅 들어갔다 나오는 카메라 느낌.
	_desk.pivot_offset = get_viewport_rect().size * Vector2(0.5, 0.85)
	var tw := create_tween()
	tw.tween_property(_desk, "scale", Vector2(1.12, 1.12), 0.16) \
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)
	tw.tween_property(_desk, "scale", Vector2.ONE, 0.22) \
		.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_IN_OUT)
	# 노트는 타자기처럼 한 글자씩.
	_desk_note.text = note
	_desk_note.visible_ratio = 0.0
	tw.parallel().tween_property(_desk_note, "visible_ratio", 1.0, note.length() * 0.03)
	# 발견 + 클로즈업 에셋이 있으면 서랍 클로즈업을 2초 보여준다.
	var closeup := _res(DESK_SEARCH_TEX)
	if found and closeup is Texture2D:
		var shot := TextureRect.new()
		shot.texture = closeup
		shot.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		shot.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		shot.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		shot.modulate = Color(1, 1, 1, 0)
		_desk.add_child(shot)
		var stw := create_tween()
		stw.tween_property(shot, "modulate:a", 1.0, 0.25)
		stw.tween_interval(2.0)
		stw.tween_property(shot, "modulate:a", 0.0, 0.35)
		stw.tween_callback(shot.queue_free)

# ---------- 스크린 상태 (CRT OS) ----------
func _build_screen() -> void:
	_screen = Control.new()
	_screen.name = "ScreenState"
	_screen.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	add_child(_screen)

	# 모니터 베젤: 화면 가장자리를 두른 바켈라이트 테두리 — OS 는 이 "유리면" 안에만 산다.
	var bezel := Panel.new()
	bezel.name = "MonitorBezel"
	bezel.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	var bsb := StyleBoxFlat.new()
	bsb.bg_color = Color(0.09, 0.07, 0.055)
	bsb.border_color = Color(0.32, 0.24, 0.14)  # 브라스 라인
	bsb.set_border_width_all(2)
	bsb.set_corner_radius_all(10)
	bezel.add_theme_stylebox_override("panel", bsb)
	_screen.add_child(bezel)
	var power_led := ColorRect.new()  # 베젤 우하단 전원 램프
	power_led.color = Color(1.0, 0.62, 0.2)
	power_led.set_anchors_preset(Control.PRESET_BOTTOM_RIGHT)
	power_led.offset_left = -14.0
	power_led.offset_top = -14.0
	power_led.offset_right = -7.0
	power_led.offset_bottom = -7.0
	bezel.add_child(power_led)

	# ScreenOS = 유리면(베젤 안쪽 22px). 바탕화면·아이콘·태스크바·창 전부 이 안에.
	var os := Control.new()
	os.name = "ScreenOS"
	os.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	os.offset_left = 22.0
	os.offset_top = 22.0
	os.offset_right = -22.0
	os.offset_bottom = -22.0
	os.clip_contents = true  # 창을 끌어도 유리면 밖(베젤 위)으로 나가지 않는다
	_screen.add_child(os)
	_os = os
	var wallpaper := ColorRect.new()
	wallpaper.name = "Wallpaper"
	wallpaper.color = Color(0.035, 0.06, 0.045)  # CRT 인광 그린 바탕화면
	wallpaper.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	os.add_child(wallpaper)
	_build_desktop_icons(os)
	# 앱 창 (유리면 좌표계, 태스크바 34px 를 뺀 작업영역 안):
	_windows["informant"] = _make_informant(Vector2(110, 8), Vector2(440, 300))
	_windows["folder"] = _make_folder(Vector2(110, 314), Vector2(440, 248))
	_windows["editor"] = _make_editor(Vector2(560, 8), Vector2(436, 554))
	_windows["comments"] = _make_comments(Vector2(600, 84), Vector2(430, 430))
	_windows["gauge"] = _make_gauge_widget(Vector2(880, 340))
	_windows["mail"] = _make_mail(Vector2(280, 70), Vector2(520, 410))
	for key in _windows:
		var w := _windows[key] as PanelContainer
		w.set_meta("app_key", key)
		os.add_child(w)
		w.visible = false
	_build_taskbar(os)
	# 첫 부팅: 의뢰 메일이 도착해 있고, 수신함이 열린 채 시작한다(온보딩).
	_push_mail("산업위원회 (발신전용)", "의뢰 — 표결일까지",
		"노동 근대화법 표결이 %d일 뒤다. 그때까지 SNS 부동층을 찬성 %d%%로 돌려라.\n방법은 묻지 않는다. 모르겐社도 치차 석간의 '정확한' 보도를 기대하고 있다.\n\n※ [정보원]에서 오늘 입수분을 확인 → [정보 폴더]의 파일을 [원고]로 끌어다 기사를 만들고 발행할 것." % [
			_tm.max_turns, int(round(float(_tm.model.config["mission"]["winThreshold"]) * 100.0))])
	_open_win("mail")
	_build_settings_panel(os)
	_build_archive_panel(os)
	_build_article_panel(os)

	var bbc := BackBufferCopy.new()
	bbc.copy_mode = BackBufferCopy.COPY_MODE_VIEWPORT
	_screen.add_child(bbc)

	var crt := ColorRect.new()
	crt.name = "CrtOverlay"
	# CRT 효과(스캔라인·곡률·비네트)는 베젤이 아니라 유리면 위에만 얹는다.
	crt.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
	crt.offset_left = 22.0
	crt.offset_top = 22.0
	crt.offset_right = -22.0
	crt.offset_bottom = -22.0
	crt.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var sh := _res(CRT_SHADER)
	if sh != null:
		var mat := ShaderMaterial.new()
		mat.shader = sh
		crt.material = mat
		_crt_mat = mat  # 파워온 연출에서 스캔라인·색수차 파라미터를 트윈
	_screen.add_child(crt)

# ---------- OS 태스크바 + 바탕화면 아이콘 ----------
const APPS := [  # [key, 라벨, 아이콘 글리프]
	["mail", "메일", "✉"], ["informant", "정보원", "☏"], ["folder", "정보 폴더", "▤"],
	["editor", "원고", "✎"], ["comments", "댓글", "❝"], ["gauge", "여론계", "◉"],
]

func _build_taskbar(parent: Control) -> void:
	var bar := PanelContainer.new()
	bar.name = "Taskbar"
	bar.set_anchors_preset(Control.PRESET_BOTTOM_WIDE)
	bar.offset_top = -34.0
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.06, 0.09, 0.07, 0.96)
	sb.border_color = Color(0.30, 0.24, 0.14)
	sb.border_width_top = 2
	sb.content_margin_left = 6.0
	sb.content_margin_right = 8.0
	sb.content_margin_top = 3.0
	sb.content_margin_bottom = 3.0
	bar.add_theme_stylebox_override("panel", sb)
	parent.add_child(bar)
	var row := HBoxContainer.new()
	row.add_theme_constant_override("separation", 6)
	bar.add_child(row)
	var back := Button.new()
	back.name = "BackButton"
	back.text = "◀ 데스크"
	back.tooltip_text = "모니터에서 물러난다 (Esc)"
	back.custom_minimum_size = Vector2(92, 0)
	back.pressed.connect(_exit_screen)
	row.add_child(back)
	row.add_child(VSeparator.new())
	for app in APPS:
		var key := str(app[0])
		var b := Button.new()
		b.text = str(app[1])
		b.custom_minimum_size = Vector2(78, 0)
		b.pressed.connect(_toggle_win.bind(key))
		row.add_child(b)
		_dock_btns[key] = b
	var spacer := Control.new()
	spacer.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	row.add_child(spacer)
	_taskbar_day = Label.new()
	_taskbar_day.text = "제 1 일 / %d" % _tm.max_turns
	_taskbar_day.add_theme_color_override("font_color", Color(0.75, 0.8, 0.7))
	row.add_child(_taskbar_day)
	var settings_btn := Button.new()
	settings_btn.name = "SettingsButton"
	settings_btn.text = "소리"
	settings_btn.pressed.connect(_toggle_settings)
	row.add_child(settings_btn)
	_update_taskbar_state()

## 바탕화면 아이콘(좌측 1열). 창이 위를 덮는 건 실제 OS 와 같다 — 태스크바로도 열 수 있다.
func _build_desktop_icons(parent: Control) -> void:
	var y := 12.0
	for app in APPS:
		var key := str(app[0])
		var icon := _desk_button(str(app[2]), 44)
		icon.custom_minimum_size = Vector2(52, 44)
		icon.position = Vector2(20, y)
		icon.add_theme_font_size_override("font_size", 22)
		icon.tooltip_text = str(app[1])
		icon.pressed.connect(_toggle_win.bind(key))
		parent.add_child(icon)
		var lb := Label.new()
		lb.text = str(app[1])
		lb.position = Vector2(4, y + 46)
		lb.custom_minimum_size = Vector2(84, 0)
		lb.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
		lb.add_theme_font_size_override("font_size", 13)
		lb.add_theme_color_override("font_color", Color(0.72, 0.82, 0.72))
		lb.mouse_filter = Control.MOUSE_FILTER_IGNORE
		parent.add_child(lb)
		y += 96.0

## 태스크바 클릭: 닫힘/내려짐 → 열기, 열려 있으면 → 내리기(실제 OS 태스크바와 동일).
func _toggle_win(key: String) -> void:
	var w := _windows.get(key) as PanelContainer
	if w == null:
		return
	if w.visible:
		_close_window(w, true)
	else:
		_open_win(key)

## 창을 열고 앞으로. 팝 인 연출 + 메일이면 읽음 처리(배지 해제).
func _open_win(key: String) -> void:
	var w := _windows.get(key) as PanelContainer
	if w == null:
		return
	w.visible = true
	w.move_to_front()
	w.pivot_offset = w.size * 0.5
	w.scale = Vector2(0.95, 0.95)
	var tw := create_tween()
	tw.tween_property(w, "scale", Vector2.ONE, 0.16) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	if _booted:
		window_opened.emit()
	if key == "mail":
		_mail_unread = 0
		_update_mail_badge()
	_update_taskbar_state()

## 창 숨기기. minimized=true 면 「내려짐」(◌, 작업 유지 상태), false 면 「닫힘」.
## 둘 다 태스크바에서 다시 열 수 있지만, 태스크바 표시가 다르다.
func _close_window(panel: PanelContainer, minimized: bool = false) -> void:
	panel.visible = false
	panel.set_meta("minimized", minimized)
	if _booted:
		window_closed.emit()
	_update_taskbar_state()

## 태스크바 상태 표기: ● 열림(밝음) / ◌ 내려짐(중간) / 표시 없음 닫힘(어둡게).
func _update_taskbar_state() -> void:
	for key in _dock_btns:
		var b := _dock_btns[key] as Button
		var w := _windows.get(key) as PanelContainer
		if w == null:
			continue
		var label := _app_label(str(key))
		if w.visible:
			b.text = "● " + label
			b.modulate = Color(1, 1, 1)
		elif bool(w.get_meta("minimized", false)):
			b.text = "◌ " + label
			b.modulate = Color(0.85, 0.88, 0.82)
		else:
			b.text = label
			b.modulate = Color(0.6, 0.64, 0.6)
	_apply_mail_badge()

func _app_label(key: String) -> String:
	for app in APPS:
		if str(app[0]) == key:
			return str(app[1])
	return key

## 메일 미읽음 배지는 상태 표기 위에 덧입힌다(개수 + 주황 강조).
func _apply_mail_badge() -> void:
	var b := _dock_btns.get("mail") as Button
	if b != null and _mail_unread > 0:
		b.text += "(%d)" % _mail_unread
		b.modulate = Color(1.0, 0.85, 0.6)

func _update_mail_badge() -> void:
	_update_taskbar_state()

# ---------- 메일 앱 (편집장·압박·분기 메시지 수신함) ----------
func _make_mail(pos: Vector2, size: Vector2) -> PanelContainer:
	var panel := _window(pos, size, "수신함 — 치차 석간 내부망")
	_mail_list = _scroll_body(_body_of(panel))
	return panel

## 수신함 맨 위에 메일을 꽂는다. 수신함이 닫혀 있으면 독에 미읽음 배지.
func _push_mail(sender: String, subject: String, body: String) -> void:
	if _mail_list == null:
		return
	var row := VBoxContainer.new()
	var head := Label.new()
	head.text = "▸ %s  —  %s" % [subject, sender]
	head.add_theme_color_override("font_color", Color(0.95, 0.8, 0.5))
	head.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	row.add_child(head)
	var b := Label.new()
	b.text = body
	b.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	b.add_theme_color_override("font_color", Color(0.8, 0.82, 0.75))
	row.add_child(b)
	row.add_child(HSeparator.new())
	_mail_list.add_child(row)
	_mail_list.move_child(row, 0)  # 최신이 위
	var w := _windows.get("mail") as PanelContainer
	if w == null or not w.visible:
		_mail_unread += 1
		_update_mail_badge()

## Win98 풍 슬림 창 크롬 × 디젤펑크 팔레트. 두꺼운 브라스 9-slice(내용 여백 46~70px)가
## 정보 면적을 다 먹던 문제를 해소: 얇은 베벨(2px) + 타이틀바(제목 + 실제 ▁/✕ 버튼).
## extra_top 은 구 프레임 시절 호환 인자(무시).
func _window(pos: Vector2, size: Vector2, title: String, _extra_top: float = 0.0) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = pos
	panel.custom_minimum_size = size
	panel.size = size
	panel.clip_contents = true
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.11, 0.095, 0.075)      # 바켈라이트 면
	sb.border_color = Color(0.58, 0.45, 0.24)    # 브라스 베벨
	sb.set_border_width_all(2)
	sb.set_corner_radius_all(2)
	sb.set_content_margin_all(4)
	sb.shadow_color = Color(0, 0, 0, 0.5)
	sb.shadow_size = 6
	panel.add_theme_stylebox_override("panel", sb)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 4)
	panel.add_child(vb)
	# 타이틀바: Win98 처럼 좌측 제목 + 우측 내리기/닫기. 바 배경 클릭은 패널로 통과(드래그).
	var bar := PanelContainer.new()
	bar.mouse_filter = Control.MOUSE_FILTER_IGNORE
	var bsb := StyleBoxFlat.new()
	bsb.bg_color = Color(0.32, 0.22, 0.10)       # 어두운 브라스 타이틀바
	bsb.border_color = Color(0.62, 0.48, 0.26)
	bsb.border_width_bottom = 1
	bsb.set_corner_radius_all(1)
	bsb.content_margin_left = 8.0
	bsb.content_margin_right = 3.0
	bsb.content_margin_top = 2.0
	bsb.content_margin_bottom = 2.0
	bar.add_theme_stylebox_override("panel", bsb)
	vb.add_child(bar)
	var bar_row := HBoxContainer.new()
	bar_row.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar_row.add_theme_constant_override("separation", 3)
	bar.add_child(bar_row)
	var t := Label.new()
	t.text = "▍ " + title
	t.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	t.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	t.mouse_filter = Control.MOUSE_FILTER_IGNORE
	bar_row.add_child(t)
	var min_b := _chrome_button("▁")
	min_b.tooltip_text = "내리기"
	min_b.pressed.connect(func() -> void: _close_window(panel, true))
	bar_row.add_child(min_b)
	var x_b := _chrome_button("✕")
	x_b.tooltip_text = "닫기"
	x_b.pressed.connect(func() -> void: _close_window(panel, false))
	bar_row.add_child(x_b)
	# 본문: 얇은 여백만 두고 내용에 면적을 최대로 준다.
	var body_wrap := MarginContainer.new()
	body_wrap.add_theme_constant_override("margin_left", 6)
	body_wrap.add_theme_constant_override("margin_right", 6)
	body_wrap.add_theme_constant_override("margin_top", 2)
	body_wrap.add_theme_constant_override("margin_bottom", 6)
	body_wrap.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(body_wrap)
	var body := VBoxContainer.new()
	body_wrap.add_child(body)
	panel.set_meta("body", body)
	panel.set_meta("title_label", t)  # 타이틀 갱신용(예: 정보원 오늘/누적 카운트)
	# OS 창답게: 클릭하면 앞으로, 타이틀바를 잡으면 드래그.
	panel.gui_input.connect(_window_gui_input.bind(panel))
	return panel

## 타이틀바용 소형 브라스 버튼(Win98 의 _ X 에 해당).
func _chrome_button(txt: String) -> Button:
	var b := Button.new()
	b.text = txt
	b.custom_minimum_size = Vector2(26, 20)
	b.focus_mode = Control.FOCUS_NONE
	var base := StyleBoxFlat.new()
	base.bg_color = Color(0.55, 0.44, 0.26)
	base.border_color = Color(0.82, 0.68, 0.42)
	base.set_border_width_all(1)
	base.set_corner_radius_all(1)
	var hover := base.duplicate() as StyleBoxFlat
	hover.bg_color = Color(0.68, 0.54, 0.32)
	var pressed := base.duplicate() as StyleBoxFlat
	pressed.bg_color = Color(0.38, 0.30, 0.18)
	b.add_theme_stylebox_override("normal", base)
	b.add_theme_stylebox_override("hover", hover)
	b.add_theme_stylebox_override("pressed", pressed)
	b.add_theme_color_override("font_color", Color(0.10, 0.08, 0.05))
	b.add_theme_font_size_override("font_size", 12)
	return b

func _window_gui_input(ev: InputEvent, panel: PanelContainer) -> void:
	if ev is InputEventMouseButton:
		var mb := ev as InputEventMouseButton
		if mb.button_index == MOUSE_BUTTON_LEFT:
			if mb.pressed:
				panel.move_to_front()
				# 내리기/닫기는 타이틀바의 실제 ▁/✕ 버튼이 처리한다(버튼이 클릭을 소비).
				if mb.position.y <= 28.0:  # 타이틀바 영역만 드래그 시작
					panel.set_meta("dragging", true)
			else:
				panel.set_meta("dragging", false)
	elif ev is InputEventMouseMotion and bool(panel.get_meta("dragging", false)):
		var area: Vector2 = (panel.get_parent() as Control).size  # 유리면(ScreenOS) 안으로 제한
		var p: Vector2 = panel.position + (ev as InputEventMouseMotion).relative
		p.x = clampf(p.x, -panel.size.x + 80.0, area.x - 80.0)
		p.y = clampf(p.y, 0.0, area.y - 70.0)
		panel.position = p

## 크롬 없는 위젯(여론계)용 드래그: 전체가 손잡이, 닫기 존 없음(태스크바로만 내림).
func _widget_drag_input(ev: InputEvent, panel: PanelContainer) -> void:
	if ev is InputEventMouseButton and (ev as InputEventMouseButton).button_index == MOUSE_BUTTON_LEFT:
		panel.set_meta("dragging", (ev as InputEventMouseButton).pressed)
		if (ev as InputEventMouseButton).pressed:
			panel.move_to_front()
	elif ev is InputEventMouseMotion and bool(panel.get_meta("dragging", false)):
		var area: Vector2 = (panel.get_parent() as Control).size
		var p: Vector2 = panel.position + (ev as InputEventMouseMotion).relative
		p.x = clampf(p.x, 0.0, area.x - panel.size.x)
		p.y = clampf(p.y, 0.0, area.y - 40.0)
		panel.position = p

func _body_of(panel: Node) -> VBoxContainer:
	return panel.get_meta("body") as VBoxContainer

## 세로 스크롤 영역을 만들어 그 안의 VBox 를 돌려준다. 내용이 창 높이를 넘겨도
## (사실 F1~F16 처럼) 잘려서 사라지지 않고 스크롤로 읽을 수 있게 한다.
func _scroll_body(parent: VBoxContainer) -> VBoxContainer:
	var sc := ScrollContainer.new()
	sc.horizontal_scroll_mode = ScrollContainer.SCROLL_MODE_DISABLED
	sc.size_flags_vertical = Control.SIZE_EXPAND_FILL
	sc.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	parent.add_child(sc)
	var inner := VBoxContainer.new()
	inner.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	sc.add_child(inner)
	return inner

# 정보원: 입수 정보(전부 진실). 유리/불리 태그는 노출하지 않음 — 판단은 플레이어 몫.
func _cur_turn() -> int:
	return _tm.model.turn + 1

## 이번 턴까지 도착한(가용) fact id 목록(등장 순서, 중복 제거). get_blocks = 코어 단일 게이팅 재사용.
func _available_fact_ids() -> Array:
	var out: Array = []
	var seen: Dictionary = {}
	for b in _tm.get_blocks():
		var fid: String = str(b["fact"])
		if not seen.has(fid):
			seen[fid] = true
			out.append(fid)
	return out

## 이 fact 가 '오늘 것'인가 — 정보원/원고에 기본 노출되는 대상.
## 오늘 도착(turn==현재) 또는 숨김 발견형(F15, 발견되면 항상 노출).
func _is_today_fact(fdict: Dictionary, cur_turn: int) -> bool:
	if bool(fdict.get("hidden", false)):
		return true
	return int(fdict.get("turn", 0)) == cur_turn

# 정보원: 오늘 입수한 정보만 보여준다(과부하 방지). 과거 정보는 「받은 자료」 오버레이로.
func _make_informant(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "정보원 — 입수 정보")
	_informant_title = panel.get_meta("title_label") as Label
	var body := _body_of(panel)
	_archive_btn = Button.new()
	_archive_btn.text = "받은 자료"
	_archive_btn.pressed.connect(_toggle_archive)
	body.add_child(_archive_btn)
	_informant_body = _scroll_body(body)
	_refresh_informant()
	return panel

## 정보원 패널을 현재 턴 기준 '가용 사실'만, 오늘/이월 구분해 다시 그린다.
## 가용 사실 = get_blocks() 에 등장하는 fact 집합(코어의 단일 턴 게이팅을 UI가 재사용 —
## hidden F15·gated F16 도 자동 반영). 로직을 UI에 중복하지 않는다.
func _refresh_informant() -> void:
	if _informant_body == null:
		return
	for c in _informant_body.get_children():
		_informant_body.remove_child(c)
		c.free()
	var facts: Dictionary = _tm.content.get("facts", {})
	var cur_turn: int = _cur_turn()
	var today: int = 0
	var carried: int = 0
	for fid in _available_fact_ids():
		var f: Dictionary = facts.get(fid, {})
		if not _is_today_fact(f, cur_turn):
			carried += 1
			continue  # 과거 정보는 정보원 패널이 아니라 「받은 자료」로
		today += 1
		var is_clue: bool = bool(f.get("hidden", false))
		var head := Label.new()
		head.text = "%s  %s" % ["· 단서(책상)" if is_clue else "● 오늘 입수", str(f.get("title", ""))]
		head.add_theme_color_override("font_color", Color(1.0, 0.85, 0.4))
		_informant_body.add_child(head)
		for frag in f.get("fragments", []):
			var l := Label.new()
			l.text = str(frag.get("text", ""))
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			_informant_body.add_child(l)
	if today == 0:
		var none := Label.new()
		none.text = "오늘 새로 들어온 정보가 없습니다."
		none.modulate = Color(0.65, 0.65, 0.6)
		_informant_body.add_child(none)
	if _informant_title != null:
		_informant_title.text = "▍ 정보원 — 오늘 입수 %d" % today
	if _archive_btn != null:
		_archive_btn.text = "받은 자료 (%d)" % carried
		_archive_btn.disabled = carried == 0

# 원고 작성: 각 문장 블록을 넣을지 말지 토글. 필수 없음. 전부 빼면 미보도.
func _make_editor(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "원고 작성", 20.0)
	var vb := _body_of(panel)
	_turn_label = Label.new()
	_turn_label.add_theme_color_override("font_color", Color(0.8, 0.9, 1.0))
	vb.add_child(_turn_label)
	_update_turn_label()
	var hint := Label.new()
	hint.text = "[정보 폴더]의 파일을 이곳에 끌어다 놓아 기사를 구성합니다."
	hint.modulate = Color(0.7, 0.75, 0.7)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(hint)

	# 드롭 영역: 원고지 느낌의 어두운 지면. 폴더 파일을 여기 떨어뜨리면 기사에 실린다.
	var drop_zone := PanelContainer.new()
	drop_zone.name = "DraftDropZone"
	var dsb := StyleBoxFlat.new()
	dsb.bg_color = Color(0.05, 0.045, 0.035)
	dsb.border_color = Color(0.45, 0.38, 0.22)
	dsb.set_border_width_all(1)
	dsb.set_corner_radius_all(3)
	dsb.set_content_margin_all(8)
	drop_zone.add_theme_stylebox_override("panel", dsb)
	drop_zone.size_flags_vertical = Control.SIZE_EXPAND_FILL
	vb.add_child(drop_zone)
	var inner_v := VBoxContainer.new()
	drop_zone.add_child(inner_v)
	_draft_box = _scroll_body(inner_v)
	# 드롭 판정은 커서 바로 아래 컨트롤에 묻으므로, 영역을 이루는 층 전부에 포워딩을 건다.
	for c: Control in [drop_zone, inner_v, _draft_box, _draft_box.get_parent()]:
		_set_drop_target(c)
	_refresh_draft()

	var pub := Button.new()
	pub.text = "발행"
	pub.custom_minimum_size = Vector2(0, 40)
	pub.pressed.connect(_on_publish)
	vb.add_child(pub)
	_pub_button = pub

	# 발행된 기사는 오버레이로 크게 뜬다(원고 창 UI 를 가리지 않게). 여기선 다시 보기 버튼만.
	_article_view_btn = Button.new()
	_article_view_btn.text = "발행 기사 다시 보기"
	_article_view_btn.disabled = true
	_article_view_btn.pressed.connect(_show_article)
	vb.add_child(_article_view_btn)

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

# ---------- 정보 폴더 (수집한 사실 = 파일) ----------
func _make_folder(pos: Vector2, size: Vector2) -> PanelContainer:
	var panel := _window(pos, size, "정보 폴더")
	var vb := _body_of(panel)
	var hint := Label.new()
	hint.text = "파일을 [원고] 창으로 드래그 (더블클릭도 가능)"
	hint.modulate = Color(0.7, 0.75, 0.7)
	hint.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	vb.add_child(hint)
	_folder_box = _scroll_body(vb)
	_refresh_blocks()
	return panel

## 현재 블록 목록에서 id 로 찾기. 없으면 빈 Dictionary.
func _block_by_id(id: String) -> Dictionary:
	for b in _tm.get_blocks():
		if str(b["id"]) == id:
			return b
	return {}

## 드래그 데이터 구성 + 종이 파일 모양 프리뷰.
func _make_drag_data(source: Control, id: String, text: String) -> Dictionary:
	var prev := Label.new()
	prev.text = "▤ " + text.substr(0, 24) + ("…" if text.length() > 24 else "")
	prev.add_theme_color_override("font_color", Color(0.1, 0.09, 0.06))
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.85, 0.8, 0.65, 0.95)  # 갱지
	sb.set_content_margin_all(6)
	var wrap := PanelContainer.new()
	wrap.add_theme_stylebox_override("panel", sb)
	wrap.add_child(prev)
	source.set_drag_preview(wrap)
	return {"type": "gireki_block", "id": id, "text": text}

## 컨트롤을 원고 드롭 대상으로 만든다(드래그 소스는 아님).
func _set_drop_target(c: Control) -> void:
	c.set_drag_forwarding(
		func(_p: Vector2) -> Variant: return null,
		func(_p: Vector2, d: Variant) -> bool:
			return d is Dictionary and str((d as Dictionary).get("type", "")) == "gireki_block",
		func(_p: Vector2, d: Variant) -> void:
			_add_to_draft(str((d as Dictionary).get("id", ""))))

func _add_to_draft(id: String) -> void:
	if id == "" or _draft_ids.has(id) or _block_by_id(id).is_empty():
		return
	_draft_ids.append(id)
	file_dropped.emit()
	_refresh_draft()
	_refresh_blocks()  # 폴더 쪽에 '원고에 실림' 표시 갱신

func _remove_from_draft(id: String) -> void:
	_draft_ids.erase(id)
	_refresh_draft()
	_refresh_blocks()

## 원고(드롭 영역)를 현재 _draft_ids 로 다시 그린다. 비면 안내 문구.
func _refresh_draft() -> void:
	if _draft_box == null:
		return
	for c in _draft_box.get_children():
		_draft_box.remove_child(c)
		c.free()
	if _draft_ids.is_empty():
		var empty := Label.new()
		empty.text = "(빈 원고)\n\n정보 폴더의 파일을 여기로 끌어오세요.\n아무것도 싣지 않고 발행하면 미보도가 됩니다."
		empty.modulate = Color(0.5, 0.5, 0.45)
		empty.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_draft_box.add_child(empty)
		return
	var facts: Dictionary = _tm.content.get("facts", {})
	for id in _draft_ids:
		var b := _block_by_id(str(id))
		if b.is_empty():
			continue
		var row := HBoxContainer.new()
		row.mouse_filter = Control.MOUSE_FILTER_IGNORE  # 드롭 판정이 행에 막히지 않게
		var lb := Label.new()
		var fid: String = str(b["fact"])
		lb.text = "▤ [%s] %s" % [str((facts.get(fid, {}) as Dictionary).get("title", fid)), str(b["text"])]
		lb.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lb.size_flags_horizontal = Control.SIZE_EXPAND_FILL
		lb.mouse_filter = Control.MOUSE_FILTER_IGNORE
		row.add_child(lb)
		var x := Button.new()
		x.text = "✕"
		x.tooltip_text = "원고에서 빼기"
		x.custom_minimum_size = Vector2(30, 26)
		x.pressed.connect(_remove_from_draft.bind(str(id)))
		row.add_child(x)
		_draft_box.add_child(row)

## 정보 폴더를 현재 상태(오늘 입수 + 이월 + F15 발견·F16 개폐)로 다시 그린다.
## 파일 은유: 사실별 그룹 아래 문장 1개 = 파일 1개. 드래그 소스.
func _refresh_blocks() -> void:
	if _folder_box == null:
		return
	for c in _folder_box.get_children():
		_folder_box.remove_child(c)
		c.free()
	var facts: Dictionary = _tm.content.get("facts", {})
	var cur_turn: int = _cur_turn()
	var last_fact := ""
	var shown_any := false
	for b in _tm.get_blocks():
		var fid: String = str(b["fact"])
		var fdict: Dictionary = facts.get(fid, {})
		var is_today: bool = _is_today_fact(fdict, cur_turn)
		# 폴더에는 오늘 것 + 「받은 자료」에서 끌어온 과거 사실만(난잡·과부하 방지).
		if not is_today and not _carryover_selected.has(fid):
			continue
		shown_any = true
		if fid != last_fact:
			last_fact = fid
			var mark: String = "● " if is_today else "↩ 이월 "
			var fh := Label.new()
			fh.text = "%s[%s]" % [mark, str(fdict.get("title", fid))]
			fh.add_theme_color_override("font_color",
				Color(1.0, 0.85, 0.4) if is_today else Color(0.7, 0.8, 0.95))
			_folder_box.add_child(fh)
		var id := str(b["id"])
		var text := str(b["text"])
		var file_btn := Button.new()
		file_btn.alignment = HORIZONTAL_ALIGNMENT_LEFT
		file_btn.clip_text = true
		var in_draft := _draft_ids.has(id)
		file_btn.text = ("✓ " if in_draft else "▤ ") + text
		file_btn.disabled = in_draft  # 이미 실린 파일은 회색 처리
		file_btn.tooltip_text = "원고 창으로 드래그해서 싣기" if not in_draft else "이미 원고에 실림"
		file_btn.set_drag_forwarding(
			(func(_p: Vector2) -> Variant: return _make_drag_data(file_btn, id, text))
				if not in_draft else (func(_p: Vector2) -> Variant: return null),
			func(_p: Vector2, _d: Variant) -> bool: return false,
			func(_p: Vector2, _d: Variant) -> void: pass)
		if not in_draft:
			file_btn.gui_input.connect(func(ev: InputEvent) -> void:
				if ev is InputEventMouseButton and (ev as InputEventMouseButton).double_click:
					_add_to_draft(id))
		_folder_box.add_child(file_btn)
	if not shown_any:
		var none := Label.new()
		none.text = "수집된 정보가 없습니다. [정보원]에서 오늘 입수분을 확인하거나\n「받은 자료」에서 과거 정보를 끌어올 수 있습니다."
		none.modulate = Color(0.65, 0.65, 0.6)
		none.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_folder_box.add_child(none)

func _make_comments(pos: Vector2, size: Vector2) -> Control:
	var panel := _window(pos, size, "댓글")
	_comments_box = _scroll_body(_body_of(panel))  # 댓글이 많아도 스크롤로 접근(삐짐 방지)
	var hint := Label.new()
	hint.text = "발행하면 여론 반응이 달립니다."
	hint.modulate = Color(0.7, 0.7, 0.7)
	_comments_box.add_child(hint)
	return panel

## 여론계: 창 크롬 없이 게이지 아트만 바탕화면에 놓이는 위젯. 드래그로 옮길 수 있고
## 태스크바 [여론계] 로 내리고 올린다.
func _make_gauge_widget(pos: Vector2) -> PanelContainer:
	var panel := PanelContainer.new()
	panel.position = pos
	panel.custom_minimum_size = Vector2(210, 220)
	panel.size = Vector2(210, 220)
	panel.add_theme_stylebox_override("panel", StyleBoxEmpty.new())  # 크롬 없음
	# 위젯 전체가 드래그 손잡이(창 프레임의 X/— 존은 없음).
	panel.gui_input.connect(_widget_drag_input.bind(panel))
	var dial := Control.new()
	dial.custom_minimum_size = Vector2(0, 200)
	dial.size_flags_vertical = Control.SIZE_EXPAND_FILL
	dial.clip_contents = true
	dial.mouse_filter = Control.MOUSE_FILTER_IGNORE  # 클릭이 패널(드래그 핸들러)로 가게
	panel.add_child(dial)
	var tex := _res(GAUGE_TEX)
	if tex != null:
		var tr := TextureRect.new()
		tr.texture = tex
		tr.stretch_mode = TextureRect.STRETCH_KEEP_ASPECT_CENTERED
		# 기본 expand_mode 는 텍스처 원본(512²)을 최소 크기로 요구해 레이아웃을 밀어낸다.
		# IGNORE_SIZE 로 두어야 앵커(FULL_RECT)를 따라 창 안에 맞춰 축소된다.
		tr.expand_mode = TextureRect.EXPAND_IGNORE_SIZE
		tr.set_anchors_and_offsets_preset(Control.PRESET_FULL_RECT)
		tr.mouse_filter = Control.MOUSE_FILTER_IGNORE
		dial.add_child(tr)
	_needle = Line2D.new()
	_needle.width = 3.0
	_needle.default_color = Color(1.0, 0.5, 0.2)
	dial.add_child(_needle)
	# 닉시관 소등 오버레이: 아트의 5개 관 위에 어두운 막을 얹어 '꺼짐'을 표현한다.
	# 켜진 관 수 = 거시 여론 레벨(부정확 계기라 숫자 대신 관 개수로 읽는다).
	_tube_dims.clear()
	for i in 5:
		var dim := ColorRect.new()
		dim.color = Color(0.02, 0.015, 0.01, 0.62)
		dim.mouse_filter = Control.MOUSE_FILTER_IGNORE
		dial.add_child(dim)
		_tube_dims.append(dim)
	# 바늘·관 오버레이를 텍스처 실좌표에 맞춘다. 창 크기가 바뀌어도 따라가도록
	# resized 에 연결한다. 하드코딩 좌표를 쓰면 창 치수를 조금만 건드려도 어긋난다.
	dial.resized.connect(func() -> void: _fit_needle(dial))
	_fit_needle(dial)
	_set_needle(0.5, 0.5)  # 시작: 바늘 수직 + 부동층 0.5 = 관 2.5개
	return panel

## KEEP_ASPECT_CENTERED 로 그려진 정사각 텍스처 안에서 다이얼 축 위치를 계산해
## 바늘의 원점·길이를 맞춘다. (축은 텍스처 기준 가로 50% · 세로 35% 지점)
func _fit_needle(dial: Control) -> void:
	if _needle == null:
		return
	var s: float = minf(dial.size.x, dial.size.y)   # 실제로 그려지는 텍스처 한 변
	var ox: float = (dial.size.x - s) * 0.5
	var oy: float = (dial.size.y - s) * 0.5
	_needle.position = Vector2(ox + s * 0.50, oy + s * 0.35)
	_needle.points = PackedVector2Array([Vector2.ZERO, Vector2(0, -s * 0.20)])
	# 닉시관 5개 위치(512² 아트 실측: 관 행 y≈0.64~0.93, 관 폭≈0.15 간격≈0.165)
	for i in _tube_dims.size():
		var dim := _tube_dims[i] as ColorRect
		dim.position = Vector2(ox + s * (0.10 + 0.163 * i), oy + s * 0.645)
		dim.size = Vector2(s * 0.135, s * 0.27)

## 바늘은 즉시 꺾이지 않는다 — 목표각까지 무겁게 스윙 후 살짝 오버슈트(아날로그 계기).
## 실제 회전은 _process 에서 base + 상시 미세 떨림으로 합성한다(세계관: 부정확한 바늘).
## 갱신 직후엔 동요(_needle_excite)로 떨림이 커졌다가 가라앉는다.
##
## 계기 이원화(플레이테스트 피드백 — 변화가 안 보임):
##  · 바늘   = 거시 여론(tvMacro). 실변동이 ±0.1 수준으로 작아 3배 증폭해 표시
##             (수치 비표시 원칙이라 과장은 허용 — '부정확한 계기'다).
##  · 닉시관 = 미션 바로미터: SNS 부동층 온도. [0.30~0.70]→0~5관 리맵이라
##             턴마다 관 단위로 움직인다. 승리선(0.65)≈4.4관.
func _set_needle(macro: float, swing: float = -1.0) -> void:
	if _needle == null:
		return
	var dev: float = clampf((macro - 0.5) * 3.0, -0.55, 0.55)
	var target: float = deg_to_rad(dev * 110.0)  # 0.5=수직, 우=찬성, 좌=반대
	_needle_excite = 1.0  # 새 여론 반영 = 계기가 크게 흔들린다
	var tw := create_tween()
	tw.tween_property(self, "_needle_rot_base", target, 1.4) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	if swing < 0.0:
		return
	var level: float = clampf(remap(swing, 0.30, 0.70, 0.0, 5.0), 0.0, 5.0)
	for i in _tube_dims.size():
		var lit: float = clampf(level - float(i), 0.0, 1.0)
		var dtw := create_tween()
		dtw.tween_property(_tube_dims[i], "color:a", lerpf(0.62, 0.0, lit), 0.9) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)

func _process(delta: float) -> void:
	if _needle == null or _screen == null or not _screen.visible:
		return
	_needle_excite = maxf(0.0, _needle_excite - delta * 0.35)  # 약 3초에 걸쳐 진정
	# 두 사인파 합성으로 불규칙해 보이는 미세 진동(±0.9°, 동요 시 최대 ±3.5°).
	var t: float = Time.get_ticks_msec() / 1000.0
	var amp: float = 1.0 + 3.0 * _needle_excite
	var jitter: float = (deg_to_rad(0.55) * sin(t * 7.3) + deg_to_rad(0.35) * sin(t * 13.7)) * amp
	_needle.rotation = _needle_rot_base + jitter

# ---------- 발행 ----------
func _on_publish() -> void:
	# 원고 = 드롭해 둔 블록들. 빈 원고 발행 = 미보도.
	var included: Array = []
	var included_texts: Array = []
	for id in _draft_ids:
		var b := _block_by_id(str(id))
		if not b.is_empty():
			included.append(str(id))
			included_texts.append(str(b["text"]))  # 본문 조립용(발행 전 캡처)
	var pub_turn: int = _tm.model.turn + 1  # 발행 대상 턴(publish 가 턴을 올리기 전)
	var det_before: int = _tm.model.detections.size()
	var result := _tm.publish({"included_ids": included})
	article_published.emit()
	if _tm.model.detections.size() > det_before:
		distortion_detected.emit()  # 이번 턴에 왜곡이 새로 들통났다
	_render_comments(result["comments"])
	var snap: Dictionary = result["snapshot"]
	var swing: float = float(snap["xs"]["sns_swing"])
	_set_needle(float(snap["tvMacro"]), swing)
	var reported: Array = result["reported_facts"]
	if not reported.is_empty():
		_article_history.append({
			"reported": reported, "frame": str(result["frame_label"]),
			"body": included_texts, "turn": pub_turn})
		_article_idx = _article_history.size() - 1  # 새 기사를 현재로
		_article_view_btn.disabled = false
		_refresh_article_view()
	var report_txt: String = "미보도" if reported.is_empty() else "보도 %d건" % reported.size()
	_status_label.text = "%s · 논조 %s(δ=%.2f) · 부동층 %d%%" % [
		report_txt, str(result["frame_label"]), float(result["distortion"]), int(round(swing * 100.0)),
	]
	if _pressure_label != null:
		_pressure_label.text = str(result["pressure_hint"])
	if _branch_label != null and str(result["branch_hint"]) != "":
		_branch_label.text = str(result["branch_hint"])
	# 압박·분기는 편집장 명의의 메일로도 도착한다(계기 비표시 원칙 — 수치 없이 문구만).
	if str(result["pressure_hint"]) != "":
		_push_mail("편집장", "위에서 온 이야기", str(result["pressure_hint"]))
	if str(result["branch_hint"]) != "":
		_push_mail("편집장", "참고", str(result["branch_hint"]))
	if bool(result["f16_unlocked"]) and not _f16_shown:
		_f16_shown = true
		_refresh_blocks()  # F16 취재선 열림 → 새 문장 블록 등장
	if bool(result["over"]):
		_show_ending(str(result["ending"]), str(result.get("epilogue", "")))
	else:
		_update_turn_label()
		_carryover_selected.clear()  # 새 턴 = 새 기사: 지난 기사에 끌어온 과거 정보는 초기화
		_draft_ids.clear()           # 원고도 백지에서 시작
		_refresh_informant()  # 이번 턴 오늘 입수 + 받은 자료 개수 갱신
		_refresh_blocks()     # 정보 폴더 = 새 턴 오늘 파일
		_refresh_draft()
		if _archive_panel != null and _archive_panel.visible:
			_refresh_archive()
		# 하루 경과 연출 → 기사 지면 팝 + 여론(댓글) 창 자동 오픈.
		var had_article: bool = not reported.is_empty()
		_show_day_transition(func() -> void:
			if had_article:
				_show_article()
			_open_win("comments"))

func _update_turn_label() -> void:
	if _turn_label != null and _tm != null:
		_turn_label.text = "턴 %d / %d" % [_tm.model.turn + 1, _tm.max_turns]
	if _taskbar_day != null and _tm != null:
		_taskbar_day.text = "제 %d 일 / %d" % [_tm.model.turn + 1, _tm.max_turns]

## 발행된 기사를 [헤드라인] + 본문(포함 블록, 최대 6줄)으로 조립해 카드로 보여준다.
## 헤드라인 = 첫 보도 fact 의 headlines[논조]. 본문 = 플레이어가 실은 문장들(등장 순서).
# ---------- 발행 기사 오버레이 ----------
func _build_article_panel(parent: Control) -> void:
	var panel := PanelContainer.new()
	panel.name = "ArticlePanel"
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH  # 중심에서 대칭으로 자라 정중앙에 오게
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
	panel.custom_minimum_size = Vector2(620, 440)
	var sb := StyleBoxFlat.new()
	sb.bg_color = Color(0.09, 0.08, 0.06, 0.98)
	sb.set_border_width_all(2)
	sb.border_color = Color(0.82, 0.62, 0.28)
	sb.set_corner_radius_all(4)
	sb.set_content_margin_all(18)
	panel.add_theme_stylebox_override("panel", sb)
	var vb := VBoxContainer.new()
	vb.add_theme_constant_override("separation", 8)
	panel.add_child(vb)
	var top := HBoxContainer.new()
	var title := Label.new()
	title.text = "▍ 발행된 기사"
	title.add_theme_color_override("font_color", Color(1.0, 0.82, 0.44))
	title.size_flags_horizontal = Control.SIZE_EXPAND_FILL
	top.add_child(title)
	_article_prev_btn = Button.new()
	_article_prev_btn.text = " < "
	_article_prev_btn.pressed.connect(_article_prev)
	top.add_child(_article_prev_btn)
	_article_nav_label = Label.new()
	_article_nav_label.custom_minimum_size = Vector2(76, 0)
	_article_nav_label.horizontal_alignment = HORIZONTAL_ALIGNMENT_CENTER
	_article_nav_label.add_theme_color_override("font_color", Color(0.8, 0.85, 0.75))
	top.add_child(_article_nav_label)
	_article_next_btn = Button.new()
	_article_next_btn.text = " > "
	_article_next_btn.pressed.connect(_article_next)
	top.add_child(_article_next_btn)
	var x := Button.new()
	x.text = " X "
	x.custom_minimum_size = Vector2(34, 30)
	x.pressed.connect(func() -> void: panel.visible = false)
	top.add_child(x)
	vb.add_child(top)
	vb.add_child(HSeparator.new())
	_article_box = _scroll_body(vb)  # 기사가 길어도 스크롤로 접근
	panel.visible = false
	parent.add_child(panel)
	_article_panel = panel

## 오버레이 높이를 기사 분량에 맞춘다(짧은 기사가 빈 판때기 위에 뜨지 않게).
## 오토랩 라벨의 실높이는 레이아웃 패스 후에 확정되므로 지연 호출로 잰다.
func _fit_article_panel() -> void:
	if _article_panel == null or _article_box == null:
		return
	var content_h: float = _article_box.get_combined_minimum_size().y
	var h: float = clampf(content_h + 92.0, 200.0, 500.0)
	_article_panel.custom_minimum_size = Vector2(620, h)
	_article_panel.size = Vector2(620, h)
	_article_panel.pivot_offset = _article_panel.size * 0.5

## 현재 인덱스의 기사를 다시 그리고 < > · 카운터 상태를 갱신한다.
func _refresh_article_view() -> void:
	if _article_idx < 0 or _article_idx >= _article_history.size():
		return
	var e: Dictionary = _article_history[_article_idx]
	_render_article(e["reported"], str(e["frame"]), e["body"])
	call_deferred("_fit_article_panel")
	if _article_nav_label != null:
		_article_nav_label.text = "T%d · %d/%d" % [int(e["turn"]), _article_idx + 1, _article_history.size()]
	if _article_prev_btn != null:
		_article_prev_btn.disabled = _article_idx <= 0
	if _article_next_btn != null:
		_article_next_btn.disabled = _article_idx >= _article_history.size() - 1

func _article_prev() -> void:
	if _article_idx > 0:
		_article_idx -= 1
		_refresh_article_view()

func _article_next() -> void:
	if _article_idx < _article_history.size() - 1:
		_article_idx += 1
		_refresh_article_view()

## 발행 기사 오버레이를 연다(발행 자동 + "다시 보기" 버튼). 현재 인덱스 기사를 보여준다.
## 신문이 책상에 놓이듯 살짝 커지며 등장(팝 인).
func _show_article() -> void:
	if _article_panel == null:
		return
	_refresh_article_view()
	_article_panel.visible = true
	_article_panel.move_to_front()
	_article_panel.pivot_offset = _article_panel.size * 0.5
	_article_panel.scale = Vector2(0.92, 0.92)
	_article_panel.modulate = Color(1, 1, 1, 0)
	var tw := create_tween()
	tw.set_parallel(true)
	tw.tween_property(_article_panel, "scale", Vector2.ONE, 0.22) \
		.set_trans(Tween.TRANS_BACK).set_ease(Tween.EASE_OUT)
	tw.tween_property(_article_panel, "modulate:a", 1.0, 0.16)

## prose 문단의 첫 문장만 뽑는다(보조 사실 요약용). "다." 로 끝나는 첫 문장 기준.
func _first_sentence(s: String) -> String:
	var idx: int = s.find("다.")
	return s.substr(0, idx + 2) if idx >= 0 else s

func _render_article(reported: Array, frame_label: String, body_lines: Array) -> void:
	if _article_box == null:
		return
	for c in _article_box.get_children():
		c.queue_free()
	if reported.is_empty():
		var none := Label.new()
		none.text = "(미보도 — 이번 턴 기사를 싣지 않았다)"
		none.modulate = Color(0.72, 0.72, 0.62)
		none.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		_article_box.add_child(none)
		return
	var facts: Dictionary = _tm.content.get("facts", {})
	# 대표(리드) 사실 = 프레임 헤드라인을 가진 첫 보도 사실.
	var lead_fid := str(reported[0])
	for fid in reported:
		if ((facts.get(fid, {}) as Dictionary).get("headlines", {}) as Dictionary).has(frame_label):
			lead_fid = str(fid); break
	var lf: Dictionary = facts.get(lead_fid, {})
	var lhs: Dictionary = lf.get("headlines", {})
	var headline: String = str(lhs[frame_label]) if lhs.has(frame_label) else str(lf.get("title", ""))
	var head := Label.new()
	head.text = "「%s」" % headline
	head.add_theme_color_override("font_color", Color(1.0, 0.86, 0.5))
	head.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
	_article_box.add_child(head)
	_article_box.add_child(HSeparator.new())
	# 본문: 리드 사실 prose + 보조 사실도 문단 전체(최대 2건) + 나머지는 단신 한 줄.
	# 문단 수가 늘어 '전문'답게 읽힌다. prose 없으면 블록 나열 폴백.
	var lbodies: Dictionary = lf.get("bodies", {})
	if lbodies.has(frame_label):
		var lead := Label.new()
		lead.text = str(lbodies[frame_label])
		lead.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		lead.add_theme_color_override("font_color", Color(0.88, 0.9, 0.82))
		_article_box.add_child(lead)
		var full_paras := 0
		var briefs := 0
		for fid in reported:
			if str(fid) == lead_fid:
				continue
			var fb: Dictionary = (facts.get(fid, {}) as Dictionary).get("bodies", {})
			if not fb.has(frame_label):
				continue
			if full_paras < 2:
				var sp := Label.new()
				sp.text = str(fb[frame_label])
				sp.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				sp.add_theme_color_override("font_color", Color(0.8, 0.83, 0.76))
				_article_box.add_child(sp)
				full_paras += 1
			elif briefs < 2:
				var sl := Label.new()
				sl.text = "— 한편, " + _first_sentence(str(fb[frame_label]))
				sl.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
				sl.add_theme_color_override("font_color", Color(0.68, 0.72, 0.66))
				_article_box.add_child(sl)
				briefs += 1
	else:
		var shown: int = mini(body_lines.size(), 6)
		for i in shown:
			var l := Label.new()
			l.text = "  " + str(body_lines[i])
			l.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
			l.add_theme_color_override("font_color", Color(0.85, 0.88, 0.8))
			_article_box.add_child(l)
		if body_lines.size() > shown:
			var more := Label.new()
			more.text = "  …외 %d줄" % (body_lines.size() - shown)
			more.modulate = Color(0.6, 0.6, 0.55)
			_article_box.add_child(more)

func _show_ending(ending: String, epi: String = "") -> void:
	ending_reached.emit()
	if _pub_button != null:
		_pub_button.disabled = true
	var panel := PanelContainer.new()
	panel.name = "EndingOverlay"
	panel.set_anchors_and_offsets_preset(Control.PRESET_CENTER)
	panel.grow_horizontal = Control.GROW_DIRECTION_BOTH  # 중심에서 대칭으로 자라 정중앙에 오게
	panel.grow_vertical = Control.GROW_DIRECTION_BOTH
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
		# 엔딩은 갑자기 박히지 않고 무겁게 떠오른다(페이드 + 미세 상승).
		panel.modulate = Color(1, 1, 1, 0)
		var tw := create_tween()
		tw.tween_property(panel, "modulate:a", 1.0, 0.8) \
			.set_trans(Tween.TRANS_QUAD).set_ease(Tween.EASE_OUT)

## 세그먼트 페르소나에 맞는 랜덤 핸들. 같은 base 도 숫자 접미(약 70%)로 변주.
func _comment_handle(seg: String) -> String:
	var pool: Array = HANDLE_POOLS.get(seg, HANDLE_FALLBACK)
	if pool.is_empty():
		pool = HANDLE_FALLBACK
	var base: String = str(pool[randi() % pool.size()])
	if randf() < 0.7:
		base += str(randi() % 89 + 11)  # 11~99
	return "@" + base

## 댓글 텍스트의 {슬롯}을 topic 기준으로 채운다. 값이 없으면 SLOT_FALLBACK 으로
## 대체해 "{대상}" 같은 리터럴이 화면에 노출되지 않게 한다.
func _fill_slots(text: String, topic_v: Variant) -> String:
	if not text.contains("{"):
		return text
	var topic: String = "" if topic_v == null else str(topic_v)
	var m: Dictionary = COMMENT_SLOTS.get(topic, {})
	for key in ["키워드", "대상", "수치", "집단"]:
		if text.contains("{" + key + "}"):
			var val: String = str(m.get(key, SLOT_FALLBACK.get(key, "")))
			text = text.replace("{" + key + "}", val)
	return text

func _render_comments(comments: Array) -> void:
	for c in _comments_box.get_children():
		c.queue_free()
	if comments.is_empty():
		var none := Label.new()
		none.text = "…반응이 뜸하다."
		none.modulate = Color(0.6, 0.6, 0.6)
		_comments_box.add_child(none)
		return
	# 댓글이 "실시간으로 달리는" 느낌: 한꺼번에 뜨지 않고 0.35초 간격으로 순차 등장.
	var tw := create_tween()
	tw.set_parallel(true)
	var i: int = 0
	for c in comments:
		var row := VBoxContainer.new()
		# 찌라시(NPC 자생 허위 소문)는 일반 반응과 구분해 보여준다. 세계 규칙상
		# 플레이어가 다루는 정보는 전부 진실이고, 거짓은 여기서만 나온다.
		# spec: docs/specs/rumor_emergence.md
		var rumor: String = str(c.get("rumor", ""))
		var lv: int = int(c.get("level", 0))
		var handle := Label.new()
		if rumor != "":
			handle.text = "%s  ⚠ 확인되지 않은 이야기" % _comment_handle(str(c.get("seg", "")))
			# 단계가 셀수록 붉게 — 확신형(3)은 명백한 허위라 가장 눈에 띈다.
			handle.add_theme_color_override("font_color",
				Color(0.95, 0.62, 0.35) if lv < 3 else Color(1.0, 0.42, 0.35))
		else:
			handle.text = _comment_handle(str(c.get("seg", "")))
			handle.add_theme_color_override("font_color", Color(0.62, 0.78, 0.95))
		row.add_child(handle)
		var body := Label.new()
		body.text = _fill_slots(str(c.get("text", "")), c.get("topic"))
		body.autowrap_mode = TextServer.AUTOWRAP_WORD_SMART
		if rumor != "":
			body.add_theme_color_override("font_color",
				Color(0.92, 0.80, 0.62) if lv < 3 else Color(1.0, 0.72, 0.62))
		row.add_child(body)
		var spacer := Control.new()
		spacer.custom_minimum_size = Vector2(0, 6)
		row.add_child(spacer)
		row.modulate = Color(1, 1, 1, 0)
		_comments_box.add_child(row)
		tw.tween_property(row, "modulate:a", 1.0, 0.3).set_delay(0.15 + i * 0.35)
		i += 1
