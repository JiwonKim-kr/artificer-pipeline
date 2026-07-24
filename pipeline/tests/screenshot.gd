extends SceneTree
## play 트랙 시각 검증 — 메인 씬(또는 인자 씬)을 렌더해 PNG 스크린샷을 저장한다.
##
## 실행(비-headless + 실제 렌더 드라이버 필수):
##   godot --path <repo> --rendering-driver opengl3 \
##         --script res://pipeline/tests/screenshot.gd \
##         -- --output <PNG경로> [--scene res://scenes/xxx.tscn] [--frames N]
##
## 왜 --headless 가 아닌가: 순수 headless 는 더미 렌더 드라이버라
## get_texture().get_image() 가 렌더 결과를 못 얻고 무한 대기한다.
## macOS 는 GUI 세션이라 창이 잠깐 뜨고, Linux CI 는 xvfb 가상 디스플레이가 필요하다.
##
## 읽기 전용 관찰: 씬을 로드해 add_child → 몇 프레임 렌더 → 뷰포트 캡처만 한다.
## 게임 로직/데이터를 수정하지 않는다. 카메라가 없어도 루트 뷰포트를 그대로 캡처한다.
##
## 출력 마커(러너가 파싱):
##   SHOT_SIZE:<W>x<H>       캡처 이미지 해상도
##   SHOT_DISTINCT:<n>       샘플에서 관측된 서로 다른 색 수(1 이면 단색=빈 렌더 의심)
##   SHOT_NONBLANK:true|false 비-단색 여부(엔진이 디코드한 픽셀 기준, 1차 판정)
##   SHOT_SAVED:<경로>       저장 성공 경로 (성공의 최종 신호)
##   SHOT_ERROR:<메시지>     실패 사유
## 종료 코드: 0 = 저장 성공, 1 = 실패.

var _output_path: String = ""
var _scene_path: String = ""
var _frames_to_wait: int = 12
var _frames_waited: int = 0
var _instance: Node = null
var _finished: bool = false


func _initialize() -> void:
	print("== play screenshot ==")
	print("Godot: %s" % Engine.get_version_info().get("string", "unknown"))
	_parse_args()

	if _scene_path == "":
		if ProjectSettings.has_setting("application/run/main_scene"):
			_scene_path = str(ProjectSettings.get_setting("application/run/main_scene"))

	if _scene_path == "":
		_fail("대상 씬이 없습니다 (main_scene 미설정, --scene 도 없음).")
		return
	if _output_path == "":
		_fail("--output <PNG경로> 인자가 필요합니다.")
		return

	print("[..] 씬 로드: %s" % _scene_path)
	if not ResourceLoader.exists(_scene_path):
		_fail("씬 파일 없음: %s" % _scene_path)
		return
	var packed: Resource = load(_scene_path)
	if packed == null or not (packed is PackedScene):
		_fail("씬이 PackedScene 으로 로드되지 않음: %s" % _scene_path)
		return
	_instance = (packed as PackedScene).instantiate()
	if _instance == null:
		_fail("씬 인스턴스화 실패: %s" % _scene_path)
		return
	get_root().add_child(_instance)
	print("[..] 인스턴스 추가됨: %s — %d 프레임 렌더 대기" % [_instance.name, _frames_to_wait])


## SceneTree._process: true 를 반환하면 메인 루프가 종료된다.
## 렌더가 실제로 일어나려면 프레임을 넘겨야 하므로 프레임 카운트로 안정화한다.
func _process(_delta: float) -> bool:
	if _finished:
		return true
	if _instance == null:
		# _initialize 에서 이미 실패 처리(quit 예약)됨.
		return true
	_frames_waited += 1
	if _frames_waited < _frames_to_wait:
		return false
	_capture_and_save()
	_finished = true
	return true


func _capture_and_save() -> void:
	var vp: Viewport = get_root()
	var tex: Texture2D = vp.get_texture()
	if tex == null:
		_fail("뷰포트 텍스처를 얻지 못함 (렌더 드라이버가 dummy/headless 일 수 있음).")
		return
	var img: Image = tex.get_image()
	if img == null or img.get_width() == 0 or img.get_height() == 0:
		_fail("뷰포트 이미지를 얻지 못함 (빈 렌더).")
		return

	var w: int = img.get_width()
	var h: int = img.get_height()
	print("SHOT_SIZE:%dx%d" % [w, h])

	# 엔진이 디코드한 픽셀로 1차 비-단색 판정(격자 샘플, 장르 무관).
	var distinct: int = _count_distinct_sample(img)
	print("SHOT_DISTINCT:%d" % distinct)
	print("SHOT_NONBLANK:%s" % ("true" if distinct > 1 else "false"))

	var abs_out: String = ProjectSettings.globalize_path(_output_path) if _output_path.begins_with("res://") else _output_path
	# 저장 디렉토리 보장
	var dir_path: String = abs_out.get_base_dir()
	if dir_path != "" and not DirAccess.dir_exists_absolute(dir_path):
		DirAccess.make_dir_recursive_absolute(dir_path)

	var err: int = img.save_png(abs_out)
	if err != OK:
		_fail("save_png 실패 (err=%d) → %s" % [err, abs_out])
		return
	print("SHOT_SAVED:%s" % abs_out)
	_cleanup()
	quit(0)


## 격자 샘플로 서로 다른 색 개수를 센다(최대 ~다수에서 조기 종료).
## 전체 픽셀 순회를 피하되 작은 스프라이트도 놓치지 않도록 촘촘히 본다.
func _count_distinct_sample(img: Image) -> int:
	var w: int = img.get_width()
	var h: int = img.get_height()
	var step_x: int = maxi(1, w / 128)
	var step_y: int = maxi(1, h / 128)
	var seen: Dictionary = {}
	var y: int = 0
	while y < h:
		var x: int = 0
		while x < w:
			var c: Color = img.get_pixel(x, y)
			var key: int = c.to_rgba32()
			seen[key] = true
			if seen.size() > 8:
				return seen.size()  # 충분히 다채로움 — 조기 종료
			x += step_x
		y += step_y
	return seen.size()


func _parse_args() -> void:
	var args: PackedStringArray = OS.get_cmdline_user_args()
	var i: int = 0
	while i < args.size():
		var a: String = args[i]
		if a == "--output" and i + 1 < args.size():
			_output_path = args[i + 1]
			i += 2
		elif a == "--scene" and i + 1 < args.size():
			_scene_path = args[i + 1]
			i += 2
		elif a == "--frames" and i + 1 < args.size():
			_frames_to_wait = maxi(1, args[i + 1].to_int())
			i += 2
		else:
			i += 1


func _cleanup() -> void:
	if _instance != null and is_instance_valid(_instance):
		_instance.free()
		_instance = null


func _fail(msg: String) -> void:
	print("SHOT_ERROR:%s" % msg)
	_cleanup()
	quit(1)
