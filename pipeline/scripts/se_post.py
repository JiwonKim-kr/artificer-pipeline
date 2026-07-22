#!/usr/bin/env python3
"""se 오디오 후처리 (ffmpeg 8.x) — 포맷 정규화 + 라우드니스 측정/검증.

`se gen` 의 두 백엔드(ElevenLabs=mp3 등 / jsfxr=WAV)가 만든 원시 오디오를
**conventions.md 오디오 규격**으로 정규화한다:
  - 포맷: OGG Vorbis
  - SE: 모노, **-16 LUFS** 정규화

처리 구조 (2단):
  1) ffmpeg **2-pass loudnorm** (1차 측정 → 2차 linear 게인) → 정규화된 PCM WAV.
     채널 다운믹스는 측정 **이전**(필터 체인 앞)에 수행해 모노 신호 기준으로
     정규화한다. loudnorm 내부 192k 업샘플은 -ar 로 되돌린다.
  2) Vorbis 인코딩 — 인코더 자동 선택:
       libvorbis (ffmpeg 에 있으면 최우선)
       → wasm libvorbis (pipeline/scripts/se_node/encode_vorbis.js — homebrew
         ffmpeg 8 슬림 빌드에 libvorbis 가 없을 때의 기본 경로)
       → ffmpeg 내장 vorbis (실험적·**스테레오 전용**이라 채널 2 일 때만)
     어느 것도 불가능하면 한국어 안내와 함께 실패한다.

서브커맨드:
  normalize  입력(WAV/MP3/기타) → OGG Vorbis (위 2단 파이프). 출력 실측까지 보고.
  probe      코덱/채널/샘플레이트/길이 + 라우드니스(BS.1770 integrated, true
             peak)를 JSON 보고. --expect-* 로 검증 게이트로도 사용(허용오차 밖
             이면 종료 코드 1). ffmpeg 의 vorbis **디코더**는 항상 내장이라
             어떤 인코더로 만든 OGG 든 측정 가능하다.

장르/트랙 상수 하드코딩 없음 — 목표 LUFS·채널 수는 인자(데이터)로 받는다.
(SE 기본값 -16/모노는 conventions.md 규격의 기본치일 뿐이며, BGM(-14/스테레오)도
같은 스크립트로 표현 가능하다. bgm gen 자체는 후순위 — pipeline/commands/se.md.)

종료 코드: 0 = 성공/검증 통과, 1 = 처리 실패/검증 불통과, 2 = 실행/인자 오류.
stdlib 만 사용. ffmpeg/ffprobe 는 PATH 또는 FFMPEG_BIN/FFPROBE_BIN,
node 는 NODE_BIN 재정의 가능.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

# SE 기본 규격 (conventions.md) — 인자로 재정의 가능한 '기본값'일 뿐이다.
DEFAULT_TARGET_I = -16.0     # integrated loudness (LUFS)
DEFAULT_TARGET_TP = -1.5     # true peak (dBTP)
DEFAULT_TARGET_LRA = 11.0    # loudness range
DEFAULT_CHANNELS = 1         # SE 는 모노
DEFAULT_SAMPLE_RATE = 44100  # loudnorm 내부 192k 업샘플 → 출력에서 되돌린다
DEFAULT_VORBIS_Q = 5.0       # libvorbis qscale 기준 (0~10). wasm 경로에선 -1~1 로 환산.


def _ffmpeg() -> str:
    return os.environ.get("FFMPEG_BIN", "ffmpeg")


def _ffprobe() -> str:
    return os.environ.get("FFPROBE_BIN", "ffprobe")


def _node_bin() -> str:
    return os.environ.get("NODE_BIN", "node")


def _encode_vorbis_js() -> Path:
    # pipeline/scripts/se_post.py -> pipeline/scripts/se_node/encode_vorbis.js
    return Path(__file__).resolve().parent / "se_node" / "encode_vorbis.js"


def _require_tools() -> str | None:
    for tool, name in ((_ffmpeg(), "ffmpeg"), (_ffprobe(), "ffprobe")):
        if shutil.which(tool) is None and not Path(tool).exists():
            return (f"{name} 실행 파일을 찾을 수 없습니다 ({tool!r}). "
                    f"설치하거나 FFMPEG_BIN/FFPROBE_BIN 지정.")
    return None


def _channel_layout(channels: int) -> str:
    layouts = {1: "mono", 2: "stereo"}
    if channels not in layouts:
        raise ValueError(f"지원하지 않는 채널 수: {channels} (1=mono, 2=stereo)")
    return layouts[channels]


# ---------------------------------------------------------------------------
# Vorbis 인코더 가용성 탐지
# ---------------------------------------------------------------------------
def detect_encoders() -> dict[str, bool]:
    """{'libvorbis': bool, 'wasm': bool, 'native_vorbis': bool} 를 보고한다."""
    out = {"libvorbis": False, "wasm": False, "native_vorbis": False}
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-encoders"], capture_output=True, text=True,
    )
    if proc.returncode == 0:
        for line in proc.stdout.splitlines():
            cols = line.split()
            if len(cols) >= 2 and cols[1] == "libvorbis":
                out["libvorbis"] = True
            if len(cols) >= 2 and cols[1] == "vorbis":
                out["native_vorbis"] = True
    node_ok = shutil.which(_node_bin()) is not None or Path(_node_bin()).exists()
    wasm_mod = _encode_vorbis_js().parent / "node_modules" / "wasm-media-encoders"
    out["wasm"] = node_ok and _encode_vorbis_js().exists() and wasm_mod.exists()
    return out


# ---------------------------------------------------------------------------
# loudnorm 측정 (1-pass 분석)
# ---------------------------------------------------------------------------
def _extract_json_block(stderr: str) -> dict:
    """ffmpeg stderr 에서 loudnorm 의 print_format=json 블록을 추출한다."""
    anchor = stderr.rfind('"input_i"')
    if anchor == -1:
        raise RuntimeError(
            "loudnorm 측정 JSON 을 찾지 못했습니다:\n" + stderr.strip()[-800:]
        )
    start = stderr.rfind("{", 0, anchor)
    end = stderr.find("}", anchor)
    if start == -1 or end == -1:
        raise RuntimeError("loudnorm JSON 블록 경계를 찾지 못했습니다.")
    return json.loads(stderr[start:end + 1])


def measure_loudness(
    src: Path,
    *,
    target_i: float = DEFAULT_TARGET_I,
    target_tp: float = DEFAULT_TARGET_TP,
    target_lra: float = DEFAULT_TARGET_LRA,
    channels: int | None = None,
) -> dict:
    """loudnorm 분석 패스로 라우드니스를 측정한다 (파일 미변경).

    channels 지정 시 해당 레이아웃으로 다운믹스한 **뒤** 측정한다
    (normalize 의 2-pass 1차 측정과 동일 조건을 만들기 위함).
    반환 키: input_i, input_tp, input_lra, input_thresh, target_offset (float).
    """
    af = []
    if channels is not None:
        af.append(f"aformat=channel_layouts={_channel_layout(channels)}")
    af.append(
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}:print_format=json"
    )
    proc = subprocess.run(
        [_ffmpeg(), "-hide_banner", "-nostats", "-i", str(src),
         "-af", ",".join(af), "-f", "null", "-"],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"loudnorm 측정 실패: {proc.stderr.strip()[-800:]}")
    raw = _extract_json_block(proc.stderr)
    out: dict = {}
    for key in ("input_i", "input_tp", "input_lra", "input_thresh", "target_offset"):
        if key in raw:
            out[key] = float(raw[key])
    return out


def probe_format(src: Path) -> dict:
    """코덱/채널/샘플레이트/길이 를 ffprobe 로 보고."""
    proc = subprocess.run(
        [_ffprobe(), "-v", "error", "-select_streams", "a:0",
         "-show_entries", "stream=codec_name,channels,sample_rate",
         "-show_entries", "format=duration",
         "-of", "json", str(src)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {proc.stderr.strip()}")
    data = json.loads(proc.stdout)
    streams = data.get("streams", [])
    if not streams:
        raise RuntimeError(f"오디오 스트림 없음: {src}")
    s = streams[0]
    duration_raw = (data.get("format") or {}).get("duration")
    return {
        "codec": s.get("codec_name"),
        "channels": s.get("channels"),
        "sample_rate": int(s.get("sample_rate", 0)),
        "duration": float(duration_raw) if duration_raw else None,
    }


# ---------------------------------------------------------------------------
# normalize (2-pass loudnorm → WAV → Vorbis 인코딩)
# ---------------------------------------------------------------------------
def _loudnorm_to_wav(
    src: Path, wav_dst: Path, *, measured: dict,
    target_i: float, target_tp: float, target_lra: float,
    channels: int, sample_rate: int,
) -> None:
    """2차 패스: 측정값 주입 + linear 게인 → 정규화된 PCM WAV."""
    layout = _channel_layout(channels)
    loudnorm = (
        f"loudnorm=I={target_i}:TP={target_tp}:LRA={target_lra}"
        f":measured_I={measured['input_i']}:measured_TP={measured['input_tp']}"
        f":measured_LRA={measured['input_lra']}:measured_thresh={measured['input_thresh']}"
        f":offset={measured.get('target_offset', 0.0)}:linear=true"
    )
    af = f"aformat=channel_layouts={layout},{loudnorm}"
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-hide_banner", "-nostats", "-i", str(src),
         "-af", af, "-ar", str(sample_rate), "-ac", str(channels),
         "-c:a", "pcm_s16le", str(wav_dst)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg loudnorm 실패: {proc.stderr.strip()[-800:]}")


def _encode_ogg(wav_src: Path, dst: Path, *, channels: int, vorbis_q: float) -> str:
    """정규화된 WAV → OGG Vorbis. 사용한 인코더 이름을 반환한다."""
    enc = detect_encoders()
    dst.parent.mkdir(parents=True, exist_ok=True)

    if enc["libvorbis"]:
        proc = subprocess.run(
            [_ffmpeg(), "-y", "-hide_banner", "-nostats", "-i", str(wav_src),
             "-c:a", "libvorbis", "-qscale:a", str(vorbis_q), str(dst)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"libvorbis 인코딩 실패: {proc.stderr.strip()[-500:]}")
        return "libvorbis"

    if enc["wasm"]:
        # libvorbis qscale(0~10) → wasm vbrQuality(-1~1) 환산
        vbr = max(-1.0, min(1.0, (vorbis_q - 5.0) / 5.0))
        proc = subprocess.run(
            [_node_bin(), str(_encode_vorbis_js()), str(wav_src), str(dst), str(vbr)],
            capture_output=True, text=True, timeout=120,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"wasm Vorbis 인코딩 실패: {proc.stderr.strip()[-500:]}")
        return "wasm-libvorbis"

    if enc["native_vorbis"] and channels == 2:
        # ffmpeg 내장 vorbis 는 실험적·스테레오 전용.
        proc = subprocess.run(
            [_ffmpeg(), "-y", "-hide_banner", "-nostats", "-i", str(wav_src),
             "-c:a", "vorbis", "-strict", "experimental", str(dst)],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"내장 vorbis 인코딩 실패: {proc.stderr.strip()[-500:]}")
        return "native-vorbis"

    raise RuntimeError(
        "사용 가능한 Vorbis 인코더가 없습니다.\n"
        "      해결 방법 (하나 선택):\n"
        "        a) cd pipeline/scripts/se_node && npm install   (wasm libvorbis — 권장)\n"
        "        b) libvorbis 포함 ffmpeg 설치 (예: brew 서드파티 full 빌드)\n"
        f"      (ffmpeg 내장 vorbis 는 스테레오 전용이라 채널 {channels} 을 만들 수 없습니다.)"
    )


def normalize_audio(
    src: Path,
    dst: Path,
    *,
    target_i: float = DEFAULT_TARGET_I,
    target_tp: float = DEFAULT_TARGET_TP,
    target_lra: float = DEFAULT_TARGET_LRA,
    channels: int = DEFAULT_CHANNELS,
    sample_rate: int = DEFAULT_SAMPLE_RATE,
    vorbis_q: float = DEFAULT_VORBIS_Q,
) -> dict:
    """입력 오디오를 목표 LUFS 의 OGG Vorbis 로 정규화한다 (2-pass linear).

    반환: {"measured": 1차 측정값, "encoder": 사용 인코더,
           "output": 결과 포맷+라우드니스 재측정값}.
    """
    if dst.suffix.lower() != ".ogg":
        raise ValueError(f"출력은 .ogg 여야 합니다 (conventions.md): {dst}")

    # 1차: 다운믹스 후 측정
    measured = measure_loudness(
        src, target_i=target_i, target_tp=target_tp, target_lra=target_lra,
        channels=channels,
    )
    if measured.get("input_i", float("-inf")) == float("-inf"):
        raise RuntimeError("입력이 무음입니다 — 정규화할 수 없습니다.")

    with tempfile.TemporaryDirectory() as td:
        wav_tmp = Path(td) / "normalized.wav"
        _loudnorm_to_wav(
            src, wav_tmp, measured=measured,
            target_i=target_i, target_tp=target_tp, target_lra=target_lra,
            channels=channels, sample_rate=sample_rate,
        )
        encoder = _encode_ogg(wav_tmp, dst, channels=channels, vorbis_q=vorbis_q)

    # 결과 자기 검증용 재측정 (인코딩 손실 반영된 실측)
    output = probe_format(dst)
    output.update(measure_loudness(dst, target_i=target_i, target_tp=target_tp,
                                   target_lra=target_lra))
    return {"measured": measured, "encoder": encoder, "output": output}


# ---------------------------------------------------------------------------
# CLI 핸들러
# ---------------------------------------------------------------------------
def _cmd_normalize(args: argparse.Namespace) -> int:
    result = normalize_audio(
        Path(args.input), Path(args.output),
        target_i=args.target_i, target_tp=args.target_tp, target_lra=args.lra,
        channels=args.channels, sample_rate=args.sample_rate, vorbis_q=args.quality,
    )
    out = result["output"]
    if args.json:
        print(json.dumps(result, ensure_ascii=False))
    else:
        print(f"정규화 완료: {args.output} (인코더: {result['encoder']})")
        print(f"  입력 측정: {result['measured']['input_i']:.2f} LUFS "
              f"(TP {result['measured']['input_tp']:.2f} dBTP)")
        print(f"  출력 실측: {out['input_i']:.2f} LUFS (목표 {args.target_i}) · "
              f"{out['codec']} · {out['channels']}ch · {out['sample_rate']}Hz")
    # 자기 검증: 목표 대비 허용오차 밖이면 실패로 알린다 (짧은 SE 는 게이팅 특성상
    # 오차가 커질 수 있어 기본 1.0 LU, --tolerance 로 조정).
    if abs(out["input_i"] - args.target_i) > args.tolerance:
        print(f"경고: 출력 라우드니스 {out['input_i']:.2f} LUFS 가 목표 "
              f"{args.target_i}±{args.tolerance} 를 벗어났습니다.", file=sys.stderr)
        return 1
    return 0


def _cmd_probe(args: argparse.Namespace) -> int:
    src = Path(args.input)
    info = probe_format(src)
    info.update(measure_loudness(src))
    print(json.dumps(info, ensure_ascii=False))

    problems: list[str] = []
    if args.expect_codec and info.get("codec") != args.expect_codec:
        problems.append(f"codec={info.get('codec')} (기대: {args.expect_codec})")
    if args.expect_channels is not None and info.get("channels") != args.expect_channels:
        problems.append(f"channels={info.get('channels')} (기대: {args.expect_channels})")
    if args.expect_i is not None:
        if abs(info["input_i"] - args.expect_i) > args.tolerance:
            problems.append(
                f"integrated={info['input_i']:.2f} LUFS "
                f"(기대: {args.expect_i}±{args.tolerance})"
            )
    if problems:
        print("검증 불통과: " + "; ".join(problems), file=sys.stderr)
        return 1
    return 0


def _cmd_encoders(args: argparse.Namespace) -> int:
    enc = detect_encoders()
    print(json.dumps(enc, ensure_ascii=False))
    return 0 if any(enc.values()) else 1


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="se_post.py",
        description="se 오디오 후처리 (ffmpeg): 2-pass loudnorm → OGG Vorbis · 라우드니스 probe 검증",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pn = sub.add_parser("normalize", help="입력 → OGG Vorbis 라우드니스 정규화 (2-pass)")
    pn.add_argument("--input", required=True)
    pn.add_argument("--output", required=True, help=".ogg 경로 (conventions: assets/audio/se/<이벤트>.ogg)")
    pn.add_argument("--target-i", type=float, default=DEFAULT_TARGET_I,
                    help=f"목표 integrated LUFS (기본 {DEFAULT_TARGET_I}=SE, BGM 은 -14)")
    pn.add_argument("--target-tp", type=float, default=DEFAULT_TARGET_TP,
                    help=f"목표 true peak dBTP (기본 {DEFAULT_TARGET_TP})")
    pn.add_argument("--lra", type=float, default=DEFAULT_TARGET_LRA,
                    help=f"목표 loudness range (기본 {DEFAULT_TARGET_LRA})")
    pn.add_argument("--channels", type=int, default=DEFAULT_CHANNELS,
                    help=f"출력 채널 수 (기본 {DEFAULT_CHANNELS}=SE 모노, BGM 은 2)")
    pn.add_argument("--sample-rate", type=int, default=DEFAULT_SAMPLE_RATE)
    pn.add_argument("--quality", type=float, default=DEFAULT_VORBIS_Q,
                    help=f"Vorbis 품질, libvorbis qscale 기준 0~10 (기본 {DEFAULT_VORBIS_Q})")
    pn.add_argument("--tolerance", type=float, default=1.0,
                    help="출력 실측 허용오차 LU (기본 1.0)")
    pn.add_argument("--json", action="store_true")
    pn.set_defaults(func=_cmd_normalize)

    pp = sub.add_parser("probe", help="포맷 + 라우드니스 JSON 보고 (+--expect-* 검증)")
    pp.add_argument("--input", required=True)
    pp.add_argument("--expect-codec", default=None, help="예: vorbis")
    pp.add_argument("--expect-channels", type=int, default=None)
    pp.add_argument("--expect-i", type=float, default=None, help="기대 integrated LUFS")
    pp.add_argument("--tolerance", type=float, default=1.0, help="LUFS 허용오차 (기본 1.0)")
    pp.set_defaults(func=_cmd_probe)

    pe = sub.add_parser("encoders", help="사용 가능한 Vorbis 인코더 보고 (JSON)")
    pe.set_defaults(func=_cmd_encoders)

    return p


def main(argv: list[str] | None = None) -> int:
    tool_err = _require_tools()
    if tool_err:
        print(f"오류: {tool_err}", file=sys.stderr)
        return 2
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (ValueError, RuntimeError, json.JSONDecodeError,
            subprocess.TimeoutExpired) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
