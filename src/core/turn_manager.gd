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
	2: "모르겐 사 홍보실에서 전화가 왔다더라. 반대 기사는 지면이 줄지도 모른다.",
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
# 댓글 반복방어용. model 의 발각 RNG(비트-정확 대조 대상)와 절대 분리한다 — 표현층이라
# 결정성 불필요, 별도 RNG 로 매 게임 다른 댓글이 나오게 한다.
var _comment_rng := RandomNumberGenerator.new()
var _recent_comments: Array = []   # 최근 사용한 댓글 id (쿨다운 큐)

# --- 찌라시 자생(표현층 전용) --- spec: docs/specs/rumor_emergence.md
# 여론·발각·평판 수치에 일절 영향을 주지 않는다. 검증된 opinion_model 은 무수정이고
# 난수도 _comment_rng(표현층)만 쓴다 → parity·밸런싱 불변.
var rumor_heat: float = 0.0        # 누적 열기. 플레이어가 만든 판이 소문을 부른다
var rumor_level: int = 1           # 강도 1(의혹)→2(확산)→3(확신형). 단조 증가
var _reported_ever: Dictionary = {}    # 지금까지 한 번이라도 보도한 사실
var _encountered_ever: Dictionary = {} # 지금까지 한 번이라도 자료로 등장한 사실
var _rumor_used: Array = []            # 이미 쓴 찌라시 id (재등장 방지)
var _rumor_last_level: int = 0         # 직전에 발화된 강도 — 역행 금지용
var f16_unlocked: bool = false     # F16 취재선 개폐 (F7 반대각 보도 시 열림)

func _init(seed: int = 1) -> void:
	var cfg: Dictionary = _load_json(CONFIG_PATH)
	content = _load_json(CONTENT_PATH)
	tuning = _load_json(TUNING_PATH)
	model = OpinionModel.new(cfg, seed)
	max_turns = int((cfg.get("mission", {}) as Dictionary).get("maxTurns", 8))
	_comment_rng.randomize()  # 댓글은 표현층 — 매 게임 다르게(발각 RNG 와 무관)

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
	var available: Dictionary = {}   # 이번 턴 자료로 등장한 사실 (찌라시 게이팅용)
	for b in get_blocks():
		available[b["fact"]] = true
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

	# 이번 기사가 다룬 주제(보도 사실들의 topic) — 댓글을 이 주제에 맞춰 가중.
	var article_topics: Dictionary = {}
	for fid in reported:
		var ft: Variant = (content.get("facts", {}).get(fid, {}) as Dictionary).get("topic", null)
		if ft != null:
			article_topics[str(ft)] = true

	# 찌라시 자생 — 모델 step 이후(여론 수치와 무관), 댓글 피드에 섞어 보낸다.
	var rumors: Array = _rumor_step(reported, available)
	var feed: Array = _select_comments(frame_label, snapshot, article_topics)
	feed.append_array(rumors)

	var ending: String = check_ending()
	return {
		"snapshot": snapshot,
		"comments": feed,
		"rumors": rumors,
		"rumor_level": rumor_level,
		"rumor_heat": rumor_heat,
		"distortion": delta,
		"lean": lean,
		"fav_in": fav_in,   # 이번 기사에 실은 유리 사실 수
		"unf_in": unf_in,   # 이번 기사에 실은 불리(비판) 사실 수 — 편집 의도 판정용
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

func _select_comments(frame_label: String, snapshot: Dictionary, topics: Dictionary = {}) -> Array:
	var micro: Dictionary = snapshot.get("micro", {})
	var out: Array = []
	for s in model.config["segments"]:
		var seg_id: String = str(s["id"])
		var c: Dictionary = _pick_comment(seg_id, _reaction_for(seg_id, micro), frame_label, topics)
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

# ---------------------------------------------------------------------------
# 찌라시 자생 (기획서 §6 · 옵션 A: 허위 소문은 플레이어가 아니라 대중이 만든다)
# ---------------------------------------------------------------------------
## 이번 턴의 열기를 갱신하고, 굴림에 성공하면 찌라시 댓글을 배열로 돌려준다(0~1개).
## reported: 이번 턴 보도한 사실 id 집합. available: 이번 턴 자료로 등장한 사실 id 집합.
func _rumor_step(reported: Dictionary, available: Dictionary) -> Array:
	var cfg: Dictionary = tuning.get("rumor", {})
	if cfg.is_empty():
		return []

	for fid in available:
		_encountered_ever[fid] = true
	for fid in reported:
		_reported_ever[fid] = true

	# 1) 열기 갱신 — 턴 경과 + 이번 턴 다룬 소재의 기여도.
	rumor_heat += float(cfg.get("heat_per_turn", 0.0))
	var contrib: Dictionary = cfg.get("contrib", {})
	for fid in contrib:
		if reported.has(fid):
			rumor_heat += float(contrib[fid])
	# 회피도 신호다 — 비공개가 자료로 왔는데 지면에서 뺐다면 의심이 더 자란다.
	if available.has("F11") and not reported.has("F11"):
		rumor_heat += float(cfg.get("avoid_bonus", 0.0))

	# 2) 강도 — 임계 구간으로 올리되 내려가지 않는다.
	var thresholds: Array = cfg.get("level_thresholds", [0.0])
	var lv: int = 1
	for i in thresholds.size():
		if rumor_heat >= float(thresholds[i]):
			lv = i + 1
	rumor_level = maxi(rumor_level, lv)

	# 3) 자생 굴림 — 표현층 RNG 사용(모델 RNG 와 분리).
	var p: float = clampf(
		float(cfg.get("p_base", 0.0)) + rumor_heat * float(cfg.get("heat_gain", 0.0)),
		0.0, float(cfg.get("p_max", 1.0)))
	if _comment_rng.randf() >= p:
		return []

	# 4) 소재 게이팅 — 맥락이 열린 소문만 후보.
	var open_topics: Dictionary = {}
	var gates: Dictionary = cfg.get("gates", {})
	for topic in gates:
		var g: Variant = gates[topic]
		if not (g is Dictionary):
			continue
		var mode: String = str((g as Dictionary).get("mode", "reported"))
		var need: Array = (g as Dictionary).get("facts", [])
		var ok: bool = not need.is_empty()
		for fid in need:
			var seen: bool = _reported_ever.has(fid) if mode == "reported" \
				else _encountered_ever.has(fid)
			if not seen:
				ok = false
				break
		if ok:
			open_topics[topic] = true
	if open_topics.is_empty():
		return []

	# 5) 후보 추출 — 현재 강도 이하 중 가장 높은 단계를 고른다(그 소재에 3단계가
	#    없으면 있는 데까지). 이미 쓴 것은 제외.
	var segs: Array = cfg.get("segments", [])
	var pool: Array = _rumor_pool(open_topics, segs, true)
	if pool.is_empty():
		# 해당 강도의 소재를 다 썼다면 재사용을 허용한다. 한 번 확신형까지 간 소문이
		# 다시 "의혹 씨앗"으로 약해지는 것보다 반복이 낫다(서사 역행 금지).
		pool = _rumor_pool(open_topics, segs, false)
	if pool.is_empty():
		return []

	var pick: Dictionary = pool[_comment_rng.randi() % pool.size()]
	_rumor_used.append(str(pick.get("id", "")))
	_rumor_last_level = maxi(_rumor_last_level, int(pick.get("level", 1)))
	# {슬롯} 치환은 UI(main.gd _fill_slots)가 topic 기준 표로 처리한다 — 여기서 채우면
	# 맥락 없는 값이 들어가 오히려 품질이 떨어진다(단일 소유자 유지).
	return [pick]

## 현재 강도 구간(직전 발화 이상 ~ rumor_level 이하)의 후보를 모은다.
## fresh=true 면 이미 쓴 id 를 제외한다.
func _rumor_pool(open_topics: Dictionary, segs: Array, fresh: bool) -> Array:
	var pool: Array = []
	var best_lv: int = 0
	for c in content.get("comments", []):
		var r: String = str(c.get("rumor", ""))
		if r == "" or not open_topics.has(r):
			continue
		if not segs.is_empty() and not segs.has(str(c.get("seg", ""))):
			continue
		var clv: int = int(c.get("level", 1))
		if clv > rumor_level or clv < _rumor_last_level:
			continue   # 강도 역행 금지
		if fresh and _rumor_used.has(str(c.get("id", ""))):
			continue
		if clv > best_lv:
			best_lv = clv
			pool.clear()
		if clv == best_lv:
			pool.append(c)
	return pool


## 반복방어(기획서 9.3): seg+reaction 후보 풀 → 쿨다운 제외 → frame 가점 가중 랜덤.
## 같은 템플릿이 연속으로 재등장하지 않게 해 "가짜 티"를 막는다.
func _pick_comment(seg_id: String, reaction: String, frame_label: String, topics: Dictionary = {}) -> Dictionary:
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
		# 이번 기사가 다룬 주제의 댓글에 큰 가점 → '각 기사에 맞는' 반응이 우선 노출.
		var ct: Variant = c.get("topic", null)
		if ct != null and topics.has(str(ct)):
			w += 3.5
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
