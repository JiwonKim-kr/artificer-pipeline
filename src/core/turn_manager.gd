class_name TurnManager
extends RefCounted
## 1턴 오케스트레이션: 문장 블록 취사 → 기울기(frameValue)·왜곡(δ) 도출 → OpinionModel.step → 댓글.
## 유리/불리 판단은 플레이어 몫 — 태그는 내부 계산용이며 UI 에 노출하지 않는다.
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

## 이번 턴 취사 가능한 문장 블록. UI 는 id·text·fact 만 사용(tag 는 내부 계산용, 비노출).
func get_blocks() -> Array:
	var blocks: Array = []
	var facts: Dictionary = content.get("facts", {})
	for fid in facts:
		var frags: Array = facts[fid].get("fragments", [])
		for i in frags.size():
			var frag: Dictionary = frags[i]
			blocks.append({
				"id": "%s#%d" % [fid, i],
				"fact": fid,
				"text": str(frag.get("text", "")),
				"tag": str(frag.get("tag", "")),
			})
	return blocks

## choices: { included_ids: Array[String] }  — 기사에 넣을 블록 id 목록(빈 배열이면 미보도).
## 반환: { snapshot, comments, distortion, lean, frame_value, frame_label, reported_facts, won }
func publish(choices: Dictionary) -> Dictionary:
	var included: Array = choices.get("included_ids", [])
	var fav_in: int = 0
	var unf_in: int = 0
	var total_unf: int = 0
	var reported: Dictionary = {}
	for b in get_blocks():
		if b["tag"] == "불리":
			total_unf += 1
		if included.has(b["id"]):
			if b["tag"] == "유리":
				fav_in += 1
			elif b["tag"] == "불리":
				unf_in += 1
			reported[b["fact"]] = true
	var unf_out: int = total_unf - unf_in  # 은폐한 불리 사실 수

	# 기울기: 유리 노출 + 불리 은폐 = 찬성 방향, 불리 노출 = 반대 방향.
	var lean: int = fav_in + unf_out - unf_in
	var k_lean: float = float(tuning.get("k_lean", 0.1))
	var frame_value: float = clampf(0.5 + k_lean * float(lean), 0.2, 0.8)
	# 왜곡(발각 리스크): 불리한 사실을 뺀 정도(선택적 누락).
	var delta: float = clampf(float(tuning.get("w_omit", 0.34)) * float(unf_out), 0.0, 1.0)

	var article: Dictionary = {
		"frameValue": frame_value,
		"tone": str(tuning.get("tone", "자극")),
		"channel": str(tuning.get("channel", "sns")),
		"distortion": delta,
	}
	var snapshot: Dictionary = model.step(article)
	var frame_label: String = _frame_label(frame_value)
	return {
		"snapshot": snapshot,
		"comments": _select_comments(frame_label, snapshot),
		"distortion": delta,
		"lean": lean,
		"frame_value": frame_value,
		"frame_label": frame_label,
		"reported_facts": reported.keys(),
		"won": model.is_won(),
	}

static func _frame_label(p: float) -> String:
	if p >= 0.6:
		return "찬성각"
	if p <= 0.4:
		return "반대각"
	return "중립"

func _select_comments(frame_label: String, snapshot: Dictionary) -> Array:
	var micro: Dictionary = snapshot.get("micro", {})
	var out: Array = []
	for s in model.config["segments"]:
		var seg_id: String = str(s["id"])
		var c: Dictionary = _pick_comment(seg_id, _reaction_for(seg_id, micro), frame_label)
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

func _pick_comment(seg_id: String, reaction: String, frame_label: String) -> Dictionary:
	var best: Dictionary = {}
	var best_score: int = -1
	for c in content.get("comments", []):
		if str(c.get("seg", "")) != seg_id or str(c.get("reaction", "")) != reaction:
			continue
		var score: int = 0
		var cf: Variant = c.get("frame", null)
		if cf != null and str(cf) == frame_label:
			score += 2
		if score > best_score:
			best_score = score
			best = c
	return best
