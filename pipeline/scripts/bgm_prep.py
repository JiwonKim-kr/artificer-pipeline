#!/usr/bin/env python3
"""외부 음원을 루프 재생용으로 다듬는다 (trim + 루프 경계 페이드).

bgm_gen.py 는 베드를 '합성'하고, 이쪽은 이미 있는 음원을 '루프 가능하게' 만든다.
출력은 정규화 전 WAV — 라우드니스·OGG 변환은 se_post.py normalize 가 맡는다.

왜 필요한가
-----------
1) 앞뒤 무음: MP3 인코더 패딩이나 원곡 자체의 여백이 남아 있으면 루프마다 그만큼
   정적이 생긴다. 실측 예: dark-loops 트랙 꼬리에 1869ms 무음 → 147초마다 2초 공백.
2) Vorbis 이음매: OGG 는 MDCT 랩드 변환이라 스트림 마지막 윈도우를 복원하지 못하고
   테이퍼시킨다. 원본 이음매가 완벽해도 구우면 벌어진다(앰비언트 베드에서 실측
   8 → 337). 양 끝을 0 으로 떨어뜨리면 되감을 때 0→0 이라 불연속이 없어진다.

트림 기준은 진폭 임계이지 박자가 아니다. 음악의 마디를 맞추려면 사람이 --head/--tail
로 직접 초를 지정해야 한다.
"""
from __future__ import annotations

import argparse
import array
import shutil
import subprocess
import sys
from pathlib import Path

EDGE_FADE_SEC = 0.008   # bgm_gen.py 와 동일 근거
PROBE_SR = 24000        # 무음 탐지용 디코드 레이트(모노) — 원본을 바꾸지 않는다


def _decode_mono(path: Path, sr: int) -> array.array:
    raw = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", str(path), "-f", "s16le", "-ac", "1", "-ar", str(sr), "-"],
        capture_output=True, check=True).stdout
    a = array.array("h")
    a.frombytes(raw)
    return a


def detect_quiet_edges(path: Path, threshold: int) -> tuple[float, float, float]:
    """(앞 무음 초, 뒤 무음 초, 총 길이 초). threshold 는 16bit 진폭."""
    a = _decode_mono(path, PROBE_SR)
    n = len(a)
    if n == 0:
        return 0.0, 0.0, 0.0
    lead = next((i for i, v in enumerate(a) if abs(v) > threshold), n)
    trail = next((i for i, v in enumerate(reversed(a)) if abs(v) > threshold), n)
    return lead / PROBE_SR, trail / PROBE_SR, n / PROBE_SR


def main() -> int:
    ap = argparse.ArgumentParser(description=__doc__.split("\n")[0])
    ap.add_argument("--input", required=True)
    ap.add_argument("--output", required=True, help="출력 WAV (정규화 전)")
    ap.add_argument("--threshold", type=int, default=100,
                    help="무음 판정 진폭(16bit, 기본 100 ≈ -50dBFS)")
    ap.add_argument("--head", type=float, default=None, help="앞을 이만큼 초 잘라낸다(자동 탐지 대신)")
    ap.add_argument("--tail", type=float, default=None, help="뒤를 이만큼 초 잘라낸다(자동 탐지 대신)")
    ap.add_argument("--edge-fade", type=float, default=EDGE_FADE_SEC)
    ap.add_argument("--sample-rate", type=int, default=None, help="리샘플(기본: 원본 유지)")
    args = ap.parse_args()

    if shutil.which("ffmpeg") is None:
        print("[bgm_prep] ffmpeg 없음", file=sys.stderr)
        return 2
    src = Path(args.input)
    if not src.exists():
        print(f"[bgm_prep] 입력 없음: {src}", file=sys.stderr)
        return 2

    lead, trail, total = detect_quiet_edges(src, args.threshold)
    head = args.head if args.head is not None else lead
    tail = args.tail if args.tail is not None else trail
    kept = total - head - tail
    if kept <= args.edge_fade * 2:
        print(f"[bgm_prep] 트림 후 남는 길이가 너무 짧다: {kept:.3f}s", file=sys.stderr)
        return 2

    print(f"원본 {total:.3f}s · 무음 앞 {lead * 1000:.1f}ms / 뒤 {trail * 1000:.1f}ms")
    print(f"트림 앞 {head * 1000:.1f}ms / 뒤 {tail * 1000:.1f}ms → 루프 {kept:.3f}s")

    fade = args.edge_fade
    af = (f"atrim=start={head:.6f}:end={total - tail:.6f},asetpts=PTS-STARTPTS,"
          f"afade=t=in:st=0:d={fade}:curve=hsin,"
          f"afade=t=out:st={kept - fade:.6f}:d={fade}:curve=hsin")
    cmd = ["ffmpeg", "-hide_banner", "-loglevel", "error", "-y", "-i", str(src), "-af", af]
    if args.sample_rate:
        cmd += ["-ar", str(args.sample_rate)]
    out = Path(args.output)
    out.parent.mkdir(parents=True, exist_ok=True)
    cmd += ["-c:a", "pcm_s16le", str(out)]
    subprocess.run(cmd, check=True)
    print(f"생성됨: {out} (루프 경계 {fade * 1000:.0f}ms 페이드)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
