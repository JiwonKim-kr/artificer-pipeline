extends SceneTree
## 여론엔진 GDScript 이식 ↔ sim 골든 대조 테스트 (headless).
## 실행: godot --headless --path <repo> --script res://pipeline/tests/opinion_parity_test.gd
## 골든 생성: node pipeline/tests/dump_opinion_golden.mjs
## 결과: 마지막 줄 PARITY_RESULT: PASS | FAIL, 종료코드로도 알림.
## spec: docs/specs/turn_loop_vertical_slice.md

const EPS := 1e-9

func _load_json(path: String) -> Variant:
	if not FileAccess.file_exists(path):
		return null
	var f := FileAccess.open(path, FileAccess.READ)
	return JSON.parse_string(f.get_as_text())

func _initialize() -> void:
	var failures: int = 0
	print("== opinion parity test ==")

	var cfg: Variant = _load_json("res://src/core/data/opinion_config.json")
	var gold: Variant = _load_json("res://pipeline/tests/fixtures/opinion_golden.json")
	if cfg == null or gold == null:
		print("[FAIL] config 또는 골든 픽스처 로드 실패")
		print("PARITY_RESULT: FAIL (1)")
		quit(1)
		return

	# --- 1) RNG 비트-정확 ---
	var rng := RngMulberry32.new(int(gold["rng_seed"]))
	var exp_rng: Array = gold["rng_uint32"]
	for i in exp_rng.size():
		var got: int = rng.next_uint32()
		if got != int(exp_rng[i]):
			print("[FAIL] rng[%d] 기대 %d 실제 %d" % [i, int(exp_rng[i]), got])
			failures += 1
	if failures == 0:
		print("[PASS] RNG uint32 16개 비트-정확")

	# --- 2) 시나리오① turn1 (정직) ---
	var m := OpinionModel.new(cfg, 1)
	m.step({"frame": "찬성각", "tone": "자극", "channel": "sns"})
	var exp_xs: Dictionary = gold["scenario1_turn1_xs"]
	var xs_ok: bool = true
	for id in exp_xs:
		var got_x: float = float(m.xs[id])
		var e: float = float(exp_xs[id])
		if absf(got_x - e) > EPS:
			print("[FAIL] xs[%s] 기대 %.12f 실제 %.12f" % [id, e, got_x])
			failures += 1
			xs_ok = false
	if xs_ok:
		print("[PASS] 시나리오① turn1 세그먼트 x 일치 (부동층=%.6f)" % float(m.xs["sns_swing"]))

	# --- 3) 발각 경로(RNG) δ=1 8턴 ---
	var m2 := OpinionModel.new(cfg, 1)
	var dl: Array = gold["distort_seed1"]
	var det_ok: bool = true
	for t in dl.size():
		var sn := m2.step({"frame": "찬성각", "tone": "자극", "channel": "sns", "distortion": 1.0})
		var g: Dictionary = dl[t]
		if absf(float(m2.risk_prob) - float(g["riskProb"])) > EPS:
			print("[FAIL] turn%d riskProb 기대 %.12f 실제 %.12f" % [t + 1, float(g["riskProb"]), float(m2.risk_prob)])
			failures += 1; det_ok = false
		var g_det: Variant = g["detection"]
		var got_det: Variant = sn["detection"]
		if (g_det == null) != (got_det == null):
			print("[FAIL] turn%d 발각 발생 여부 불일치 (기대 %s)" % [t + 1, str(g_det != null)])
			failures += 1; det_ok = false
		elif g_det != null:
			if absf(float(got_det["damage"]) - float(g_det["damage"])) > EPS:
				print("[FAIL] turn%d 발각 피해 불일치" % [t + 1])
				failures += 1; det_ok = false
	if det_ok:
		print("[PASS] 발각 경로 8턴 riskProb·발각 일치")

	if failures == 0:
		print("PARITY_RESULT: PASS")
		quit(0)
	else:
		print("PARITY_RESULT: FAIL (%d)" % failures)
		quit(1)
