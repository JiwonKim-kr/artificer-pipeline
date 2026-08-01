#!/usr/bin/env python3
"""art 로컬 후처리 (ffmpeg 8.x). Scenario 플랫폼 후처리로 부족한 부분만 보완한다.

`art gen` 은 플랫폼 내장 후처리(배경 제거·투명 PNG)를 **우선** 활용하고, 픽셀아트
정합에 필요한 로컬 처리만 이 스크립트로 수행한다. (HANDOFF §4 Phase 3, §6-1)

서브커맨드:
  resize   픽셀아트용 **nearest-neighbor** 리사이즈 (블러 없이 격자 보존). 투명 유지.
  pack     동일 크기 프레임들을 스프라이트시트로 패킹 (ffmpeg **tile** 필터). 투명 유지.
  probe    이미지의 width/height/pix_fmt/투명(alpha) 여부를 JSON 으로 보고.

장르/스타일을 하드코딩하지 않는다 — 크기·프레임 수는 전부 인자(데이터)로 받는다.
(픽셀아트라는 사실은 정책 문서·매니페스트 데이터로만 표현한다. CLAUDE.md/HANDOFF §6-3)

종료 코드: 0 = 성공, 1 = 처리 실패(ffmpeg 오류 등), 2 = 실행/인자 오류.
stdlib 만 사용 (외부 패키지 없음). ffmpeg/ffprobe 는 PATH 또는 FFMPEG_BIN/FFPROBE_BIN.
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

# alpha 채널을 갖는 대표 pix_fmt (완전하진 않으나 PNG/스프라이트 용도에 충분).
_ALPHA_PIX_FMTS = {
    "rgba", "bgra", "argb", "abgr",
    "rgba64be", "rgba64le", "bgra64be", "bgra64le",
    "ya8", "ya16be", "ya16le",
    "yuva420p", "yuva422p", "yuva444p",
    "yuva420p10le", "yuva444p10le",
    "pal8",  # 팔레트는 tRNS 로 투명을 가질 수 있음
}


def _ffmpeg() -> str:
    return os.environ.get("FFMPEG_BIN", "ffmpeg")


def _ffprobe() -> str:
    return os.environ.get("FFPROBE_BIN", "ffprobe")


def _require_tools() -> str | None:
    for tool, name in ((_ffmpeg(), "ffmpeg"), (_ffprobe(), "ffprobe")):
        if shutil.which(tool) is None and not Path(tool).exists():
            return f"{name} 실행 파일을 찾을 수 없습니다 ({tool!r}). 설치하거나 FFMPEG_BIN/FFPROBE_BIN 지정."
    return None


# ---------------------------------------------------------------------------
# probe
# ---------------------------------------------------------------------------
def probe_image(path: Path) -> dict:
    """이미지의 width/height/pix_fmt/has_alpha 를 반환. ffprobe 사용."""
    proc = subprocess.run(
        [
            _ffprobe(), "-v", "error", "-select_streams", "v:0",
            "-show_entries", "stream=width,height,pix_fmt",
            "-of", "json", str(path),
        ],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffprobe 실패: {proc.stderr.strip()}")
    streams = json.loads(proc.stdout).get("streams", [])
    if not streams:
        raise RuntimeError(f"영상 스트림 없음: {path}")
    s = streams[0]
    pix_fmt = s.get("pix_fmt", "")
    return {
        "width": s.get("width"),
        "height": s.get("height"),
        "pix_fmt": pix_fmt,
        "has_alpha": pix_fmt in _ALPHA_PIX_FMTS or pix_fmt.startswith(("rgba", "bgra", "ya")),
    }


# ---------------------------------------------------------------------------
# resize (nearest-neighbor)
# ---------------------------------------------------------------------------
# ffmpeg scale flags 중 허용 값. neighbor=픽셀아트(격자 보존),
# lanczos/bicubic=회화체·사진체(축소 시 계단현상 방지).
RESIZE_FILTERS = ("neighbor", "lanczos", "bicubic", "bilinear", "spline")


def resize_image(
    src: Path, dst: Path, *, width: int | None, height: int | None, scale: float | None,
    filter_name: str = "neighbor",
) -> None:
    """리사이즈. width/height 직접 지정 또는 scale 배수. 투명(alpha)을 보존한다.

    보간 필터는 **인자(데이터)로 받는다** — 픽셀아트는 neighbor, 회화체 아트는
    lanczos 처럼 아트 스타일에 맞춰 고른다(스타일 하드코딩 금지 원칙).
    """
    if filter_name not in RESIZE_FILTERS:
        raise ValueError(f"지원하지 않는 필터: {filter_name} (허용: {', '.join(RESIZE_FILTERS)})")
    if scale is not None:
        info = probe_image(src)
        width = max(1, round(int(info["width"]) * scale))
        height = max(1, round(int(info["height"]) * scale))
    if not width or not height:
        raise ValueError("resize 에는 --width/--height 또는 --scale 이 필요합니다.")
    dst.parent.mkdir(parents=True, exist_ok=True)
    # format=rgba + -pix_fmt rgba: 알파 보존.
    vf = f"scale={width}:{height}:flags={filter_name},format=rgba"
    proc = subprocess.run(
        [_ffmpeg(), "-y", "-i", str(src), "-vf", vf, "-pix_fmt", "rgba", str(dst)],
        capture_output=True, text=True,
    )
    if proc.returncode != 0:
        raise RuntimeError(f"ffmpeg resize 실패: {proc.stderr.strip()[-800:]}")


# ---------------------------------------------------------------------------
# pack (spritesheet, tile 필터)
# ---------------------------------------------------------------------------
def pack_sheet(
    frames: list[Path], dst: Path, *, cols: int | None, rows: int | None
) -> dict:
    """동일 크기 프레임들을 하나의 스프라이트시트로 tile 패킹. 투명 보존.

    반환: {frame_width, frame_height, cols, rows, count, sheet_width, sheet_height}
    (매니페스트 params 에 프레임 정보로 기록하기 위함 — conventions.md 이미지 규격.)
    """
    if not frames:
        raise ValueError("pack 에 최소 1개 프레임이 필요합니다.")
    missing = [str(p) for p in frames if not p.exists()]
    if missing:
        raise ValueError("프레임 파일 없음: " + ", ".join(missing))

    # 모든 프레임이 동일 크기인지 검증 (스프라이트시트 전제: conventions.md).
    sizes = {(int(i["width"]), int(i["height"])) for i in (probe_image(p) for p in frames)}
    if len(sizes) != 1:
        raise ValueError(f"프레임 크기가 제각각입니다: {sorted(sizes)} (동일 크기만 패킹 가능)")
    fw, fh = next(iter(sizes))

    n = len(frames)
    if cols is None and rows is None:
        cols, rows = n, 1                       # 기본: 가로 스트립
    elif cols is None:
        cols = -(-n // rows)                     # ceil
    elif rows is None:
        rows = -(-n // cols)
    if cols * rows < n:
        raise ValueError(f"cols*rows({cols*rows}) < 프레임 수({n})")

    dst.parent.mkdir(parents=True, exist_ok=True)
    with tempfile.TemporaryDirectory() as td:
        # tile 필터는 단일 입력 스트림의 연속 프레임을 모은다 → 번호 시퀀스로 스테이징.
        for i, p in enumerate(frames):
            shutil.copy(p, Path(td) / f"f{i:04d}.png")
        seq = str(Path(td) / "f%04d.png")
        # color=0x00000000: 남는 셀을 투명으로. format=rgba + -pix_fmt rgba: 알파 보존.
        vf = f"format=rgba,tile={cols}x{rows}:color=0x00000000"
        proc = subprocess.run(
            [
                _ffmpeg(), "-y", "-framerate", "1", "-start_number", "0",
                "-i", seq, "-frames:v", "1", "-update", "1",
                "-vf", vf, "-pix_fmt", "rgba", str(dst),
            ],
            capture_output=True, text=True,
        )
        if proc.returncode != 0:
            raise RuntimeError(f"ffmpeg pack(tile) 실패: {proc.stderr.strip()[-800:]}")

    return {
        "frame_width": fw, "frame_height": fh,
        "cols": cols, "rows": rows, "count": n,
        "sheet_width": fw * cols, "sheet_height": fh * rows,
    }


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _cmd_probe(args: argparse.Namespace) -> int:
    info = probe_image(Path(args.input))
    print(json.dumps(info, ensure_ascii=False))
    return 0


def _cmd_resize(args: argparse.Namespace) -> int:
    resize_image(
        Path(args.input), Path(args.output),
        width=args.width, height=args.height, scale=args.scale,
        filter_name=args.filter,
    )
    info = probe_image(Path(args.output))
    print(f"리사이즈 완료: {args.output} ({info['width']}x{info['height']}, "
          f"pix_fmt={info['pix_fmt']}, alpha={'예' if info['has_alpha'] else '아니오'})")
    return 0


def _cmd_pack(args: argparse.Namespace) -> int:
    meta = pack_sheet(
        [Path(p) for p in args.frames], Path(args.output),
        cols=args.cols, rows=args.rows,
    )
    if args.json:
        print(json.dumps(meta, ensure_ascii=False))
    else:
        print(f"패킹 완료: {args.output} — {meta['count']}프레임 "
              f"{meta['frame_width']}x{meta['frame_height']} → "
              f"{meta['cols']}x{meta['rows']} 시트 "
              f"({meta['sheet_width']}x{meta['sheet_height']})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="art_post.py",
        description="art 로컬 후처리 (ffmpeg): 픽셀아트 nearest 리사이즈 · 스프라이트시트 패킹 · 투명 검사",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pp = sub.add_parser("probe", help="width/height/pix_fmt/has_alpha JSON 보고")
    pp.add_argument("--input", required=True)
    pp.set_defaults(func=_cmd_probe)

    pr = sub.add_parser("resize", help="리사이즈 (투명 유지, 보간 필터 선택)")
    pr.add_argument("--input", required=True)
    pr.add_argument("--output", required=True)
    pr.add_argument("--width", type=int, default=None)
    pr.add_argument("--height", type=int, default=None)
    pr.add_argument("--scale", type=float, default=None, help="배수 (예: 2.0). width/height 대신 사용.")
    pr.add_argument("--filter", default="neighbor", choices=RESIZE_FILTERS,
                    help="보간 필터. 픽셀아트=neighbor(기본), 회화체=lanczos 권장.")
    pr.set_defaults(func=_cmd_resize)

    pk = sub.add_parser("pack", help="동일 크기 프레임 → 스프라이트시트 (tile 필터)")
    pk.add_argument("--output", required=True)
    pk.add_argument("--cols", type=int, default=None)
    pk.add_argument("--rows", type=int, default=None)
    pk.add_argument("--json", action="store_true", help="프레임 메타를 JSON 으로 출력")
    pk.add_argument("frames", nargs="+", help="프레임 PNG 경로들 (순서대로)")
    pk.set_defaults(func=_cmd_pack)

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
    except (ValueError, RuntimeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1
    except (FileNotFoundError, OSError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
