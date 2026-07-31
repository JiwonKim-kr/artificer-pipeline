import { readFileSync } from "node:fs";
import { initState, step, isWon, macroOpinion, contestedness } from "./opinion-model.mjs";

// config 단일 출처: 게임 런타임과 공유(sim은 이 파일을 읽기만). spec 선행작업 A.
const config = JSON.parse(readFileSync(new URL("../../src/core/data/opinion_config.json", import.meta.url)));
const SEG = config.segments.map((s) => s.id);
const LABEL = Object.fromEntries(config.segments.map((s) => [s.id, s.label]));

const pct = (v) => (v * 100).toFixed(0).padStart(3) + "%";
function row(label, obj) {
  return label.padEnd(16) + SEG.map((id) => pct(obj[id])).join("  ");
}
function header() {
  return "턴".padEnd(16) + config.segments.map((s) => s.label.slice(0, 5).padStart(4)).join("  ");
}

function runScenario(name, articleForTurn) {
  const state = initState(config);
  console.log("\n=== " + name + " ===");
  console.log(header() + "   | 거시TV  접전  평판  승리?");
  console.log(row("초기값(x0)", state.xs));
  for (let t = 1; t <= config.mission.maxTurns; t++) {
    const art = articleForTurn(t, state);
    const snap = step(config, state, art);
    const won = isWon(config, state);
    const tag = `${art.frame}/${art.tone}/${art.channel}` + (art.distortion ? `+왜곡${art.distortion}` : "");
    const detMark = snap.detection ? `⚡발각(피해${snap.detection.damage.toFixed(2)})` : "";
    console.log(
      row(`T${t} ${tag}`.slice(0, 16), snap.xs) +
      `   | ${pct(snap.tvMacro)}  ${pct(snap.contested)}  ${pct(snap.reputation)}  리스크${pct(snap.riskProb)}  ${won ? "★승리" : ""}${detMark}`
    );
    if (won) { console.log(`  → ${LABEL[config.mission.target]} ${config.mission.winThreshold * 100}% 도달: ${t}턴`); break; }
  }
}

// 1) 부동층 전향 최적 플레이(정직): 찬성각 + 자극 + SNS 반복
runScenario("① 부동층 공략 (찬성각·자극·SNS, 정직)", () => ({ frame: "찬성각", tone: "자극", channel: "sns" }));

// 2) 같은 기사를 반대층 관점에서: 역풍 검증 (전체 궤적에서 반대층 열 확인)
runScenario("② 역풍 검증 (찬성각·자극·SNS) — 반대층이 오히려 내려가야", () => ({ frame: "찬성각", tone: "자극", channel: "sns" }));

// 3) 올드 찬성층 채널벽: SNS로만 찬성 강화 시 도달 실패
runScenario("③ 채널벽 (SNS만 사용) — 올드찬성층 거의 안 움직여야", () => ({ frame: "찬성각", tone: "차분", channel: "sns" }));
runScenario("③' 올드 채널 사용 — 올드찬성층엔 닿음", () => ({ frame: "찬성각", tone: "차분", channel: "old" }));

// 4) 논조 급변 페널티: 홀수턴 찬성각 / 짝수턴 반대각 → 평판 급락 확인
runScenario("④ 논조 급변 (찬성각↔반대각 번갈아) — 평판 급락", (t) => ({
  frame: t % 2 === 1 ? "찬성각" : "반대각", tone: "자극", channel: "sns",
}));

// 5) 왜곡 트레이드오프: 즉시 효과는 크나 접전일 때 리스크 (여기선 이동폭만 확인)
runScenario("⑤ 왜곡 부스트 (찬성각·자극·SNS·왜곡0.8)", () => ({
  frame: "찬성각", tone: "자극", channel: "sns", distortion: 0.8,
}));

// 6) 톤 스윕: 부동층에 자극 vs 차분 (감정반응성 반응 차이)
console.log("\n=== ⑥ 톤 효과 비교 (부동층, 찬성각·SNS 1턴) ===");
for (const tone of ["차분", "중립", "자극"]) {
  const st = initState(config);
  const snap = step(config, st, { frame: "찬성각", tone, channel: "sns" });
  console.log(`  ${tone.padEnd(3)} → 부동층 50% → ${pct(snap.xs.sns_swing)}   반대층 → ${pct(snap.xs.sns_against)}`);
}
