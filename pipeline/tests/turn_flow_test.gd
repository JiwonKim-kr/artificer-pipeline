extends SceneTree
## 1턴 흐름(turn_manager) 헤드리스 테스트 — 문장 블록 취사 → 기울기·δ → step.
## 실행: godot --headless --path <repo> --script res://pipeline/tests/turn_flow_test.gd
## 결과: 마지막 줄 TURN_RESULT: PASS | FAIL. spec: docs/specs/turn_loop_vertical_slice.md

const EPS := 1e-9

func _initialize() -> void:
	var failures: int = 0
	print("== turn flow test ==")

	var tm := TurnManager.new(1)
	if tm.content.is_empty() or tm.tuning.is_empty():
		print("[FAIL] content_slice / lever_tuning 로드 실패")
		print("TURN_RESULT: FAIL (1)")
		quit(1)
		return

	var all_ids: Array = []
	var non_unf_ids: Array = []   # 불리가 아닌 블록만(=불리 은폐)
	var unf_ids: Array = []
	for b in tm.get_blocks():
		all_ids.append(b["id"])
		if str(b["tag"]) == "불리":
			unf_ids.append(b["id"])
		else:
			non_unf_ids.append(b["id"])
	var total_unf: int = unf_ids.size()
	var w_omit: float = float(tm.tuning["w_omit"])

	# 1) 전부 포함(정직): δ=0, 부동층 상승
	var r1 := tm.publish({"included_ids": all_ids})
	if absf(float(r1["distortion"])) > EPS:
		print("[FAIL] 전부 포함인데 δ != 0 (%.4f)" % float(r1["distortion"])); failures += 1
	if float(r1["snapshot"]["xs"]["sns_swing"]) <= 0.5:
		print("[FAIL] 정직 보도 1턴 부동층 미상승"); failures += 1
	if (r1["comments"] as Array).size() < 2:
		print("[FAIL] 댓글 2개 미만"); failures += 1
	if failures == 0:
		print("[PASS] 전부 포함(정직): δ=0, 부동층 %.3f, 댓글 %d" % [float(r1["snapshot"]["xs"]["sns_swing"]), (r1["comments"] as Array).size()])

	# 2) 불리 은폐(불리만 제외): δ = w_omit*total_unf, 논조=찬성각
	var r2 := tm.publish({"included_ids": non_unf_ids})
	var exp_omit: float = clampf(w_omit * float(total_unf), 0.0, 1.0)
	if absf(float(r2["distortion"]) - exp_omit) > EPS:
		print("[FAIL] 불리은폐 δ 기대 %.4f 실제 %.4f" % [exp_omit, float(r2["distortion"])]); failures += 1
	elif str(r2["frame_label"]) != "찬성각":
		print("[FAIL] 불리은폐 논조 기대 찬성각 실제 %s" % str(r2["frame_label"])); failures += 1
	else:
		print("[PASS] 불리 은폐: δ=%.2f, 논조=%s" % [float(r2["distortion"]), str(r2["frame_label"])])

	# 3) 미보도(전부 제외): δ = w_omit*total_unf, reported 비어있음
	var r3 := tm.publish({"included_ids": []})
	if absf(float(r3["distortion"]) - exp_omit) > EPS:
		print("[FAIL] 미보도 δ 기대 %.4f 실제 %.4f" % [exp_omit, float(r3["distortion"])]); failures += 1
	elif not (r3["reported_facts"] as Array).is_empty():
		print("[FAIL] 미보도인데 보도 사실 존재"); failures += 1
	else:
		print("[PASS] 미보도: δ=%.2f (불리 은폐로 취급), 보도 0건" % float(r3["distortion"]))

	# 4) 불리만 보도: δ=0, 논조=반대각
	var r4 := tm.publish({"included_ids": unf_ids})
	if absf(float(r4["distortion"])) > EPS:
		print("[FAIL] 불리만 보도인데 δ != 0"); failures += 1
	elif str(r4["frame_label"]) != "반대각":
		print("[FAIL] 불리만 보도 논조 기대 반대각 실제 %s" % str(r4["frame_label"])); failures += 1
	else:
		print("[PASS] 불리만 보도: δ=0, 논조=%s" % str(r4["frame_label"]))

	# 5) 다중 턴 → maxTurns 도달 시 종료·엔딩
	var tm2 := TurnManager.new(1)
	var all2: Array = []
	for b in tm2.get_blocks():
		all2.append(b["id"])
	var last: Dictionary = {}
	for _t in tm2.max_turns:
		last = tm2.publish({"included_ids": all2})
		if bool(last["over"]):
			break
	if last.is_empty() or not bool(last["over"]):
		print("[FAIL] maxTurns 내 종료 안 됨"); failures += 1
	elif not (str(last["ending"]) in ["성공", "실패", "발각파탄"]):
		print("[FAIL] 엔딩 값 이상: %s" % str(last["ending"])); failures += 1
	else:
		print("[PASS] 다중 턴 종료: %s (턴 %d/%d)" % [str(last["ending"]), int(last["turn"]), tm2.max_turns])

	# 6) 압박: 반대각 기사 누적 → 배신파탄
	var tm3 := TurnManager.new(1)
	var unf3: Array = []
	for b in tm3.get_blocks():
		if str(b["tag"]) == "불리":
			unf3.append(b["id"])
	var pr: Dictionary = {}
	for _t in tm3.max_turns:
		pr = tm3.publish({"included_ids": unf3})  # 불리만 보도 = 반대각
		if bool(pr["over"]):
			break
	if str(pr.get("ending", "")) != "배신파탄":
		print("[FAIL] 반대각 누적인데 배신파탄 아님: %s (pressure=%d)" % [str(pr.get("ending", "")), int(pr.get("pressure", -1))]); failures += 1
	else:
		print("[PASS] 압박: 반대 기사 누적 → 배신파탄 (pressure=%d, 턴 %d)" % [int(pr["pressure"]), int(pr["turn"])])

	# 7) 분기: F15 숨김/발견, F16 F7-반대각 보도로 개폐, 찬성각이면 닫힘(흔적)
	var tmb := TurnManager.new(1)
	var base := {}
	for b in tmb.get_blocks():
		base[str(b["fact"])] = true
	if base.has("F15") or base.has("F16"):
		print("[FAIL] F15/F16이 발견·개폐 전에 노출됨"); failures += 1
	tmb.discover_theo()
	var disc := {}
	for b in tmb.get_blocks():
		disc[str(b["fact"])] = true
	if not disc.has("F15"):
		print("[FAIL] 책상 발견 후에도 F15 미노출"); failures += 1
	else:
		print("[PASS] F15: 발견 전 숨김 → discover_theo 후 등장")
	var all_unf := []
	for b in tmb.get_blocks():
		if str(b["tag"]) == "불리":
			all_unf.append(b["id"])
	var rf := tmb.publish({"included_ids": all_unf})  # 전 불리 = 반대각, F7 포함
	var has_f16 := false
	for b in tmb.get_blocks():
		if str(b["fact"]) == "F16":
			has_f16 = true
	if not (bool(rf["f16_unlocked"]) and has_f16):
		print("[FAIL] F7 반대각 보도했는데 F16 미개폐 (논조=%s)" % str(rf["frame_label"])); failures += 1
	else:
		print("[PASS] F16: F7 반대각 보도 → 개폐, 블록 등장")
	var tmc := TurnManager.new(1)
	var f7_fav := []
	for b in tmc.get_blocks():
		if str(b["fact"]) == "F7" and str(b["tag"]) == "유리":
			f7_fav.append(b["id"])
	var rc := tmc.publish({"included_ids": f7_fav})  # F7 유리만 = 찬성각
	if str(rc["branch_hint"]) == "" or bool(rc["f16_unlocked"]):
		print("[FAIL] F7 찬성각인데 닫힌 분기 흔적 없음/F16 열림 (논조=%s)" % str(rc["frame_label"])); failures += 1
	else:
		print("[PASS] 닫힌 분기: F7 찬성각 → 흔적 노출, F16 잠김 유지")

	# 8) 후일담: 형(F15) 발견 후 은폐 → 냉혹 / 보도·미발견 → 정직
	var tme := TurnManager.new(1)
	var epi_ok := true
	if tme.epilogue() != "정직":
		print("[FAIL] 기본(미발견) 후일담이 정직 아님: %s" % tme.epilogue()); failures += 1; epi_ok = false
	tme.discover_theo()
	if tme.epilogue() != "냉혹":
		print("[FAIL] 형 발견 후 은폐인데 냉혹 아님: %s" % tme.epilogue()); failures += 1; epi_ok = false
	tme.theo_reported = true
	if tme.epilogue() != "정직":
		print("[FAIL] 형 보도했는데 정직 아님: %s" % tme.epilogue()); failures += 1; epi_ok = false
	if epi_ok:
		print("[PASS] 후일담: 발견+은폐→냉혹 / 보도·미발견→정직")
	# epilogue 는 성공 엔딩에만 실린다(첫 턴은 미종료 → "")
	var tmf := TurnManager.new(1)
	var fav_all := []
	for b in tmf.get_blocks():
		if str(b["tag"]) == "유리":
			fav_all.append(b["id"])
	var rff := tmf.publish({"included_ids": fav_all})
	if str(rff["ending"]) != "성공" and str(rff.get("epilogue", "")) != "":
		print("[FAIL] 비성공인데 epilogue 채워짐: %s" % str(rff["epilogue"])); failures += 1
	else:
		print("[PASS] epilogue 는 성공 엔딩에만 실림")

	if failures == 0:
		print("TURN_RESULT: PASS")
		quit(0)
	else:
		print("TURN_RESULT: FAIL (%d)" % failures)
		quit(1)
