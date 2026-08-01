// C6/CB3 밸런싱 몬테카를로 — 게임 계층(turn_manager.publish)과 동일 도출식 + 8턴 비트시트.
// 게임과 동일 조건:
//   턴 t 가용 풀 = 사실 중 (turn<=t, hidden/gated 제외)의 유리/불리 조각 집계 (get_blocks 미러)
//   lean = 유리노출 + 불리은폐 − 불리노출, frameValue = clamp(0.5 + k_lean·lean, 0.2, 0.8),
//   δ = clamp01(w_omit · 불리은폐수)
// 종료: 발각 RUIN_AT회+ → 파탄 / 목표 도달 → 성공 / MAX_TURNS 도달 → 실패
//   (turn_manager.check_ending 미러 — 압박은 찬성 전략만 다루므로 제외)
// 실행: node sim/opinion-model/balance_montecarlo.mjs · 근거 기록: docs/build/c6_balance.md
import { readFileSync } from "node:fs";
import { step, initState, isWon } from "./opinion-model.mjs";

const config = JSON.parse(readFileSync(new URL("../../src/core/data/opinion_config.json", import.meta.url)));
const tuning = JSON.parse(readFileSync(new URL("../../src/core/lever_tuning.json", import.meta.url)));
const content = JSON.parse(readFileSync(new URL("../../src/core/data/content_slice.json", import.meta.url)));

const MAX_TURNS = config.mission.maxTurns;
const RUIN_AT = 3; // turn_manager.DETECT_BREAK 와 일치시킬 것
const N = 4000;
const clamp01 = (v) => Math.min(1, Math.max(0, v));

// 턴 t(1-based 이번 턴)의 가용 풀 — get_blocks 의 hidden/gated/turn 필터를 미러.
function poolAt(t) {
  let fav = 0, unf = 0;
  for (const f of Object.values(content.facts)) {
    if (f.hidden || f.gated) continue;
    const ft = f.turn || 0;
    if (ft > 0 && ft > t) continue;
    for (const fr of f.fragments) {
      if (fr.tag === "유리") fav++;
      else if (fr.tag === "불리") unf++;
    }
  }
  return { fav, unf };
}
function derive(fav, unf, h) { // h = 불리은폐수
  const lean = fav + h - (unf - h);
  return {
    frameValue: Math.min(0.8, Math.max(0.2, 0.5 + tuning.k_lean * lean)),
    tone: tuning.tone, channel: tuning.channel,
    distortion: clamp01(tuning.w_omit * h),
  };
}

// 전략: (턴 t, 풀, 상태) → 이번 턴 불리은폐수 h. 유리는 항상 전량 노출.
const strategies = {
  "정직(전부공개)":  (t, p) => 0,
  "은폐1(최소왜곡)": (t, p) => Math.min(1, p.unf),
  "은폐2(중간왜곡)": (t, p) => Math.min(2, p.unf),
  "은폐전부(δ=1)":   (t, p) => p.unf,
  "적응형(0.62까지 은폐2→정직)": (t, p, st) =>
    st.xs[config.mission.target] < 0.62 ? Math.min(2, p.unf) : 0,
  // 캡(frameValue 0.8 = lean≥3)에 필요한 최소 은폐만 — 이론상 최적선
  "최적(캡유지 최소은폐)": (t, p) =>
    Math.max(0, Math.min(p.unf, Math.ceil((3 - p.fav + p.unf) / 2))),
};

console.log(`config: maxTurns=${MAX_TURNS} winThreshold=${config.mission.winThreshold} ` +
  `manipStep=${config.detection.manipStep} k_lean=${tuning.k_lean} w_omit=${tuning.w_omit} 파탄임계=${RUIN_AT} · N=${N}`);
console.log("풀(턴1→8 불리):", Array.from({length: MAX_TURNS}, (_, i) => poolAt(i + 1).unf).join(" "));
console.log("전략".padEnd(28) + "성공%   평균승리턴   발각파탄%   실패%   평균발각");
for (const [name, fn] of Object.entries(strategies)) {
  let win = 0, ruin = 0, fail = 0, winTurns = 0, dets = 0;
  for (let s = 1; s <= N; s++) {
    const st = initState(config, s);
    let end = "실패";
    for (let t = 1; t <= MAX_TURNS; t++) {
      const p = poolAt(t);
      step(config, st, derive(p.fav, p.unf, fn(t, p, st)));
      if (st.detections.length >= RUIN_AT) { end = "파탄"; break; }
      if (isWon(config, st)) { end = "성공"; break; }
    }
    dets += st.detections.length;
    if (end === "성공") { win++; winTurns += st.turn; }
    else if (end === "파탄") ruin++;
    else fail++;
  }
  console.log([
    name.padEnd(26),
    (100 * win / N).toFixed(1).padStart(6),
    win ? (winTurns / win).toFixed(2).padStart(9) : "-".padStart(9),
    (100 * ruin / N).toFixed(1).padStart(9),
    (100 * fail / N).toFixed(1).padStart(7),
    (dets / N).toFixed(2).padStart(8),
  ].join("  "));
}
