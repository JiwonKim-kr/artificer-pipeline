#!/usr/bin/env node
/**
 * encode_vorbis.js — PCM WAV → OGG Vorbis 인코더 (wasm-media-encoders 사용).
 *
 * 왜 존재하나: conventions.md 는 SE 를 「OGG Vorbis · 모노」로 규정하지만,
 * homebrew ffmpeg 8.x 슬림 빌드에는 libvorbis 가 없고 내장(native) vorbis
 * 인코더는 **스테레오 전용**이라 모노 OGG 를 만들 수 없다. 그래서 라우드니스
 * 정규화(ffmpeg loudnorm)까지는 ffmpeg 가 WAV 로 수행하고, 최종 Vorbis 인코딩만
 * 이 스크립트(libvorbis 의 WASM 빌드, MIT)가 담당한다. — se_post.py 가 ffmpeg 에
 * libvorbis 가 있으면 그것을 우선 쓰고, 없을 때만 여기로 폴백한다.
 *
 * 사용법: node encode_vorbis.js <in.wav> <out.ogg> [vbrQuality]
 *   - in.wav: PCM 16bit(le) 또는 8bit WAV (모노/스테레오)
 *   - vbrQuality: libvorbis VBR 품질 -1.0 ~ 1.0 (기본 0.5 ≈ oggenc -q5)
 *
 * stdout: {"out", "channels", "sample_rate", "bytes"} JSON 한 건.
 * 종료 코드: 0 = 성공, 1 = 인코딩 실패, 2 = 사용법/입력 오류.
 */
"use strict";

const fs = require("fs");
const path = require("path");

function fail(code, msg) {
  process.stderr.write(`오류: ${msg}\n`);
  process.exit(code);
}

/** 최소 WAV 파서 — RIFF/fmt/data 청크에서 PCM 을 Float32Array 채널 배열로. */
function parseWav(buf) {
  if (buf.length < 44 || buf.toString("ascii", 0, 4) !== "RIFF" ||
      buf.toString("ascii", 8, 12) !== "WAVE") {
    throw new Error("WAV(RIFF) 형식이 아닙니다.");
  }
  let pos = 12;
  let fmt = null;
  let data = null;
  while (pos + 8 <= buf.length) {
    const id = buf.toString("ascii", pos, pos + 4);
    const size = buf.readUInt32LE(pos + 4);
    const body = pos + 8;
    if (id === "fmt ") {
      fmt = {
        audioFormat: buf.readUInt16LE(body),
        channels: buf.readUInt16LE(body + 2),
        sampleRate: buf.readUInt32LE(body + 4),
        bitsPerSample: buf.readUInt16LE(body + 14),
      };
    } else if (id === "data") {
      data = buf.subarray(body, Math.min(body + size, buf.length));
    }
    pos = body + size + (size % 2); // 청크는 2바이트 정렬
  }
  if (!fmt || !data) throw new Error("fmt/data 청크를 찾지 못했습니다.");
  if (fmt.audioFormat !== 1) {
    throw new Error(`PCM(WAVE_FORMAT_PCM=1)만 지원합니다 (받음: ${fmt.audioFormat})`);
  }
  const { channels, bitsPerSample } = fmt;
  let frames;
  if (bitsPerSample === 16) {
    frames = Math.floor(data.length / 2 / channels);
  } else if (bitsPerSample === 8) {
    frames = Math.floor(data.length / channels);
  } else {
    throw new Error(`지원 샘플 크기: 8/16bit (받음: ${bitsPerSample}bit)`);
  }
  const planes = [];
  for (let c = 0; c < channels; c++) planes.push(new Float32Array(frames));
  for (let i = 0; i < frames; i++) {
    for (let c = 0; c < channels; c++) {
      if (bitsPerSample === 16) {
        planes[c][i] = data.readInt16LE((i * channels + c) * 2) / 32768;
      } else {
        planes[c][i] = (data[i * channels + c] - 128) / 128;
      }
    }
  }
  return { channels, sampleRate: fmt.sampleRate, planes };
}

async function main() {
  const argv = process.argv.slice(2);
  if (argv.length < 2 || argv.length > 3) {
    fail(2, "사용법: node encode_vorbis.js <in.wav> <out.ogg> [vbrQuality(-1..1)]");
  }
  const [inPath, outPath] = argv;
  const vbrQuality = argv[2] !== undefined ? Number(argv[2]) : 0.5;
  if (!Number.isFinite(vbrQuality) || vbrQuality < -1 || vbrQuality > 1) {
    fail(2, `vbrQuality 는 -1.0~1.0 이어야 합니다 (받음: ${argv[2]})`);
  }

  let wav;
  try {
    wav = parseWav(fs.readFileSync(inPath));
  } catch (e) {
    fail(2, `WAV 읽기 실패(${inPath}): ${e.message}`);
  }

  let createOggEncoder;
  try {
    ({ createOggEncoder } = require("wasm-media-encoders"));
  } catch (e) {
    fail(1, "wasm-media-encoders 모듈을 찾을 수 없습니다. " +
            "pipeline/scripts/se_node 에서 `npm install` 을 먼저 실행하세요.");
  }

  try {
    const encoder = await createOggEncoder();
    encoder.configure({
      channels: wav.channels,
      sampleRate: wav.sampleRate,
      vbrQuality,
    });
    const chunks = [];
    const c1 = encoder.encode(wav.planes);
    if (c1.length) chunks.push(Buffer.from(c1));
    const c2 = encoder.finalize();
    if (c2.length) chunks.push(Buffer.from(c2));
    const ogg = Buffer.concat(chunks);
    if (!ogg.length) throw new Error("인코더가 빈 출력을 반환했습니다.");
    fs.mkdirSync(path.dirname(path.resolve(outPath)), { recursive: true });
    fs.writeFileSync(outPath, ogg);
    process.stdout.write(JSON.stringify({
      out: outPath,
      channels: wav.channels,
      sample_rate: wav.sampleRate,
      bytes: ogg.length,
    }) + "\n");
  } catch (e) {
    fail(1, `Vorbis 인코딩 실패: ${e.message}`);
  }
}

main();
