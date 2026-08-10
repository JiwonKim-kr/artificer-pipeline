extends SceneTree
## 앰비언트 베드(BGM) 상태 전환 검증 — 타이틀→데스크→CRT→데스크→엔딩.
## 실행: godot --headless --path <repo> --script res://pipeline/tests/bgm_flow_test.gd
## 결과: 마지막 줄 BGM_RESULT: PASS | FAIL.
##
## ⚠ 대기는 프레임이 아니라 create_timer(실시간)로 한다. 헤드리스는 프레임 루프가
## 실시간보다 훨씬 빨리 돌아서 await process_frame 을 아무리 반복해도 트윈이 끝나지
## 않고, _transitioning 가드에 막혀 전환이 없는 것처럼 보인다(실제로는 정상).

func _initialize() -> void:
	var fails: int = 0
	print("== bgm flow test ==")
	var main = load("res://scenes/main.tscn").instantiate()
	root.add_child(main)
	await process_frame
	await process_frame

	var p = main.find_child("BgmPlayer", true, false)
	if p == null:
		print("[FAIL] BgmPlayer 노드 없음")
		print("BGM_RESULT: FAIL (1)")
		quit(1)
		return
	if str(p.bus) != "BGM":
		print("[FAIL] BgmPlayer 버스가 BGM 이 아님: %s" % str(p.bus)); fails += 1
	else:
		print("[PASS] BgmPlayer 생성 · bus=BGM")

	# 웹은 첫 사용자 제스처 전 오디오를 막는다. 타이틀에서 미리 틀면 그냥 안 나온다.
	if p.playing:
		print("[FAIL] 타이틀에서 이미 재생 중 — 웹에서 차단된다"); fails += 1
	else:
		print("[PASS] 타이틀에서는 미재생 (첫 제스처 대기)")

	main._start_game()
	await create_timer(1.4).timeout
	if main._bgm_track != main.BGM_ROOM or not p.playing:
		print("[FAIL] 타이틀 클릭 후 room 미재생 (track=%s playing=%s)" % [
			main._bgm_track, str(p.playing)]); fails += 1
	elif not bool(p.stream.loop):
		print("[FAIL] room 루프 미설정 — 30초 뒤 정적"); fails += 1
	else:
		print("[PASS] 타이틀 클릭 → room_ambient 재생 · loop=true")

	main._enter_screen()
	await create_timer(2.2).timeout
	if main._bgm_track != main.BGM_JAZZ or not p.playing:
		print("[FAIL] 모니터 진입 후 평시 재즈 미전환 (track=%s)" % main._bgm_track); fails += 1
	elif not bool(p.stream.loop):
		print("[FAIL] 평시 재즈 루프 미설정"); fails += 1
	else:
		print("[PASS] 모니터 진입 → jazz_calm 전환 · loop=true")

	# 위기 전환: 트리거 전에는 평시 유지, 편집장 tier2+ 면 위기, 그 뒤 되돌아가지 않는다.
	main._mark_crisis(1)
	if main._crisis:
		print("[FAIL] tier1 인데 위기 진입"); fails += 1
	else:
		print("[PASS] 위기 미진입: 편집장 tier1(경고 창)은 트리거 아님")
	main._mark_crisis(2)
	main._play_bgm(main._crt_bgm())
	await create_timer(1.6).timeout
	if not main._crisis or main._bgm_track != main.BGM_CRISIS:
		print("[FAIL] tier2 인데 위기 곡 미전환 (crisis=%s track=%s)" % [
			str(main._crisis), main._bgm_track]); fails += 1
	elif not bool(p.stream.loop):
		print("[FAIL] 위기 곡 루프 미설정"); fails += 1
	else:
		print("[PASS] 편집장 tier2 → jazz_crisis 전환 · loop=true")
	# 편도: 이후 어떤 판정이 와도 평시로 돌아가지 않는다(숨긴 수치 누출 방지).
	main._mark_crisis(0)
	if not main._crisis or main._crt_bgm() != main.BGM_CRISIS:
		print("[FAIL] 위기 진입 후 평시로 역행"); fails += 1
	else:
		print("[PASS] 편도 유지: 위기 진입 후 평시 복귀 없음")

	# 같은 트랙 재요청에 재시작하면 상태를 오갈 때마다 곡이 툭툭 끊긴다.
	var before: float = p.get_playback_position()
	main._play_bgm(main._crt_bgm())
	await create_timer(0.3).timeout
	if p.get_playback_position() < before:
		print("[FAIL] 같은 트랙 재요청에 재시작됨"); fails += 1
	else:
		print("[PASS] 같은 트랙 재요청은 무시(끊김 없음)")

	main._exit_screen()
	await create_timer(1.6).timeout
	if main._bgm_track != main.BGM_ROOM:
		print("[FAIL] 모니터 이탈 후 room 미복귀 (track=%s)" % main._bgm_track); fails += 1
	else:
		print("[PASS] 모니터 이탈 → room_ambient 복귀")

	main._stop_bgm(0.3)
	await create_timer(0.9).timeout
	if p.playing:
		print("[FAIL] 엔딩 페이드아웃 후에도 재생 중"); fails += 1
	else:
		print("[PASS] 엔딩 → 페이드아웃 정지")

	if fails == 0:
		print("BGM_RESULT: PASS")
		quit(0)
	else:
		print("BGM_RESULT: FAIL (%d)" % fails)
		quit(1)
