#!/usr/bin/env node
/**
 * render_sfxr.js — jsfxr 파라미터/프리셋 → WAV 렌더러 (se 트랙 절차적 백엔드).
 *
 * jsfxr(npm, sfxr 포팅, 퍼블릭 도메인)은 프리셋 생성과 노이즈 파형 합성에
 * 전역 `Math.random()` 을 쓰므로 그대로는 재현이 불가능하다. 이 스크립트는
 * 렌더 전에 Math.random 을 **시드된 PRNG(mulberry32)** 로 교체해
 * 「seed + preset(+params) 고정 → 항상 동일한 WAV 바이트」를 보장한다.
 * (재현성 요구: pipeline/commands/se.md, HANDOFF §6-2)
 *
 * 사용법:
 *   node render_sfxr.js <spec.json | -> <out.wav>
 *   ('-' 는 stdin 에서 spec JSON 을 읽는다)
 *
 * spec JSON 형식 (모든 필드 선택, 최소 {}):
 *   {
 *     "seed": 12345,            // PRNG 시드 (기본 0)
 *     "preset": "pickupCoin",  // jsfxr 표준 프리셋 이름 (선택)
 *     "params": { ... },        // sfxr 직렬화 키 명시 오버레이 (선택, preset 뒤 적용)
 *     "sound_vol": 0.25,        // 최상위 단축 오버라이드 (선택)
 *     "sample_rate": 44100,
 *     "sample_size": 16
 *   }
 *
 * stdout: 렌더 결과 JSON 한 건 —
 *   { "out", "seed", "preset", "sha256", "bytes", "resolved_params" }
 * resolved_params 는 실제 렌더에 쓰인 전체 파라미터로, 이것을 spec.params 로
 * 되먹이면(seed 동일) 동일 WAV 가 재현된다. (매니페스트 params 기록용)
 *
 * 종료 코드: 0 = 성공, 1 = 렌더 실패, 2 = 사용법/인자 오류.
 */
"use strict";

const fs = require("fs");
const path = require("path");
const crypto = require("crypto");

// jsfxr 표준 프리셋 (sfxr.js Params.prototype 의 생성기 메서드들)
const PRESETS = [
  "pickupCoin", "laserShoot", "explosion", "powerUp",
  "hitHurt", "jump", "blipSelect", "synth", "tone", "click", "random",
];

/** mulberry32 — 32bit 시드 결정적 PRNG. [0,1) 반환 (Math.random 호환). */
function mulberry32(seed) {
  let a = seed >>> 0;
  return function () {
    a |= 0;
    a = (a + 0x6d2b79f5) | 0;
    let t = Math.imul(a ^ (a >>> 15), 1 | a);
    t = (t + Math.imul(t ^ (t >>> 7), 61 | t)) ^ t;
    return ((t ^ (t >>> 14)) >>> 0) / 4294967296;
  };
}

function usage(msg) {
  if (msg) process.stderr.write(`오류: ${msg}\n`);
  process.stderr.write(
    "사용법: node render_sfxr.js <spec.json | -> <out.wav>\n" +
    `프리셋: ${PRESETS.join(", ")}\n`,
  );
  process.exit(2);
}

function main() {
  const argv = process.argv.slice(2);
  if (argv.length !== 2) usage("인자는 <spec> <out.wav> 2개여야 합니다.");
  const [specArg, outPath] = argv;

  let specText;
  try {
    specText = specArg === "-"
      ? fs.readFileSync(0, "utf-8")
      : fs.readFileSync(specArg, "utf-8");
  } catch (e) {
    usage(`spec 을 읽을 수 없습니다: ${e.message}`);
  }
  let spec;
  try {
    spec = JSON.parse(specText);
  } catch (e) {
    usage(`spec JSON 파싱 실패: ${e.message}`);
  }
  if (typeof spec !== "object" || spec === null || Array.isArray(spec)) {
    usage("spec 최상위는 객체여야 합니다.");
  }
  if (spec.preset !== undefined && !PRESETS.includes(spec.preset)) {
    usage(`알 수 없는 preset: ${spec.preset} (가능: ${PRESETS.join(", ")})`);
  }

  const seed = Number.isInteger(spec.seed) ? spec.seed : 0;

  // ── 재현성 핵심: jsfxr 로드 전에 Math.random 을 시드 PRNG 로 교체 ──
  Math.random = mulberry32(seed);

  let sfxr;
  try {
    sfxr = require("jsfxr");
  } catch (e) {
    process.stderr.write(
      "오류: jsfxr 모듈을 찾을 수 없습니다. pipeline/scripts/se_node 에서 " +
      "`npm install` 을 먼저 실행하세요.\n",
    );
    process.exit(1);
  }

  try {
    const parameters = new sfxr.Params();
    // 기본값 (jsfxr 동봉 CLI 와 동일 취지, 다만 양자화 노이즈를 줄이기 위해 16bit)
    parameters.sound_vol = 0.25;
    parameters.sample_rate = 44100;
    parameters.sample_size = 16;

    if (spec.preset) parameters[spec.preset]();

    // 명시 파라미터 오버레이 (preset 결과 위에 덮어씀 — 부분 지정 가능)
    if (spec.params && typeof spec.params === "object") {
      for (const k of Object.keys(spec.params)) parameters[k] = spec.params[k];
    }
    // 최상위 단축 오버라이드
    for (const k of ["sound_vol", "sample_rate", "sample_size"]) {
      if (spec[k] !== undefined) parameters[k] = spec[k];
    }

    const sound = new sfxr.SoundEffect(parameters).generate();
    const m = /^data:.+\/(.+);base64,(.*)$/.exec(sound.dataURI);
    if (!m) throw new Error("jsfxr 가 data URI 를 반환하지 않았습니다.");
    const wav = Buffer.from(m[2], "base64");

    fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
    fs.writeFileSync(outPath, wav);

    // 재현 기록: 실제 렌더에 쓰인 전체 파라미터 (메서드 제외 own property 만)
    const resolved = JSON.parse(JSON.stringify(parameters));
    process.stdout.write(JSON.stringify({
      out: outPath,
      seed,
      preset: spec.preset || null,
      sha256: crypto.createHash("sha256").update(wav).digest("hex"),
      bytes: wav.length,
      resolved_params: resolved,
    }) + "\n");
  } catch (e) {
    process.stderr.write(`오류: 렌더 실패 — ${e.message}\n`);
    process.exit(1);
  }
}

main();
