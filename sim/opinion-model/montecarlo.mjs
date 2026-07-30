import { readFileSync } from "node:fs";
import { initState, step, isWon } from "./opinion-model.mjs";
const config = JSON.parse(readFileSync(new URL("./config.json", import.meta.url)));

function runOnce(play, seed) {
  const st = initState(config, seed);
  let won = false, wonTurn = null, detections = 0, totalDamage = 0, firstDetectRisk = null;
  for (let t = 1; t <= config.mission.maxTurns; t++) {
    const snap = step(config, st, play(t, st));
    if (snap.detection) {
      detections++; totalDamage += snap.detection.damage;
      if (firstDetectRisk === null) firstDetectRisk = snap.detection.riskAtCatch;
    }
    if (!won && isWon(config, st)) { won = true; wonTurn = t; }
  }
  won = isWon(config, st); // 마감일 시점 최종 판정
  return { won, wonTurn, detections, totalDamage, endX: st.xs[config.mission.target], rep: st.reputation, firstDetectRisk };
}

function monteCarlo(name, play, N = 4000) {
  let wins = 0, sumTurn = 0, turnN = 0, anyDetect = 0, sumDet = 0, sumDmg = 0, sumEndX = 0, sumRep = 0, sumFirstRisk = 0, firstRiskN = 0;
  for (let i = 0; i < N; i++) {
    const r = runOnce(play, i * 2654435761 + 1);
    if (r.won) { wins++; if (r.wonTurn) { sumTurn += r.wonTurn; turnN++; } }
    if (r.detections > 0) anyDetect++;
    sumDet += r.detections; sumDmg += r.totalDamage; sumEndX += r.endX; sumRep += r.rep;
    if (r.firstDetectRisk !== null) { sumFirstRisk += r.firstDetectRisk; firstRiskN++; }
  }
  const p = (v) => (v * 100).toFixed(1) + "%";
  console.log(`\n[${name}]  (N=${N})`);
  console.log(`  승률            ${p(wins / N)}` + (turnN ? `   평균 승리턴 ${(sumTurn / turnN).toFixed(1)}` : ""));
  console.log(`  발각 경험 비율  ${p(anyDetect / N)}   판당 평균 발각횟수 ${(sumDet / N).toFixed(2)}`);
  console.log(`  마감 시 부동층  ${p(sumEndX / N)}   평균 평판 ${p(sumRep / N)}`);
  if (firstRiskN) console.log(`  첫 발각시 riskProb 평균 ${p(sumFirstRisk / firstRiskN)}   판당 평균 총피해 ${(sumDmg / N).toFixed(3)}`);
}

const honest = () => ({ frame: "찬성각", tone: "자극", channel: "sns" });
const alwaysDistort = () => ({ frame: "찬성각", tone: "자극", channel: "sns", distortion: 1.0 });
const oneDistort = (t) => ({ frame: "찬성각", tone: "자극", channel: "sns", distortion: t === 1 ? 1.0 : 0 });
// 영리한 왜곡: 초반 2턴만 강하게 왜곡하고 이후 정직(리스크 관리)
const smartDistort = (t) => ({ frame: "찬성각", tone: "자극", channel: "sns", distortion: t <= 2 ? 1.0 : 0 });

console.log("=== 발각 메커닉 몬테카를로: 정직 vs 왜곡 전략 ===");
monteCarlo("정직 (왜곡 0)", honest);
monteCarlo("항상 왜곡 (δ=1 매턴)", alwaysDistort);
monteCarlo("가벼운 왜곡 (1턴만)", oneDistort);
monteCarlo("영리한 왜곡 (초반 2턴만)", smartDistort);

// 접전도 가중 on/off 비교
console.log("\n=== 접전도 가중 영향 (항상 왜곡) ===");
for (const cw of [0.0, 0.6, 1.2]) {
  config.detection.contestednessWeight = cw;
  process.stdout.write(`contestednessWeight=${cw.toFixed(1)}: `);
  let d = 0, N = 3000;
  for (let i = 0; i < N; i++) d += runOnce(smartDistort, i * 40503 + 7).detections > 0 ? 1 : 0;
  console.log(`발각 경험 ${((d / N) * 100).toFixed(1)}%`);
}
