class_name TurnManager
extends RefCounted
## 1턴 오케스트레이션: 레버 선택 → δ 산출 → OpinionModel.step → 반응(댓글) 반환.
## 엔진(opinion_model)과 UI 사이의 로직 브릿지. 씬 의존 없음(헤드리스 테스트 가능).
## spec: docs/specs/turn_loop_vertical_slice.md

const CONFIG_PATH := "res://src/core/data/opinion_config.json"
const CONTENT_PATH := "res://src/core/data/content_slice.json"
const TUNING_PATH := "res://src/core/lever_tuning.json"

var model: OpinionModel
var content: Dictionary
var tuning: Dictionary

func _init(seed: int = 1) -> void:
	var cfg: Dictionary = _load_json(CONFIG_PATH)
	content = _load_json(CONTENT_PATH)
	tuning = _load_json(TUNING_PATH)
	model = OpinionModel.new(cfg, seed)

static func _load_json(path: String) -> Dictionary:
	if not FileAccess.file_exists(path):
		push_error("파일 없음: %s" % path)
		return {}
	var f := FileAccess.open(path, FileAccess.READ)
	var parsed: Variant = JSON.parse_string(f.get_as_text())
	return parsed if parsed is Dictionary else {}

## 왜곡 3종 → 단일 스칼라 δ (게임 계층 튜닝값). 프레임은 δ와 독립.
func compute_distortion(omitted_unfavorable: int, reorder: bool, exaggerate: bool) -> float:
	var d: float = float(tuning.get("w_omit", 0.0)) * float(omitted_unfavorable)
	if reorder:
		d += float(tuning.get("w_reorder", 0.0))
	if exaggerate:
		d += float(tuning.get("w_exagg", 0.0))
	return clampf(d, 0.0, 1.0)

## choices: {frame, tone, channel, topic?, omitted_unfavorable?, reorder?, exaggerate?}
## 반환: {snapshot, comments(Array), distortion, won}
func publish(choices: Dictionary) -> Dictionary:
	var delta: float = compute_distortion(
		int(choices.get("omitted_unfavorable", 0)),
		bool(choices.get("reorder", false)),
		bool(choices.get("exaggerate", false)),
	)
	var article: Dictionary = {
		"frame": choices["frame"],
		"tone": choices["tone"],
		"channel": choices["channel"],
		"distortion": delta,
	}
	var snapshot: Dictionary = model.step(article)
	var comments: Array = _select_comments(choices, snapshot)
	return {
		"snapshot": snapshot,
		"comments": comments,
		"distortion": delta,
		"won": model.is_won(),
	}

## 세그먼트 micro 반응으로 각 세그먼트의 반응 유형을 정하고, 그에 맞는 댓글을 고른다.
func _select_comments(choices: Dictionary, snapshot: Dictionary) -> Array:
	var frame: String = str(choices.get("frame", ""))
	var topic: Variant = choices.get("topic", null)
	var micro: Dictionary = snapshot.get("micro", {})
	var out: Array = []
	for s in model.config["segments"]:
		var seg_id: String = str(s["id"])
		var reaction: String = _reaction_for(seg_id, micro)
		var c: Dictionary = _pick_comment(seg_id, reaction, frame, topic)
		if not c.is_empty():
			out.append(c)
	return out

func _reaction_for(seg_id: String, micro: Dictionary) -> String:
	if seg_id == "apathetic":
		return "시큰둥"
	var r: Variant = micro.get(seg_id, null)
	if r is Dictionary and bool(r.get("accepted", false)):
		return "수용"
	return "역풍"

## seg+reaction 우선, frame·topic 일치하면 가점. 최소 seg+reaction 일치 하나는 보장(폴백).
func _pick_comment(seg_id: String, reaction: String, frame: String, topic: Variant) -> Dictionary:
	var best: Dictionary = {}
	var best_score: int = -1
	for c in content.get("comments", []):
		if str(c.get("seg", "")) != seg_id:
			continue
		if str(c.get("reaction", "")) != reaction:
			continue
		var score: int = 0
		var cf: Variant = c.get("frame", null)
		if cf != null and str(cf) == frame:
			score += 2
		var ct: Variant = c.get("topic", null)
		if topic != null and ct != null and str(ct) == str(topic):
			score += 1
		if score > best_score:
			best_score = score
			best = c
	return best
