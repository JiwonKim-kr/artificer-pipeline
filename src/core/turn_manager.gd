class_name TurnManager
extends RefCounted
## 1턴 오케스트레이션: 문장 블록 취사 → 기울기(frameValue)·왜곡(δ) 도출 → OpinionModel.step → 댓글.
## 유리/불리 판단은 플레이어 몫 — 태그는 내부 계산용이며 UI 에 노출하지 않는다.
## spec: docs/specs/turn_loop_vertical_slice.md

const CONFIG_PATH := "res://src/core/data/opinion_config.json"
const CONTENT_PATH := "res://src/core/data/content_slice.json"
const TUNING_PATH := "res://src/core/lever_tuning.json"

# 압박(외압) 암시 문구 — 수치 비표시, 반대 기사 누적에 따른 단계별 노출(스토리 §2.3).
const PRESSURE_HINTS := {
	1: "편집장이 당신의 기사를 한참 들여다봤다.",
	2: "모르겐社 홍보실에서 전화가 왔다더라. 반대 기사는 지면이 줄지도 모른다.",
	3: "편집국 앞을 '강철 손'이 서성인다. 이번이 마지막 경고다.",
}
const PRESSURE_BREAK := 4  # 반대 기사 누적 임계 → 배신파탄

var model: OpinionModel
var content: Dictionary
var tuning: Dictionary
var max_turns: int = 8
var pressure: int = 0  # 반대 스탠스(반대각 기사) 누적 카운터

func _init(seed: int = 1) -> void:
	var cfg: Dictionary = _load_json(CONFIG_PATH)
	content = _load_json(CONTENT_PATH)
	tuning = _load_json(TUNING_PATH)
	model = OpinionModel.new(cfg, seed)
	max_turns = int((cfg.get("mission", {}) as Dictionary).get("maxTurns", 8))

## 종료 판정: 발각 2회+ → 발각파탄 / 목표 도달 → 성공 / maxTurns 도달 → 실패 / 그 외 진행("").
func check_ending() -> String:
	if model.detections.size() >= 2:
		return "발각파탄"
	if pressure >= PRESSURE_BREAK:
		return "배신파탄"
	if model.is_won():
		return "성공"
	if model.turn >= max_turns:
		return "실패"
	return ""

## 현재 압박 단계의 암시 문구(수치 비표시). 없으면 "".
func pressure_hint() -> String:
	if pressure <= 0:
		return ""
	return str(PRESSURE_HINTS.get(mini(pressure, 3), ""))

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
	if frame_label == "반대각":
		pressure += 1  # 반대 스탠스 = 의뢰인 외압 누적
	var ending: String = check_ending()
	return {
		"snapshot": snapshot,
		"comments": _select_comments(frame_label, snapshot),
		"distortion": delta,
		"lean": lean,
		"frame_value": frame_value,
		"frame_label": frame_label,
		"reported_facts": reported.keys(),
		"won": model.is_won(),
		"turn": model.turn,
		"max_turns": max_turns,
		"pressure": pressure,
		"pressure_hint": pressure_hint(),
		"ending": ending,
		"over": ending != "",
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
