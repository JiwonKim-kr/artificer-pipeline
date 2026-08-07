#!/usr/bin/env python3
"""bgm gen — 앰비언트 베드 절차 합성 (ffmpeg).

카탈로그상 `bgm gen` 은 "최소 기능만 유지" 계약이다. 여기서 구현하는 최소 기능은
**루프 가능한 앰비언트 베드 합성** 하나뿐 — 멜로디·편곡은 범위 밖이다.

설계 근거
---------
1) 절차 합성을 쓰는 이유: SE 와 동일한 라이선스 청정성(외부 음원·API 무사용),
   0 비용, 결정적 재현. 기존 SE 는 jsfxr 절차생성이라 기재도 일관된다.
2) 심리스 루프: 모든 사인 성분의 주파수를 `1/LOOP_SEC` 의 정수배로 잡아 루프
   지점에서 위상이 연속되게 한다(50Hz × 30s = 정확히 1500주기). 위상이 없는
   노이즈 층은 꼬리 구간을 머리에 크로스페이드해 이음매를 지운다.
3) 스테레오 폭: 사인은 중앙 고정(위상 연속 유지), 노이즈만 좌우 시드를 달리해
   비상관화한다. 디튠으로 폭을 만들면 루프 주기 정수배가 깨진다.

출력은 정규화 전 WAV. 라우드니스·OGG 변환은 se_post.py normalize 가 맡는다
(단일 창구 유지).
"""
from __future__ import annotations

import argparse
import shutil
import subprocess
import sys
from pathlib import Path

LOOP_SEC = 30.0
XFADE_SEC = 3.0  # 노이즈 이음매를 지우는 꼬리 크로스페이드 길이
SAMPLE_RATE = 44100
# Vorbis 는 MDCT 랩드 변환이라 스트림 마지막 윈도우를 복원하지 못하고 테이퍼시킨다.
# 그래서 WAV 단계에서 이음매가 완벽해도(실측 점프 8) OGG 로 굽고 나면 벌어진다(337).
# 양 끝을 0 으로 떨어뜨리면 되감을 때 0→0 이라 불연속이 아예 없어진다. 대가는 루프당
# 이만큼의 진폭 딥인데, 8ms 는 드론 베드에서 클릭보다 훨씬 덜 거슬린다.
EDGE_FADE_SEC = 0.008


def _check_harmonic(freq: float, name: str) -> None:
    """루프 길이 안에서 정수 주기인지 검사 — 아니면 이음매에서 '툭' 소리가 난다."""
    cycles = freq * LOOP_SEC
    if abs(cycles - round(cycles)) > 1e-6:
        raise SystemExit(
            f"[bgm_gen] {name} {freq}Hz 는 {LOOP_SEC}s 루프에서 정수 주기가 아님 "
            f"({cycles} 주기). 루프 이음매가 들린다."
        )


# 베드 정의: (주파수, 게인) 목록. 게인은 정규화 전 상대 비율일 뿐 절대값이 아니다.
BEDS: dict[str, dict] = {
    "room": {
        "desc": "밤의 편집국 — 전력망 험 + 방 공기. 타이틀·데스크용.",
        "tones": [(50.0, 0.30), (100.0, 0.12), (150.0, 0.05)],
        "noise_gain": 0.10,
        "noise_lowpass": 400,
        "tremolo_hz": 0.1,   # 램프 흔들림. 30s 에 3주기 → 루프 연속
        "tremolo_depth": 0.25,
    },
    "crt": {
        "desc": "브라운관 앞 — room + 편향코일 험 + 형광등 버즈. 화면 상태용.",
        "tones": [
            (50.0, 0.26), (100.0, 0.14), (150.0, 0.05),
            (120.0, 0.18), (240.0, 0.08),   # 편향코일
            (300.0, 0.04), (500.0, 0.02),   # 형광등 버즈 배음
        ],
        "noise_gain": 0.09,
        "noise_lowpass": 600,
        "tremolo_hz": 0.2,
        "tremolo_depth": 0.18,
    },
}


def build_filter(bed: dict, seed_l: int, seed_r: int) -> tuple[str, str]:
    """filter_complex 문자열과 최종 출력 라벨을 만든다."""
    gen_sec = LOOP_SEC + XFADE_SEC  # 꼬리 크로스페이드용 여분
    parts: list[str] = []
    mix_in: list[str] = []

    for i, (freq, gain) in enumerate(bed["tones"]):
        _check_harmonic(freq, "tone")
        lbl = f"t{i}"
        parts.append(
            f"sine=frequency={freq}:sample_rate={SAMPLE_RATE}:duration={gen_sec},"
            f"volume={gain}[{lbl}]"
        )
        mix_in.append(f"[{lbl}]")

    # 사인 합 → 중앙 정위. amix 는 입력 수로 나누므로 볼륨을 되살린다.
    n = len(mix_in)
    parts.append(
        f"{''.join(mix_in)}amix=inputs={n}:normalize=0[tones]"
    )

    # 노이즈 2채널(좌우 비상관) — 방 공기.
    for side, seed in (("l", seed_l), ("r", seed_r)):
        parts.append(
            f"anoisesrc=color=pink:sample_rate={SAMPLE_RATE}:duration={gen_sec}:seed={seed},"
            f"lowpass=f={bed['noise_lowpass']},volume={bed['noise_gain']}[n{side}]"
        )

    # 좌/우 = 사인(공통) + 각 채널 노이즈
    parts.append("[tones]asplit=2[tl][tr]")
    parts.append("[tl][nl]amix=inputs=2:normalize=0[ml]")
    parts.append("[tr][nr]amix=inputs=2:normalize=0[mr]")
    parts.append("[ml][mr]join=inputs=2:channel_layout=stereo[st]")

    # 아주 느린 진폭 흔들림(램프/화면 명멸).
    _check_harmonic(bed["tremolo_hz"], "tremolo")
    parts.append(
        f"[st]tremolo=f={bed['tremolo_hz']}:d={bed['tremolo_depth']}[trem]"
    )

    # 루프 이음매 제거: [LOOP, LOOP+XFADE] 꼬리를 [0, XFADE] 머리에 겹쳐 섞는다.
    # 사인은 위상이 이미 연속이라 이 연산으로 값이 변하지 않고, 노이즈만 매끄러워진다.
    parts.append("[trem]asplit=3[a][b][c]")
    parts.append(f"[a]atrim=0:{XFADE_SEC},asetpts=PTS-STARTPTS,afade=t=in:st=0:d={XFADE_SEC}[head]")
    parts.append(
        f"[b]atrim={LOOP_SEC}:{LOOP_SEC + XFADE_SEC},asetpts=PTS-STARTPTS,"
        f"afade=t=out:st=0:d={XFADE_SEC}[tail]"
    )
    parts.append("[head][tail]amix=inputs=2:normalize=0[seam]")
    parts.append(
        f"[c]atrim={XFADE_SEC}:{LOOP_SEC},asetpts=PTS-STARTPTS[body]"
    )
    parts.append("[seam][body]concat=n=2:v=0:a=1[joined]")

    # 루프 경계를 0 으로 — 위 EDGE_FADE_SEC 주석 참조.
    parts.append(
        f"[joined]afade=t=in:st=0:d={EDGE_FADE_SEC}:curve=hsin,"
        f"afade=t=out:st={LOOP_SEC - EDGE_FADE_SEC}:d={EDGE_FADE_SEC}:curve=hsin[out]"
    )

    return ";".join(parts), "[out]"


def generate(name: str, out_path: Path, seed_l: int, seed_r: int) -> None:
    bed = BEDS[name]
    fc, out_lbl = build_filter(bed, seed_l, seed_r)
    cmd = [
        "ffmpeg", "-hide_banner", "-loglevel", "error", "-y",
        "-filter_complex", fc,
        "-map", out_lbl,
        "-c:a", "pcm_s16le", "-ar", str(SAMPLE_RATE),
        str(out_path),
    ]
    subprocess.run(cmd, check=True)


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--bed", choices=sorted(BEDS), required=True)
    ap.add_argument("--output", required=True, help="출력 WAV 경로 (정규화 전)")
    ap.add_argument("--seed-l", type=int, default=101)
    ap.add_argument("--seed-r", type=int, default=202)
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        print("[bgm_gen] ffmpeg 없음", file=sys.stderr)
        return 2

    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    generate(args.bed, out, args.seed_l, args.seed_r)
    print(f"생성됨: {out} ({BEDS[args.bed]['desc']}) · 루프 {LOOP_SEC}s")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
