extends SceneTree
## play 트랙 스모크 테스트 (SceneTree 스크립트).
##
## 실행: godot --headless --path <repo> --script res://pipeline/tests/smoke_test.gd
##
## 단계적 설계 — 프로젝트가 아직 씬이 없어도 의미 있게 동작한다:
##   1) 엔진/프로젝트가 로드돼 이 스크립트가 실행됨 = 임포트/부트 무결성 확인
##   2) main_scene 이 설정돼 있으면 로드→인스턴스화까지 무결성 확인, 없으면 SKIP
##
## play build 가 첫 씬을 만들고 main_scene 을 설정하면, 재실행만으로 2단계가
## 자동 활성화된다. 장르/스타일 의존 로직은 없다(파이프라인 범용 유지).
##
## 결과: 마지막 줄에 SMOKE_RESULT: PASS | FAIL 를 출력하고 종료 코드로도 알린다.

func _initialize() -> void:
	var failures: int = 0
	print("== play smoke test ==")
	print("Godot: %s" % Engine.get_version_info().get("string", "unknown"))

	var main_scene_path: String = ""
	if ProjectSettings.has_setting("application/run/main_scene"):
		main_scene_path = str(ProjectSettings.get_setting("application/run/main_scene"))

	if main_scene_path == "":
		print("[SKIP] main_scene 미설정 — 부트/임포트 단계만 검증 (씬 생성 전 단계)")
	else:
		print("[..] main_scene 로드 시도: %s" % main_scene_path)
		if not ResourceLoader.exists(main_scene_path):
			print("[FAIL] main_scene 파일 없음: %s" % main_scene_path)
			failures += 1
		else:
			var packed: Resource = load(main_scene_path)
			if packed == null or not (packed is PackedScene):
				print("[FAIL] main_scene 이 PackedScene 로 로드되지 않음")
				failures += 1
			else:
				var inst: Node = (packed as PackedScene).instantiate()
				if inst == null:
					print("[FAIL] main_scene 인스턴스화 실패")
					failures += 1
				else:
					print("[PASS] main_scene 인스턴스화 성공: %s" % inst.name)
					inst.free()

	if failures > 0:
		print("SMOKE_RESULT: FAIL (%d)" % failures)
		quit(1)
	else:
		print("SMOKE_RESULT: PASS")
		quit(0)
