// C6 밸런싱 몬테카를로 — 게임 계층(turn_manager.publish)과 동일한 도출식으로
// 전략별 승률·발각파탄률·평균 승리턴을 측정한다. (개발 계층 — 웹빌드 제외)
//
// 게임과 동일 조건: tone/channel 은 lever_tuning 고정값, frameValue/δ 는
//   lean = 유리노출 + 불리은폐 − 불리노출, frameValue = clamp(0.5 + k_lean·lean, 0.2, 0.8),
//   δ = clamp01(w_omit · 불리은폐수)  (turn_manager.publish 미러)
// 종료 판정: 발각 RUIN_AT회+ → 파탄 / 목표 도달 → 성공 / MAX_TURNS 도달 → 실패
//   (turn_manager.check_ending 미러 — 압박은 찬성 전략만 다루므로 제외)
//
// 실행: node sim/opinion-model/balance_montecarlo.mjs
// 근거 기록: docs/build/c6_balance.md
import { readFileSync } from "node:fs";
import { step, initState, isWon } from "./opinion-model.mjs";

const config = JSON.parse(readFileSync(new URL("../../src/core/data/opinion_config.json", import.meta.url)));
const tuning = JSON.parse(readFileSync(new URL("../../src/core/lever_tuning.json", import.meta.url)));
const content = JSON.parse(readFileSync(new URL("../../src/core/data/content_slice.json", import.meta.url)));

const MAX_TURNS = config.mission.maxTurns;
const RUIN_AT = 3; // turn_manager.DETECT_BREAK 와 일치시킬 것
const N = 4000;

// 기본 풀(분기 미개방): F15(hidden)·F16(gated) 제외 조각 태그 집계
let N_FAV = 0, N_UNF = 0;
for (const f of Object.values(content.facts)) {
  if (f.hidden || f.gated) continue;
  for (const fr of f.fragments) {
    if (fr.tag === "유리") N_FAV++;
    else if (fr.tag === "불리") N_UNF++;
  }
}

const clamp01 = (v) => Math.min(1, Math.max(0, v));
function derive(f, h) {
  const lean = f + h - (N_UNF - h);
  return { frameValue: Math.min(0.8, Math.max(0.2, 0.5 + tuning.k_lean * lean)),
           tone: tuning.tone, channel: tuning.channel,
           distortion: clamp01(tuning.w_omit * h) };
}

// 전략: 상태 → [유리노출수, 불리은폐수]
const strategies = {
  "정직(전부공개)":  () => [N_FAV, 0],
  "은폐1(최소왜곡)": () => [N_FAV, 1],
  "은폐2(중간왜곡)": () => [N_FAV, 2],
  "은폐전부(δ=1)":   () => [N_FAV, N_UNF],
  "적응형(0.62까지 은폐2→정직)": (st) =>
    st.xs[config.mission.target] < 0.62 ? [N_FAV, 2] : [N_FAV, 0],
};

console.log(`config: maxTurns=${MAX_TURNS} winThreshold=${config.mission.winThreshold} ` +
  `manipStep=${config.detection.manipStep} 파탄임계=${RUIN_AT} · 풀: 유리 ${N_FAV}/불리 ${N_UNF} · N=${N}`);
console.log("전략".padEnd(28) + "성공%   평균승리턴   발각파탄%   실패%   평균발각");
for (const [name, fn] of Object.entries(strategies)) {
  let win = 0, ruin = 0, fail = 0, winTurns = 0, dets = 0;
  for (let s = 1; s <= N; s++) {
    const st = initState(config, s);
    let end = "실패";
    for (let t = 0; t < MAX_TURNS; t++) {
      const [f, h] = fn(st);
      step(config, st, derive(f, h));
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
