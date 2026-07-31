class_name OpinionModel
extends RefCounted
## sim/opinion-model/opinion-model.mjs 의 여론 확산 엔진 GDScript 이식.
## bounded-confidence + 확증편향 대역 + 역풍 + 톤×감정 공명 + 발각 확률 + 평판.
## config 는 res://src/core/data/opinion_config.json (모델 단일 출처).
## 이식 정확성은 pipeline/tests/opinion_parity_test.gd 가 sim 골든과 대조.
## spec: docs/specs/turn_loop_vertical_slice.md

var config: Dictionary
var rng: RngMulberry32

# --- 상태 ---
var xs: Dictionary            # seg_id(String) -> float
var tv_macro: float           # TV(거시) 저역통과 지연값
var reputation: float
var risk_prob: float          # 누적 발각 확률
var detections: Array         # 발각 이벤트 기록
var turn: int
var log: Array
var _has_last_frame: bool
var _last_frame_value: float

func _init(cfg: Dictionary, seed: int = 1) -> void:
	config = cfg
	rng = RngMulberry32.new(seed)
	_init_state()

func _init_state() -> void:
	xs = {}
	for s in config["segments"]:
		xs[s["id"]] = float(s["x0"])
	tv_macro = _macro_opinion()
	reputation = float(config["reputation"]["start"])
	risk_prob = 0.0
	detections = []
	turn = 0
	log = []
	_has_last_frame = false
	_last_frame_value = 0.0

static func _clamp01(v: float) -> float:
	return clampf(v, 0.0, 1.0)

static func _sign(v: float) -> float:
	if v > 0.0:
		return 1.0
	if v < 0.0:
		return -1.0
	return 0.0

## 톤×감정 공명: 자극→emo, 차분→1-emo, 그 외(중립)→0.5.
static func tone_effectiveness(tone: String, emo: float) -> float:
	if tone == "자극":
		return emo
	if tone == "차분":
		return 1.0 - emo
	return 0.5

func _macro_opinion() -> float:
	var sum: float = 0.0
	var w: float = 0.0
	for s in config["segments"]:
		sum += float(s["size"]) * float(xs[s["id"]])
		w += float(s["size"])
	return sum / (w if w != 0.0 else 1.0)

## 접전도: 0.5 근처=1, 극단=0.
static func contestedness(macro: float) -> float:
	return 1.0 - absf(2.0 * macro - 1.0)

## 한 세그먼트가 한 기사에 대해 겪는 이번 턴 변화.
func update_segment(seg: Dictionary, x: float, article: Dictionary, R: float) -> Dictionary:
	var C: Dictionary = config["constants"]
	var reach: float = float((seg["reach"] as Dictionary).get(article["channel"], 0.0))
	var p: float = float(article["frameValue"])
	var eps: float = float(C["epsMax"]) * (1.0 - float(seg["conf"]))
	var d: float = absf(p - x)
	var E: float = tone_effectiveness(article["tone"], float(seg["emo"]))

	var dir: float
	var strength: float
	var accepted: bool
	if d <= eps:
		accepted = true
		dir = _sign(p - x)
		var denom: float = eps if eps != 0.0 else 1e-9
		strength = 1.0 - d / denom
	else:
		accepted = false
		dir = _sign(x - p)
		var over: float = minf(1.0, (d - eps) / (1.0 - eps + 1e-9))
		strength = float(C["backfireCoef"]) * float(seg["conf"]) * over

	var distortion: float = float(article.get("distortion", 0.0))
	var dist_boost: float = 1.0 + distortion * float(C["distortionGain"])
	var pull: float = float(C["k"]) * reach * E * strength * dir * R * dist_boost
	var anchor: float = -float(C["anchorLambda"]) * (x - float(seg["x0"]))
	var nx: float = _clamp01(x + pull + anchor)
	return {
		"nx": nx, "pull": pull, "anchor": anchor, "reach": reach,
		"eps": eps, "d": d, "E": E, "strength": strength, "accepted": accepted, "dir": dir,
	}

## 한 턴 진행: 기사 1건 발행 → 세그먼트 즉시 반응 → 발각 굴림 → TV 거시 지연 반영.
## article: {frame, tone, channel, distortion?}
func step(article: Dictionary) -> Dictionary:
	var C: Dictionary = config["constants"]
	# 프레임: 직접 frameValue 를 받으면 사용(게임 계층에서 도출), 없으면 레버 키로 조회.
	var frame_value: float = float(article["frameValue"]) if article.has("frameValue") else float(config["levers"]["frame"][article["frame"]])
	var a: Dictionary = article.duplicate()
	a["frameValue"] = frame_value

	var rep: Dictionary = config["reputation"]
	if _has_last_frame:
		var cur: float = _sign(frame_value - 0.5)
		var flipped: bool = cur != 0.0 and cur == -_sign(_last_frame_value - 0.5)
		if flipped:
			reputation = maxf(float(rep["floor"]), reputation - float(rep["swingPenalty"]))
		else:
			reputation = minf(1.0, reputation + float(rep["recover"]))
	_last_frame_value = frame_value
	_has_last_frame = true

	var R: float = reputation
	var micro: Dictionary = {}
	for s in config["segments"]:
		var r: Dictionary = update_segment(s, float(xs[s["id"]]), a, R)
		xs[s["id"]] = r["nx"]
		micro[s["id"]] = r

	var macro_now: float = _macro_opinion()
	var contested: float = contestedness(macro_now)

	# === 발각(확률 누적식) ===
	var det: Dictionary = config["detection"]
	var delta: float = float(a.get("distortion", 0.0))
	if delta > 0.0:
		risk_prob = _clamp01(risk_prob + float(det["manipStep"]) * delta)
	else:
		risk_prob = maxf(0.0, risk_prob - float(det["honestDecay"]))

	var detection: Variant = null
	if risk_prob > 0.0:
		var eff_prob: float = _clamp01(risk_prob * (1.0 + float(det["contestednessWeight"]) * (contested - 0.5) * 2.0))
		if rng.next() < eff_prob:
			var damage: float = float(det["damageK"]) * risk_prob
			var lean: float = _sign(frame_value - 0.5)
			for s in config["segments"]:
				var shock: float = damage * (0.5 + 0.5 * float(s["emo"]))
				xs[s["id"]] = _clamp01(float(xs[s["id"]]) - lean * shock)
			reputation = maxf(float(rep["floor"]), reputation - float(det["accuracyRepPenalty"]))
			detection = {"turn": turn + 1, "prob": eff_prob, "riskAtCatch": risk_prob, "damage": damage, "lean": lean}
			detections.append(detection)
			risk_prob *= float(det["resetOnDetect"])
			macro_now = _macro_opinion()

	tv_macro = tv_macro + float(C["macroLagAlpha"]) * (macro_now - tv_macro)
	turn += 1

	var snapshot: Dictionary = {
		"turn": turn, "article": a, "reputation": reputation, "xs": xs.duplicate(),
		"macroNow": macro_now, "tvMacro": tv_macro, "contested": contested,
		"riskProb": risk_prob, "detection": detection, "micro": micro,
	}
	log.append(snapshot)
	return snapshot

func is_won() -> bool:
	return float(xs[config["mission"]["target"]]) >= float(config["mission"]["winThreshold"])
