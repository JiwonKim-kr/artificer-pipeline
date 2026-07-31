extends SceneTree
## 1턴 흐름(turn_manager) 헤드리스 테스트 — 레버→δ→step→댓글.
## 실행: godot --headless --path <repo> --script res://pipeline/tests/turn_flow_test.gd
## 결과: 마지막 줄 TURN_RESULT: PASS | FAIL, 종료코드로도 알림.
## spec: docs/specs/turn_loop_vertical_slice.md

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

	# --- 1) 정직 발행: δ=0, 부동층 상승, 댓글 세그먼트별 반환 ---
	var r1 := tm.publish({
		"frame": "찬성각", "tone": "자극", "channel": "sns", "topic": "생산성",
		"omitted_unfavorable": 0, "reorder": false, "exaggerate": false,
	})
	if absf(float(r1["distortion"])) > EPS:
		print("[FAIL] 정직인데 δ != 0 (%.4f)" % float(r1["distortion"])); failures += 1
	var swing1: float = float(r1["snapshot"]["xs"]["sns_swing"])
	if swing1 <= 0.5:
		print("[FAIL] 정직 찬성각 1턴인데 부동층 미상승 (%.6f)" % swing1); failures += 1
	var comments1: Array = r1["comments"]
	if comments1.size() < 2:
		print("[FAIL] 댓글이 2개 미만 (%d)" % comments1.size()); failures += 1
	if failures == 0:
		print("[PASS] 정직 발행: δ=0, 부동층 %.6f, 댓글 %d개" % [swing1, comments1.size()])

	# --- 2) 왜곡 발행: 불리 1개 누락 → δ = w_omit ---
	var r2 := tm.publish({
		"frame": "찬성각", "tone": "자극", "channel": "sns", "topic": "안전",
		"omitted_unfavorable": 1, "reorder": false, "exaggerate": false,
	})
	var expect_delta: float = float(tm.tuning["w_omit"])
	if absf(float(r2["distortion"]) - expect_delta) > EPS:
		print("[FAIL] 누락 δ 기대 %.4f 실제 %.4f" % [expect_delta, float(r2["distortion"])]); failures += 1
	else:
		print("[PASS] 왜곡 발행: 누락 1개 → δ=%.4f" % float(r2["distortion"]))

	# --- 3) 과장+재배치 결합 δ 산출 ---
	var d3: float = tm.compute_distortion(2, true, true)
	var expect3: float = clampf(float(tm.tuning["w_omit"]) * 2.0 + float(tm.tuning["w_reorder"]) + float(tm.tuning["w_exagg"]), 0.0, 1.0)
	if absf(d3 - expect3) > EPS:
		print("[FAIL] 결합 δ 기대 %.4f 실제 %.4f" % [expect3, d3]); failures += 1
	else:
		print("[PASS] 결합 δ(누락2+재배치+과장) = %.4f" % d3)

	if failures == 0:
		print("TURN_RESULT: PASS")
		quit(0)
	else:
		print("TURN_RESULT: FAIL (%d)" % failures)
		quit(1)
