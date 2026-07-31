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
	if absf(float(r2["distortion"]) - w_omit * float(total_unf)) > EPS:
		print("[FAIL] 불리은폐 δ 기대 %.4f 실제 %.4f" % [w_omit * total_unf, float(r2["distortion"])]); failures += 1
	elif str(r2["frame_label"]) != "찬성각":
		print("[FAIL] 불리은폐 논조 기대 찬성각 실제 %s" % str(r2["frame_label"])); failures += 1
	else:
		print("[PASS] 불리 은폐: δ=%.2f, 논조=%s" % [float(r2["distortion"]), str(r2["frame_label"])])

	# 3) 미보도(전부 제외): δ = w_omit*total_unf, reported 비어있음
	var r3 := tm.publish({"included_ids": []})
	if absf(float(r3["distortion"]) - w_omit * float(total_unf)) > EPS:
		print("[FAIL] 미보도 δ 기대 %.4f 실제 %.4f" % [w_omit * total_unf, float(r3["distortion"])]); failures += 1
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

	if failures == 0:
		print("TURN_RESULT: PASS")
		quit(0)
	else:
		print("TURN_RESULT: FAIL (%d)" % failures)
		quit(1)
