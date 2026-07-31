// 여론엔진 GDScript 이식 대조용 골든값 덤퍼.
// sim/opinion-model(오라클)을 읽기 전용으로 import 하고, 게임 런타임 config
// (src/core/data/opinion_config.json)로 실행해 골든을 생성한다 → 골든이 게임 config와 정합.
// 산출: pipeline/tests/fixtures/opinion_golden.json
// 재생성: node pipeline/tests/dump_opinion_golden.mjs
import { readFileSync, writeFileSync, mkdirSync } from "node:fs";
import { makeRng, initState, step } from "../../sim/opinion-model/opinion-model.mjs";

const config = JSON.parse(
  readFileSync(new URL("../../src/core/data/opinion_config.json", import.meta.url)),
);

// 1) RNG 골든: makeRng(1) 첫 16개 uint32 (f = uint/2^32 → uint = round(f*2^32), 2^32<2^53 이므로 정확)
const r = makeRng(1);
const rng_uint32 = [];
for (let i = 0; i < 16; i++) rng_uint32.push(Math.round(r() * 4294967296));

// 2) 시나리오① turn1 (정직 찬성각·자극·SNS, δ=0 → RNG 미호출)
const st = initState(config, 1);
step(config, st, { frame: "찬성각", tone: "자극", channel: "sns" });
const scenario1_turn1_xs = {};
for (const s of config.segments) scenario1_turn1_xs[s.id] = st.xs[s.id];

// 3) 발각 경로(RNG) 검증: δ=1 매턴, seed 1, 8턴 — 턴별 riskProb·발각·부동층
const st2 = initState(config, 1);
const distort_seed1 = [];
for (let t = 1; t <= 8; t++) {
  const sn = step(config, st2, { frame: "찬성각", tone: "자극", channel: "sns", distortion: 1.0 });
  distort_seed1.push({
    turn: t,
    riskProb: sn.riskProb,
    swing: st2.xs.sns_swing,
    detection: sn.detection ? { damage: sn.detection.damage, riskAtCatch: sn.detection.riskAtCatch } : null,
  });
}

const out = { rng_seed: 1, rng_uint32, scenario1_turn1_xs, distort_seed1 };
mkdirSync(new URL("./fixtures/", import.meta.url), { recursive: true });
writeFileSync(new URL("./fixtures/opinion_golden.json", import.meta.url), JSON.stringify(out, null, 2));
console.log("golden written:", JSON.stringify(out).length, "bytes");
