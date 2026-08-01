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
# 발각 누적 임계 → 발각파탄. 2→3 완화(C6): 최적 플레이(은폐1)의 파탄률 26.4%→5.3%로
# 심사자 1회 플레이가 운으로 끝나는 일을 줄이되, 과욕(은폐2+)은 파탄 24%+실패 40%로
# 여전히 벌받는다. 근거 수치: docs/build/c6_balance.md (sim 몬테카를로 N=4000)
const DETECT_BREAK := 3
const COMMENT_COOLDOWN := 5  # 최근 이만큼 쓴 댓글 id 는 재추출에서 제외(반복방어 9.3)

var model: OpinionModel
var content: Dictionary
var tuning: Dictionary
var max_turns: int = 8
var pressure: int = 0  # 반대 스탠스(반대각 기사) 누적 카운터
var theo_discovered: bool = false  # F15(형 테오) 책상 발견 여부
var theo_reported: bool = false    # 발견한 형 테오(F15)를 실제로 지면에 실었는가 (후일담 분기)
# 댓글 반복방어용. model 의 발각 RNG(비트-정확 대조 대상)와 절대 분리한다 — 표현层이라
# 결정성 불필요, 별도 RNG 로 매 게임 다른 댓글이 나오게 한다.
var _comment_rng := RandomNumberGenerator.new()
var _recent_comments: Array = []   # 최근 사용한 댓글 id (쿨다운 큐)
var f16_unlocked: bool = false     # F16 취재선 개폐 (F7 반대각 보도 시 열림)

func _init(seed: int = 1) -> void:
	var cfg: Dictionary = _load_json(CONFIG_PATH)
	content = _load_json(CONTENT_PATH)
	tuning = _load_json(TUNING_PATH)
	model = OpinionModel.new(cfg, seed)
	max_turns = int((cfg.get("mission", {}) as Dictionary).get("maxTurns", 8))
	_comment_rng.randomize()  # 댓글은 표현层 — 매 게임 다르게(발각 RNG 와 무관)

## 종료 판정: 발각 DETECT_BREAK회+ → 발각파탄 / 압박 누적 → 배신파탄 / 목표 도달 → 성공
## / maxTurns 도달 → 실패 / 그 외 진행("").
func check_ending() -> String:
	if model.detections.size() >= DETECT_BREAK:
		return "발각파탄"
	if pressure >= PRESSURE_BREAK:
		return "배신파탄"
	if model.is_won():
		return "성공"
	if model.turn >= max_turns:
		return "실패"
	return ""

## 성공 엔딩의 후일담 분기. 형 테오(F15)를 발견하고도 지면에서 뺐다면 "냉혹"
## (제 가족은 지키며 여론을 조작해 이긴 것). 그 외(무지·정직 보도)는 "정직".
## 요나스 반전(F14) 축은 콘텐츠에 F14 가 추가되면 여기에 합류한다.
func epilogue() -> String:
	if theo_discovered and not theo_reported:
		return "냉혹"
	return "정직"

## 현재 압박 단계의 암시 문구(수치 비표시). 없으면 "".
func pressure_hint() -> String:
	if pressure <= 0:
		return ""
	return str(PRESSURE_HINTS.get(mini(pressure, 3), ""))

## F15(형 테오) 책상 발견. 새로 발견하면 true.
func discover_theo() -> bool:
	if theo_discovered:
		return false
	theo_discovered = true
	return true

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
		var fdict: Dictionary = facts[fid]
		if bool(fdict.get("hidden", false)) and not theo_discovered:
			continue   # F15: 책상에서 발견해야 등장
		if bool(fdict.get("gated", false)) and not f16_unlocked:
			continue   # F16: F7 반대각 보도로 열려야 등장
		var t: int = int(fdict.get("turn", 0))
		if t > 0 and t > model.turn + 1:
			continue   # 비트시트: 아직 도착하지 않은 사실(이번 턴 = model.turn+1)
		var frags: Array = fdict.get("fragments", [])
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

	if reported.has("F15"):
		theo_reported = true  # 발견한 형을 실제로 실었다 → 후일담 정직

	# F16 분기: F7 을 반대각으로 보도하면 취재선이 열리고, 찬성/중립으로 보도하면 닫힌다(흔적).
	var branch_hint: String = ""
	if reported.has("F7"):
		if frame_label == "반대각":
			f16_unlocked = true
		elif not f16_unlocked:
			branch_hint = "편집장 메일: \"자네가 접었다던 그 태엽인 건, 다른 데서 냄새를 맡은 모양이야.\""

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
		"theo_discovered": theo_discovered,
		"f16_unlocked": f16_unlocked,
		"branch_hint": branch_hint,
		"ending": ending,
		"epilogue": epilogue() if ending == "성공" else "",
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

## 반복방어(기획서 9.3): seg+reaction 후보 풀 → 쿨다운 제외 → frame 가점 가중 랜덤.
## 같은 템플릿이 연속으로 재등장하지 않게 해 "가짜 티"를 막는다.
func _pick_comment(seg_id: String, reaction: String, frame_label: String) -> Dictionary:
	var pool: Array = []
	for c in content.get("comments", []):
		if str(c.get("seg", "")) == seg_id and str(c.get("reaction", "")) == reaction:
			pool.append(c)
	if pool.is_empty():
		return {}
	# 최근 쓴 id 는 뺀다. 전부 최근이면(후보 고갈) 쿨다운 무시 폴백.
	var fresh: Array = pool.filter(
		func(c): return not _recent_comments.has(str(c.get("id", ""))))
	var cand: Array = fresh if not fresh.is_empty() else pool
	# 가중: 지배 프레임과 일치하는 댓글에 가점(관련성).
	var weights: Array = []
	var total: float = 0.0
	for c in cand:
		var w: float = 1.0
		var cf: Variant = c.get("frame", null)
		if cf != null and str(cf) == frame_label:
			w += 2.0
		weights.append(w)
		total += w
	var roll: float = _comment_rng.randf() * total
	var pick: Dictionary = cand[0]
	var acc: float = 0.0
	for i in cand.size():
		acc += weights[i]
		if roll <= acc:
			pick = cand[i]
			break
	var pid: String = str(pick.get("id", ""))
	if pid != "":
		_recent_comments.append(pid)
		if _recent_comments.size() > COMMENT_COOLDOWN:
			_recent_comments.pop_front()
	return pick
