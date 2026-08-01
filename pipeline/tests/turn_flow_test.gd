extends SceneTree
## 턴 흐름(turn_manager) 헤드리스 테스트 — 문장 취사·δ·엔딩·압박·분기·비트시트.
## 실행: godot --headless --path <repo> --script res://pipeline/tests/turn_flow_test.gd
## 결과: 마지막 줄 TURN_RESULT: PASS | FAIL. spec: docs/specs/phase_c_turn_progression.md

const EPS := 1e-9
const ENDINGS := ["성공", "실패", "발각파탄", "배신파탄"]

func _ids(tm) -> Array:
	var a: Array = []
	for b in tm.get_blocks():
		a.append(b["id"])
	return a

func _unf_ids(tm) -> Array:
	var a: Array = []
	for b in tm.get_blocks():
		if str(b["tag"]) == "불리":
			a.append(b["id"])
	return a

func _non_unf_ids(tm) -> Array:
	var a: Array = []
	for b in tm.get_blocks():
		if str(b["tag"]) != "불리":
			a.append(b["id"])
	return a

func _total_unf(tm) -> int:
	var n: int = 0
	for b in tm.get_blocks():
		if str(b["tag"]) == "불리":
			n += 1
	return n

func _fact_set(tm) -> Dictionary:
	var d: Dictionary = {}
	for b in tm.get_blocks():
		d[str(b["fact"])] = true
	return d

func _initialize() -> void:
	var failures: int = 0
	print("== turn flow test ==")
	var w_omit: float = float(TurnManager.new(1).tuning.get("w_omit", 0.34))

	# 1) 전부 포함(정직, 턴1=F1·F2): δ=0, 부동층 상승, 댓글 ≥2
	var t1 := TurnManager.new(1)
	var r1 := t1.publish({"included_ids": _ids(t1)})
	if absf(float(r1["distortion"])) > EPS:
		print("[FAIL] 정직인데 δ != 0"); failures += 1
	elif float(r1["snapshot"]["xs"]["sns_swing"]) <= 0.5:
		print("[FAIL] 정직 1턴 부동층 미상승"); failures += 1
	elif (r1["comments"] as Array).size() < 2:
		print("[FAIL] 댓글 2개 미만"); failures += 1
	else:
		print("[PASS] 정직: δ=0, 부동층 %.3f, 댓글 %d" % [float(r1["snapshot"]["xs"]["sns_swing"]), (r1["comments"] as Array).size()])

	# 2) 불리 은폐: δ = clamp(w_omit*불리수), 논조 찬성각
	var t2 := TurnManager.new(1)
	var exp_omit: float = clampf(w_omit * float(_total_unf(t2)), 0.0, 1.0)
	var r2 := t2.publish({"included_ids": _non_unf_ids(t2)})
	if absf(float(r2["distortion"]) - exp_omit) > EPS:
		print("[FAIL] 불리은폐 δ 기대 %.4f 실제 %.4f" % [exp_omit, float(r2["distortion"])]); failures += 1
	elif str(r2["frame_label"]) != "찬성각":
		print("[FAIL] 불리은폐 논조 기대 찬성각 실제 %s" % str(r2["frame_label"])); failures += 1
	else:
		print("[PASS] 불리 은폐: δ=%.2f, 논조=찬성각" % float(r2["distortion"]))

	# 3) 미보도: δ=exp_omit, 보도 0건
	var t3 := TurnManager.new(1)
	var r3 := t3.publish({"included_ids": []})
	if absf(float(r3["distortion"]) - exp_omit) > EPS:
		print("[FAIL] 미보도 δ 기대 %.4f 실제 %.4f" % [exp_omit, float(r3["distortion"])]); failures += 1
	elif not (r3["reported_facts"] as Array).is_empty():
		print("[FAIL] 미보도인데 보도 사실 존재"); failures += 1
	else:
		print("[PASS] 미보도: δ=%.2f, 보도 0건" % float(r3["distortion"]))

	# 4) 불리만 보도: δ=0, 논조 반대각
	var t4 := TurnManager.new(1)
	var r4 := t4.publish({"included_ids": _unf_ids(t4)})
	if absf(float(r4["distortion"])) > EPS or str(r4["frame_label"]) != "반대각":
		print("[FAIL] 불리만 보도 기대 δ0·반대각 실제 δ%.2f·%s" % [float(r4["distortion"]), str(r4["frame_label"])]); failures += 1
	else:
		print("[PASS] 불리만 보도: δ=0, 논조=반대각")

	# 5) 다중 턴 종료(매 턴 전부 포함): over + 엔딩 유효
	var t5 := TurnManager.new(1)
	var last: Dictionary = {}
	for _i in t5.max_turns:
		last = t5.publish({"included_ids": _ids(t5)})
		if bool(last["over"]):
			break
	if last.is_empty() or not bool(last["over"]) or not (str(last["ending"]) in ENDINGS):
		print("[FAIL] 다중 턴 종료 실패: %s" % str(last.get("ending", "?"))); failures += 1
	else:
		print("[PASS] 다중 턴 종료: %s (턴 %d)" % [str(last["ending"]), int(last["turn"])])

	# 6) 압박: 매 턴 불리만(반대각) → 배신파탄
	var t6 := TurnManager.new(1)
	var pr: Dictionary = {}
	for _i in t6.max_turns:
		pr = t6.publish({"included_ids": _unf_ids(t6)})
		if bool(pr["over"]):
			break
	if str(pr.get("ending", "")) != "배신파탄":
		print("[FAIL] 반대 누적인데 배신파탄 아님: %s" % str(pr.get("ending", ""))); failures += 1
	else:
		print("[PASS] 압박: 반대 누적 → 배신파탄 (턴 %d)" % int(pr["turn"]))

	# 7) 비트시트: 턴1엔 F5·F7 없음
	var t7 := TurnManager.new(1)
	var f_t1 := _fact_set(t7)
	if f_t1.has("F7") or f_t1.has("F5"):
		print("[FAIL] 비트시트 미적용(턴1에 F5/F7 노출)"); failures += 1
	else:
		print("[PASS] 비트시트: 턴1엔 F1·F2만")

	# 8) 분기: F15 발견 + F16 개폐(F7 도착 턴으로 점프)
	t7.discover_theo()
	t7.model.turn = 4  # 이번 턴 = 5 → F7 노출 (테스트 단축)
	var f_t5 := _fact_set(t7)
	if not (f_t5.has("F7") and f_t5.has("F15")):
		print("[FAIL] 턴5+발견 후 F7/F15 미노출"); failures += 1
	else:
		var rf := t7.publish({"included_ids": _unf_ids(t7)})  # 전 불리 = 반대각(F7 포함)
		if not (bool(rf["f16_unlocked"]) and _fact_set(t7).has("F16")):
			print("[FAIL] F7 반대각 보도 후 F16 미개폐 (논조=%s)" % str(rf["frame_label"])); failures += 1
		else:
			print("[PASS] 분기: F15 발견 + F7 반대각 → F16 개폐")

	# 9) 닫힌 분기: F7 찬성각 보도 → 흔적, F16 잠김
	var t8 := TurnManager.new(1)
	t8.model.turn = 4
	var f7_fav: Array = []
	for b in t8.get_blocks():
		if str(b["fact"]) == "F7" and str(b["tag"]) == "유리":
			f7_fav.append(b["id"])
	var rc := t8.publish({"included_ids": f7_fav})
	if str(rc["branch_hint"]) == "" or bool(rc["f16_unlocked"]):
		print("[FAIL] F7 찬성각인데 흔적 없음/F16 열림 (논조=%s)" % str(rc["frame_label"])); failures += 1
	else:
		print("[PASS] 닫힌 분기: F7 찬성각 → 흔적, F16 잠김")

	if failures == 0:
		print("TURN_RESULT: PASS")
		quit(0)
	else:
		print("TURN_RESULT: FAIL (%d)" % failures)
		quit(1)
