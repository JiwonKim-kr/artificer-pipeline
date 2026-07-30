// 기레기 시뮬레이터 — 여론 확산 엔진 (런타임 탑재용, 의존성 0)
// 모델 계보: bounded-confidence 여론 동역학(Deffuant/HK) + 확증편향 대역 축소 + 역풍(backfire)
// 각 레버가 성향 축과 1:1로 물림: 프레임↔확증편향, 톤↔감정반응성, 채널↔매체소비.

const clamp01 = (v) => Math.max(0, Math.min(1, v));
const sign = (v) => (v > 0 ? 1 : v < 0 ? -1 : 0);

// 재현 가능한 시드 RNG (발각 확률 굴림용).
export function makeRng(seed = 1) {
  let a = seed >>> 0;
  return function () {
    a |= 0; a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

// 톤 효과 = 세그먼트 emo와 톤의 공명.
//  자극  → emo 높은 집단만 크게 반응(emo), 낮은 집단은 거의 무반응.
//  중립  → 누구에게나 평평한 기준선.
//  차분  → emo 낮은 집단(올드류)이 오히려 신뢰해 반응(1-emo), emo 높은 집단엔 밋밋.
export function toneEffectiveness(tone, emo) {
  if (tone === "자극") return emo;
  if (tone === "차분") return 1 - emo;
  return 0.5; // 중립
}

// 한 세그먼트가 한 기사에 대해 이번 턴 겪는 변화.
// seg: {x0,emo,conf,size,reach}, x: 현재 위치, article:{frameValue,tone,channel,distortion}
// R: 평판 계수(0~1), C: constants
export function updateSegment(seg, x, article, R, C) {
  const reach = seg.reach[article.channel] ?? 0; // 도달 게이트: 채널 안 맞으면 0
  const p = article.frameValue; // 프레임이 미는 위치
  const eps = C.epsMax * (1 - seg.conf); // 확증편향이 좁히는 수용 대역
  const d = Math.abs(p - x);
  const E = toneEffectiveness(article.tone, seg.emo);

  let dir, strength, accepted;
  if (d <= eps) {
    // 수용: 프레임 쪽으로 끌림. 가까울수록 강함.
    accepted = true;
    dir = sign(p - x);
    strength = 1 - d / (eps || 1e-9);
  } else {
    // 거부 → 역풍: 프레임 반대쪽으로 파고듦. 확증편향 강할수록 세다.
    accepted = false;
    dir = sign(x - p);
    const over = Math.min(1, (d - eps) / (1 - eps + 1e-9));
    strength = C.backfireCoef * seg.conf * over;
  }

  const distBoost = 1 + (article.distortion ?? 0) * C.distortionGain;
  const pull = C.k * reach * E * strength * dir * R * distBoost;
  const anchor = -C.anchorLambda * (x - seg.x0); // 기존입장으로의 관성

  const nx = clamp01(x + pull + anchor);
  return { nx, pull, anchor, reach, eps, d, E, strength, accepted, dir };
}

// 규모 가중 거시 여론.
export function macroOpinion(segments, xs) {
  let sum = 0, w = 0;
  for (const s of segments) { sum += s.size * xs[s.id]; w += s.size; }
  return sum / (w || 1);
}

// 접전도: 여론이 0.5에 가까울수록 1, 극단일수록 0. 발각 리스크 발동 강도.
export function contestedness(macro) {
  return 1 - Math.abs(2 * macro - 1);
}

// 게임 상태 컨테이너.
export function initState(config, seed = 1) {
  const xs = {};
  for (const s of config.segments) xs[s.id] = s.x0;
  const macro = macroOpinion(config.segments, xs);
  return {
    xs,
    tvMacro: macro,       // TV(느린 거시). 저역통과로 지연됨.
    reputation: config.reputation.start,
    lastFrameValue: null, // 논조 급변 감지용
    riskProb: 0,          // 누적 발각 확률 (왜곡할수록 증가)
    detections: [],       // 발각 이벤트 기록
    rng: makeRng(seed),
    turn: 0,
    log: [],
  };
}

// 한 턴 진행: 기사 1건 발행 → 각 세그먼트 즉시 반응(SNS 미시) → TV 거시 지연 반영.
// article: {frame:"찬성각"|..., tone, channel, distortion}
export function step(config, state, article) {
  const C = config.constants;
  const frameValue = config.levers.frame[article.frame];
  const a = { ...article, frameValue };

  // 평판: 직전 논조 대비 반대 방향으로 급변하면 하락, 유지하면 회복.
  const rep = config.reputation;
  if (state.lastFrameValue !== null) {
    const flipped = sign(frameValue - 0.5) !== 0 &&
      sign(frameValue - 0.5) === -sign(state.lastFrameValue - 0.5);
    state.reputation = flipped
      ? Math.max(rep.floor, state.reputation - rep.swingPenalty)
      : Math.min(1, state.reputation + rep.recover);
  }
  state.lastFrameValue = frameValue;

  const R = state.reputation;
  const micro = {}; // 세그먼트별 즉시 반응(화면3 SNS)
  for (const s of config.segments) {
    const r = updateSegment(s, state.xs[s.id], a, R, C);
    state.xs[s.id] = r.nx;
    micro[s.id] = r;
  }

  let macroNow = macroOpinion(config.segments, state.xs);
  const contested = contestedness(macroNow);

  // === 발각(확률 누적식) ===
  const det = config.detection;
  const delta = a.distortion ?? 0;
  if (delta > 0) {
    state.riskProb = clamp01(state.riskProb + det.manipStep * delta); // 왜곡할수록 증가
  } else {
    state.riskProb = Math.max(0, state.riskProb - det.honestDecay);   // 정직하면 소폭 냉각
  }

  let detection = null;
  if (state.riskProb > 0) {
    // 접전일수록 잘 들통남(화면2 TV 읽기 메커닉). weight=0이면 순수 누적확률.
    const effProb = clamp01(state.riskProb * (1 + det.contestednessWeight * (contested - 0.5) * 2));
    if (state.rng() < effProb) {
      // 단발성 충격: 크기는 걸린 시점의 riskProb에 비례.
      const damage = det.damageK * state.riskProb;
      const lean = sign(frameValue - 0.5); // 최근 밀던 방향
      for (const s of config.segments) {
        const shock = damage * (0.5 + 0.5 * s.emo); // 감정 집단이 배신감에 더 크게 등 돌림
        state.xs[s.id] = clamp01(state.xs[s.id] - lean * shock); // 밀던 방향의 반대로
      }
      // 평판의 '사실정확성' 축이 발각으로 드러나 지속 하락.
      state.reputation = Math.max(rep.floor, state.reputation - det.accuracyRepPenalty);
      detection = { turn: state.turn + 1, prob: effProb, riskAtCatch: state.riskProb, damage, lean };
      state.detections.push(detection);
      state.riskProb *= det.resetOnDetect; // 스캔들 소모 후 리셋
      macroNow = macroOpinion(config.segments, state.xs); // 충격 반영
    }
  }

  // TV는 즉시 값이 아니라 저역통과된 지연값 → 거시-미시 시차.
  state.tvMacro = state.tvMacro + C.macroLagAlpha * (macroNow - state.tvMacro);
  state.turn += 1;

  const snapshot = {
    turn: state.turn,
    article: a,
    reputation: state.reputation,
    xs: { ...state.xs },
    macroNow,
    tvMacro: state.tvMacro,
    contested,
    riskProb: state.riskProb,
    detection,
    micro,
  };
  state.log.push(snapshot);
  return snapshot;
}

export function isWon(config, state) {
  return state.xs[config.mission.target] >= config.mission.winThreshold;
}
