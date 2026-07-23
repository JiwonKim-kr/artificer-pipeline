#!/usr/bin/env python3
"""placeholder_gen — 로컬 플레이스홀더 스프라이트/타일 PNG 생성기 (무료·오프라인).

`play build` 가 배치하는 `PLACEHOLDER_` 에셋을 **읽히는 그림**으로 만든다. 단색
네모 대신 글리프(문자)와 색·테두리를 넣어, 실제 아트 없이도 "게임이 뭘 하는지"를
화면에서 눈으로 판정할 수 있게 하는 것이 목적이다.

이것은 임시방편이 아니라 **정식 중간 산출물**이다. 산출물은 기존 파이프라인과
100% 호환된다:
  · 파일명은 호출자가 `PLACEHOLDER_` 접두사 규약(docs/conventions.md)으로 준다.
  · 매니페스트 등록은 이 스크립트가 하지 않는다 — 쓰기 창구는 `manifest.py` 뿐이다
    (CLAUDE.md 원칙 3). 이 스크립트는 **이미지 파일만** 만든다.
  · 출력은 RGBA PNG + Sprite2D 텍스처로 그대로 쓰이므로, 예산이 생기면
    `art reskin` 이 동일 경로/동일 구조의 실제 에셋으로 교체한다(재작업 0).

art_post.py 와의 역할 분담:
  · placeholder_gen.py — **없는 이미지를 만든다**(stdlib zlib/struct 로 PNG 직접 기록).
  · art_post.py        — **있는 이미지를 가공/검사한다**(ffmpeg resize/pack/probe).
  둘은 겹치지 않는다. 생성물 확대·시트 패킹·규격 검사는 art_post 를 그대로 쓴다.

결정성: 동일 인자 → 동일 바이트 PNG. 난수·시각·환경 의존 값을 쓰지 않는다
(zlib 압축 레벨 고정, PNG 는 IHDR/IDAT/IEND 만 기록 — tIME 등 가변 청크 없음).
※ 픽셀 데이터는 어떤 환경에서든 동일하다. 압축 바이트열은 zlib 구현이 같으면
  동일하다(동일 머신/CI 이미지 내 재현성 보장). zlib 구현이 다른 머신 사이에서는
  압축 결과가 달라질 수 있으므로, 재생성 산출물을 커밋할 때는 픽셀 동일성을
  기준으로 판단한다.

장르 하드코딩 없음: 글리프·색·크기는 전부 인자(데이터)로 받는다. 어떤 글리프가
플레이어/적/바닥인지는 spec·lore 데이터를 보고 **호출자(Claude)** 가 정한다.

CLI 예:
  # 스프라이트(배경 투명): 노란 '@'
  python3 pipeline/scripts/placeholder_gen.py --glyph '@' --fg '#ffd23f' \
      --output assets/art/sprites/player/PLACEHOLDER_player_idle.png
  # 타일(불투명 배경 + 테두리): 회색 '.'
  python3 pipeline/scripts/placeholder_gen.py --glyph '.' --fg '#6b705c' \
      --bg '#2b2d24' --border '#3f4334' \
      --output assets/art/sprites/tiles/PLACEHOLDER_floor.png
  # 글리프 없이 도형만 (단색 + 테두리)
  python3 pipeline/scripts/placeholder_gen.py --bg '#404040' --border '#808080' \
      --output /tmp/box.png

  ※ zsh/bash 에서 `#RRGGBB` 는 반드시 따옴표로 감싼다(`#` 는 주석 시작). 편의를 위해
    `--fg ffd23f` 처럼 `#` 없는 형태도 허용한다.

종료 코드: 0 = 성공, 1 = 처리 실패(쓰기 오류 등), 2 = 실행/인자 오류.
stdlib 만 사용 (Python 3.14). 외부 패키지·ffmpeg 불필요.
"""
from __future__ import annotations

import argparse
import json
import struct
import sys
import zlib
from pathlib import Path

# ---------------------------------------------------------------------------
# 내장 비트맵 폰트 (5x7)
# ---------------------------------------------------------------------------
# '#' = 켜짐, '.' = 꺼짐. 행 구분자는 '/'. 각 글리프는 정확히 7행 x 5열이어야 한다
# (모듈 로드 시 _build_font 가 검사한다 — 오타는 즉시 ValueError).
#
# 5x7 을 고른 이유: 16x16 타일에서 정수 2배 스케일 시 10x14 가 되어 여백 1~3px 를
# 남기고 꽉 찬다. 3x5 는 작아서 판독성이 떨어지고, 8x8 은 16x16 에서 1배(작음) 또는
# 2배(16x16 초과)밖에 안 돼 중앙 배치가 어렵다.
FONT_WIDTH = 5
FONT_HEIGHT = 7
FALLBACK_GLYPH = "?"

_FONT_SRC: dict[str, str] = {
    " ": "...../...../...../...../...../...../.....",
    # --- 숫자 ---
    "0": ".###./#...#/#..##/#.#.#/##..#/#...#/.###.",
    "1": "..#../.##../..#../..#../..#../..#../.###.",
    "2": ".###./#...#/....#/...#./..#../.#.../#####",
    "3": "#####/...#./..#../...#./....#/#...#/.###.",
    "4": "...#./..##./.#.#./#..#./#####/...#./...#.",
    "5": "#####/#..../####./....#/....#/#...#/.###.",
    "6": "..##./.#.../#..../####./#...#/#...#/.###.",
    "7": "#####/....#/...#./..#../.#.../.#.../.#...",
    "8": ".###./#...#/#...#/.###./#...#/#...#/.###.",
    "9": ".###./#...#/#...#/.####/....#/...#./.##..",
    # --- 대문자 ---
    "A": "..#../.#.#./#...#/#...#/#####/#...#/#...#",
    "B": "####./#...#/#...#/####./#...#/#...#/####.",
    "C": ".###./#...#/#..../#..../#..../#...#/.###.",
    "D": "###../#..#./#...#/#...#/#...#/#..#./###..",
    "E": "#####/#..../#..../####./#..../#..../#####",
    "F": "#####/#..../#..../####./#..../#..../#....",
    "G": ".###./#...#/#..../#.###/#...#/#...#/.###.",
    "H": "#...#/#...#/#...#/#####/#...#/#...#/#...#",
    "I": ".###./..#../..#../..#../..#../..#../.###.",
    "J": "..###/...#./...#./...#./...#./#..#./.##..",
    "K": "#...#/#..#./#.#../##.../#.#../#..#./#...#",
    "L": "#..../#..../#..../#..../#..../#..../#####",
    "M": "#...#/##.##/#.#.#/#.#.#/#...#/#...#/#...#",
    "N": "#...#/##..#/#.#.#/#..##/#...#/#...#/#...#",
    "O": ".###./#...#/#...#/#...#/#...#/#...#/.###.",
    "P": "####./#...#/#...#/####./#..../#..../#....",
    "Q": ".###./#...#/#...#/#...#/#.#.#/#..#./.##.#",
    "R": "####./#...#/#...#/####./#.#../#..#./#...#",
    "S": ".####/#..../#..../.###./....#/....#/####.",
    "T": "#####/..#../..#../..#../..#../..#../..#..",
    "U": "#...#/#...#/#...#/#...#/#...#/#...#/.###.",
    "V": "#...#/#...#/#...#/#...#/#...#/.#.#./..#..",
    "W": "#...#/#...#/#...#/#.#.#/#.#.#/##.##/#...#",
    "X": "#...#/#...#/.#.#./..#../.#.#./#...#/#...#",
    "Y": "#...#/#...#/.#.#./..#../..#../..#../..#..",
    "Z": "#####/....#/...#./..#../.#.../#..../#####",
    # --- 소문자 (x-height 5, 하단 2행은 디센더용) ---
    "a": "...../...../.###./....#/.####/#...#/.####",
    "b": "#..../#..../####./#...#/#...#/#...#/####.",
    "c": "...../...../.###./#..../#..../#..../.###.",
    "d": "....#/....#/.####/#...#/#...#/#...#/.####",
    "e": "...../...../.###./#...#/#####/#..../.###.",
    "f": "..##./.#..#/.#.../###../.#.../.#.../.#...",
    "g": "...../.####/#...#/#...#/.####/....#/.###.",
    "h": "#..../#..../####./#...#/#...#/#...#/#...#",
    "i": "..#../...../.##../..#../..#../..#../.###.",
    "j": "...#./...../..##./...#./...#./#..#./.##..",
    "k": "#..../#..../#..#./#.#../##.../#.#../#..#.",
    "l": ".##../..#../..#../..#../..#../..#../.###.",
    "m": "...../...../##.##/#.#.#/#.#.#/#.#.#/#.#.#",
    "n": "...../...../####./#...#/#...#/#...#/#...#",
    "o": "...../...../.###./#...#/#...#/#...#/.###.",
    "p": "...../####./#...#/#...#/####./#..../#....",
    "q": "...../.####/#...#/#...#/.####/....#/....#",
    "r": "...../...../#.##./##.../#..../#..../#....",
    "s": "...../...../.####/#..../.###./....#/####.",
    "t": ".#.../.#.../###../.#.../.#.../.#..#/..##.",
    "u": "...../...../#...#/#...#/#...#/#..##/.##.#",
    "v": "...../...../#...#/#...#/#...#/.#.#./..#..",
    "w": "...../...../#...#/#...#/#.#.#/#.#.#/.#.#.",
    "x": "...../...../#...#/.#.#./..#../.#.#./#...#",
    "y": "...../#...#/#...#/#...#/.####/....#/.###.",
    "z": "...../...../#####/...#./..#../.#.../#####",
    # --- 기호 ---
    "@": ".###./#...#/#.###/#.#.#/#.###/#..../.###.",
    "#": ".#.#./.#.#./#####/.#.#./#####/.#.#./.#.#.",
    "%": "##..#/##..#/...#./..#../.#.../#..##/#..##",
    "!": "..#../..#../..#../..#../..#../...../..#..",
    "?": ".###./#...#/....#/..##./..#../...../..#..",
    "$": "..#../.####/#.#../.###./..#.#/####./..#..",
    "&": ".##../#..#./#..#./.##../#.#.#/#..#./.##.#",
    "*": "...../#.#.#/.###./#####/.###./#.#.#/.....",
    "+": "...../..#../..#../#####/..#../..#../.....",
    "-": "...../...../...../#####/...../...../.....",
    ".": "...../...../...../...../...../.##../.##..",
    ",": "...../...../...../...../.##../.##../.#...",
    "/": "....#/....#/...#./..#../.#.../#..../#....",
    "\\": "#..../#..../.#.../..#../...#./....#/....#",
    "<": "...#./..#../.#.../#..../.#.../..#../...#.",
    ">": ".#.../..#../...#./....#/...#./..#../.#...",
    "(": "..##./.#.../.#.../.#.../.#.../.#.../..##.",
    ")": ".##../...#./...#./...#./...#./...#./.##..",
    "[": ".###./.#.../.#.../.#.../.#.../.#.../.###.",
    "]": ".###./...#./...#./...#./...#./...#./.###.",
    "{": "..##./.#.../.#.../##.../.#.../.#.../..##.",
    "}": ".##../...#./...#./...##/...#./...#./.##..",
    "=": "...../...../#####/...../#####/...../.....",
    "~": "...../...../.#.../#.#.#/...#./...../.....",
    "^": "..#../.#.#./#...#/...../...../...../.....",
    "_": "...../...../...../...../...../...../#####",
    "|": "..#../..#../..#../..#../..#../..#../..#..",
    ":": "...../.##../.##../...../.##../.##../.....",
    ";": "...../.##../.##../...../.##../.##../.#...",
    '"': ".#.#./.#.#./...../...../...../...../.....",
    "'": "..#../..#../...../...../...../...../.....",
    "`": ".#.../..#../...../...../...../...../.....",
}


def _build_font() -> dict[str, tuple[tuple[bool, ...], ...]]:
    """폰트 소스를 검증하며 불리언 격자로 변환한다. 형식 위반은 즉시 ValueError."""
    font: dict[str, tuple[tuple[bool, ...], ...]] = {}
    for ch, src in _FONT_SRC.items():
        rows = src.split("/")
        if len(rows) != FONT_HEIGHT:
            raise ValueError(f"폰트 글리프 {ch!r}: {FONT_HEIGHT}행이어야 하는데 {len(rows)}행")
        grid: list[tuple[bool, ...]] = []
        for r, row in enumerate(rows):
            if len(row) != FONT_WIDTH:
                raise ValueError(
                    f"폰트 글리프 {ch!r} 행 {r}: {FONT_WIDTH}열이어야 하는데 {len(row)}열 ({row!r})"
                )
            bad = set(row) - {"#", "."}
            if bad:
                raise ValueError(f"폰트 글리프 {ch!r} 행 {r}: 허용되지 않는 문자 {sorted(bad)}")
            grid.append(tuple(c == "#" for c in row))
        font[ch] = tuple(grid)
    return font


FONT: dict[str, tuple[tuple[bool, ...], ...]] = _build_font()

RGBA = tuple[int, int, int, int]
TRANSPARENT: RGBA = (0, 0, 0, 0)


def supported_glyphs() -> str:
    """지원 문자 전체를 정렬된 문자열로 반환(공백 포함)."""
    return "".join(sorted(FONT))


# ---------------------------------------------------------------------------
# 색 파싱
# ---------------------------------------------------------------------------
def parse_color(text: str) -> RGBA:
    """`#RRGGBB` / `#RRGGBBAA` / `transparent` → (r, g, b, a).

    셸에서 `#` 이 주석으로 먹히는 사고를 줄이기 위해 `#` 없는 형태도 허용한다.
    """
    s = (text or "").strip()
    if s.lower() in ("transparent", "none"):
        return TRANSPARENT
    body = s[1:] if s.startswith("#") else s
    if len(body) not in (6, 8) or any(c not in "0123456789abcdefABCDEF" for c in body):
        raise ValueError(
            f"색 형식 오류: {text!r} — '#RRGGBB' 또는 '#RRGGBBAA' 또는 'transparent' 만 허용"
        )
    r = int(body[0:2], 16)
    g = int(body[2:4], 16)
    b = int(body[4:6], 16)
    a = int(body[6:8], 16) if len(body) == 8 else 255
    return (r, g, b, a)


def _over(src: RGBA, dst: RGBA) -> RGBA:
    """src-over 알파 합성 (straight alpha, 정수 연산 → 결정적)."""
    sa = src[3]
    if sa == 255 or dst[3] == 0:
        return src
    if sa == 0:
        return dst
    da = dst[3]
    ia = 255 - sa
    out_a = sa + (da * ia + 127) // 255
    if out_a == 0:
        return TRANSPARENT
    out: list[int] = []
    denom = out_a * 255
    for i in range(3):
        num = src[i] * sa * 255 + dst[i] * da * ia
        out.append(min(255, (num + denom // 2) // denom))
    return (out[0], out[1], out[2], out_a)


# ---------------------------------------------------------------------------
# 렌더링
# ---------------------------------------------------------------------------
def resolve_glyph(glyph: str | None) -> tuple[str | None, bool]:
    """(사용할 글리프, 폴백 여부). 미지원 문자는 FALLBACK_GLYPH 로 대체한다."""
    if glyph is None:
        return None, False
    if glyph in FONT:
        return glyph, False
    return FALLBACK_GLYPH, True


def compute_scale(width: int, height: int, inset: int) -> int:
    """테두리 안쪽 영역에 5x7 폰트가 들어가는 최대 정수 배수(최소 1)."""
    avail_w = max(0, width - 2 * inset)
    avail_h = max(0, height - 2 * inset)
    return max(1, min(avail_w // FONT_WIDTH, avail_h // FONT_HEIGHT))


def render_grid(
    *,
    width: int,
    height: int,
    glyph: str | None = None,
    fg: RGBA = (255, 255, 255, 255),
    bg: RGBA = TRANSPARENT,
    border: RGBA | None = None,
    border_width: int = 1,
    scale: int | None = None,
) -> tuple[list[list[RGBA]], dict]:
    """플레이스홀더 픽셀 격자를 만든다. (grid, meta) 반환.

    · 배경(bg) 채움 → 테두리(border) → 글리프(fg, 정수 배수 nearest 스케일 중앙 배치)
    · bg 가 투명이면 스프라이트용(알파 0), 불투명이면 타일용이 된다.
    · 글리프는 알파 합성(src-over)되므로 반투명 fg 도 정확히 표현된다.
    """
    if width <= 0 or height <= 0:
        raise ValueError(f"크기는 1 이상이어야 합니다: {width}x{height}")
    if border_width < 0:
        raise ValueError(f"--border-width 는 0 이상이어야 합니다: {border_width}")

    grid: list[list[RGBA]] = [[bg for _ in range(width)] for _ in range(height)]

    inset = 0
    if border is not None and border_width > 0:
        inset = min(border_width, (min(width, height) + 1) // 2)
        for y in range(height):
            for x in range(width):
                if x < inset or y < inset or x >= width - inset or y >= height - inset:
                    grid[y][x] = _over(border, grid[y][x])

    meta: dict = {
        "width": width,
        "height": height,
        "glyph": glyph,
        "glyph_scale": 0,
        "clipped": False,
    }
    if glyph is None:
        return grid, meta

    bitmap = FONT[glyph]
    gscale = scale if scale is not None else compute_scale(width, height, inset)
    if gscale < 1:
        raise ValueError(f"--scale 은 1 이상이어야 합니다: {gscale}")
    gw = FONT_WIDTH * gscale
    gh = FONT_HEIGHT * gscale
    # 이미지 전체 기준 중앙 배치 (테두리가 있어도 시각적 중심은 이미지 중앙).
    ox = (width - gw) // 2
    oy = (height - gh) // 2

    clipped = False
    for row in range(FONT_HEIGHT):
        for col in range(FONT_WIDTH):
            if not bitmap[row][col]:
                continue
            for dy in range(gscale):
                y = oy + row * gscale + dy
                for dx in range(gscale):
                    x = ox + col * gscale + dx
                    if 0 <= x < width and 0 <= y < height:
                        grid[y][x] = _over(fg, grid[y][x])
                    else:
                        clipped = True

    meta["glyph_scale"] = gscale
    meta["clipped"] = clipped
    return grid, meta


def ascii_preview(
    grid: list[list[RGBA]],
    *,
    bg: RGBA | None = None,
    border: RGBA | None = None,
    on: str = "#",
    off: str = ".",
    edge: str = "+",
) -> str:
    """격자를 텍스트 픽셀 맵으로 (판독성을 눈으로 확인하는 용도).

    bg 를 주면 '배경과 다른 픽셀'을 on 으로 본다(불투명 타일도 글리프가 보인다).
    border 를 주면 테두리 색 픽셀만 edge 문자로 구분한다.
    bg 가 없으면 알파>0 기준(투명 배경 스프라이트용).
    """
    lines: list[str] = []
    for row in grid:
        chars: list[str] = []
        for px in row:
            if border is not None and px == border:
                chars.append(edge)
            elif (px == bg) if bg is not None else (px[3] == 0):
                chars.append(off)
            else:
                chars.append(on)
        lines.append("".join(chars))
    return "\n".join(lines)


# ---------------------------------------------------------------------------
# PNG 기록 (stdlib: zlib + struct) — 결정적
# ---------------------------------------------------------------------------
_ZLIB_LEVEL = 9  # 고정: 동일 입력 → 동일 바이트


def _chunk(tag: bytes, data: bytes) -> bytes:
    return (
        struct.pack(">I", len(data))
        + tag
        + data
        + struct.pack(">I", zlib.crc32(tag + data) & 0xFFFFFFFF)
    )


def encode_rgba_png(width: int, height: int, source) -> bytes:
    """8-bit RGBA PNG 바이트를 만든다 (필터 0 고정 → 결정적).

    source: `pixel(x, y) -> (r,g,b,a)` 호출 가능 객체, 또는 행 시퀀스(grid).
    """
    raw = bytearray()
    is_callable = callable(source)
    for y in range(height):
        raw.append(0)  # filter type 0 (None)
        row = None if is_callable else source[y]
        for x in range(width):
            px = source(x, y) if is_callable else row[x]
            raw.extend((px[0] & 255, px[1] & 255, px[2] & 255, px[3] & 255))
    ihdr = struct.pack(">IIBBBBB", width, height, 8, 6, 0, 0, 0)  # 6 = truecolor+alpha
    idat = zlib.compress(bytes(raw), _ZLIB_LEVEL)
    return (
        b"\x89PNG\r\n\x1a\n"
        + _chunk(b"IHDR", ihdr)
        + _chunk(b"IDAT", idat)
        + _chunk(b"IEND", b"")
    )


def write_rgba_png(path: Path, width: int, height: int, source) -> Path:
    """encode_rgba_png 결과를 파일로 기록(부모 디렉토리 자동 생성)."""
    path = Path(path)
    if path.parent and not path.parent.exists():
        path.parent.mkdir(parents=True, exist_ok=True)
    path.write_bytes(encode_rgba_png(width, height, source))
    return path


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
PLACEHOLDER_PREFIX = "PLACEHOLDER_"


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="placeholder_gen.py",
        description=(
            "플레이스홀더 스프라이트/타일 PNG 생성 (stdlib 전용, 결정적). "
            "글리프·색·크기는 전부 인자로 받는다 — 장르 하드코딩 없음."
        ),
        epilog="셸에서 '#RRGGBB' 는 따옴표로 감싸세요('#' 는 주석). '#' 생략도 허용됩니다.",
    )
    p.add_argument("--output", "-o", required=True, help="출력 PNG 경로")
    p.add_argument("--glyph", default=None,
                   help="가운데 그릴 문자 1개(예: '@'). 생략하면 도형(단색+테두리)만 그린다.")
    p.add_argument("--fg", default="#ffffff", help="글리프 색 (기본 #ffffff)")
    p.add_argument("--bg", default="transparent",
                   help="배경 색. 'transparent'(기본)=스프라이트용, 불투명 색=타일용")
    p.add_argument("--border", default=None, help="테두리 색 (생략 시 테두리 없음)")
    p.add_argument("--border-width", type=int, default=1, help="테두리 두께 픽셀 (기본 1)")
    p.add_argument("--size", type=int, default=16, help="정사각 한 변 픽셀 (기본 16)")
    p.add_argument("--width", type=int, default=None, help="가로 픽셀 (--size 대신)")
    p.add_argument("--height", type=int, default=None, help="세로 픽셀 (--size 대신)")
    p.add_argument("--scale", type=int, default=None,
                   help="글리프 정수 배수(기본: 자동 — 여백에 들어가는 최대 배수)")
    p.add_argument("--preview", action="store_true", help="텍스트 픽셀 맵을 함께 출력")
    p.add_argument("--json", action="store_true", help="생성 결과 메타를 JSON 으로 출력")
    p.add_argument("--list-glyphs", action="store_true",
                   help="지원 문자 목록만 출력하고 종료")
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    # --list-glyphs 는 --output 없이도 쓸 수 있게 선처리.
    argv = list(sys.argv[1:] if argv is None else argv)
    if "--list-glyphs" in argv:
        print(supported_glyphs())
        print(f"({len(FONT)}자 · {FONT_WIDTH}x{FONT_HEIGHT} 비트맵 · "
              f"미지원 문자는 {FALLBACK_GLYPH!r} 로 폴백)")
        return 0
    args = parser.parse_args(argv)

    # --- 인자 해석 ---
    try:
        width = args.width if args.width is not None else args.size
        height = args.height if args.height is not None else args.size
        if width <= 0 or height <= 0:
            raise ValueError(f"크기는 1 이상이어야 합니다: {width}x{height}")
        fg = parse_color(args.fg)
        bg = parse_color(args.bg)
        border = parse_color(args.border) if args.border is not None else None
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    glyph_arg = args.glyph
    if glyph_arg is not None and len(glyph_arg) != 1:
        print(f"오류: --glyph 는 문자 1개여야 합니다 (받은 값: {glyph_arg!r}, "
              f"길이 {len(glyph_arg)})", file=sys.stderr)
        return 2

    glyph, fell_back = resolve_glyph(glyph_arg)
    if fell_back:
        print(f"경고: 지원하지 않는 문자 {glyph_arg!r} → {FALLBACK_GLYPH!r} 로 대체합니다. "
              f"(--list-glyphs 로 지원 문자 확인)", file=sys.stderr)

    # --- 렌더 ---
    try:
        grid, meta = render_grid(
            width=width, height=height, glyph=glyph, fg=fg, bg=bg,
            border=border, border_width=args.border_width, scale=args.scale,
        )
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    if meta["clipped"]:
        print(f"경고: 글리프가 이미지({width}x{height})를 벗어나 잘렸습니다. "
              f"--size 를 키우거나 --scale 을 낮추세요.", file=sys.stderr)
    if all(px[3] == 0 for row in grid for px in row):
        print("경고: 결과가 완전히 투명합니다(화면에 아무것도 보이지 않음). "
              "--fg/--bg/--border 를 확인하세요.", file=sys.stderr)

    # --- 기록 ---
    out = Path(args.output)
    try:
        write_rgba_png(out, width, height, grid)
    except OSError as exc:
        print(f"오류: PNG 기록 실패: {exc}", file=sys.stderr)
        return 1

    meta.update({
        "output": str(out),
        "fg": args.fg, "bg": args.bg, "border": args.border,
        "border_width": args.border_width if border is not None else 0,
        "glyph_fallback": fell_back,
        "bytes": out.stat().st_size,
    })

    if args.json:
        print(json.dumps(meta, ensure_ascii=False))
    else:
        kind = "타일(불투명 배경)" if bg[3] == 255 else "스프라이트(투명 배경)"
        desc = f"글리프 {glyph!r} x{meta['glyph_scale']}" if glyph else "도형만"
        print(f"생성 완료: {out} ({width}x{height} RGBA · {kind} · {desc} · "
              f"{meta['bytes']}바이트)")
    if not out.name.startswith(PLACEHOLDER_PREFIX):
        print(f"[i] 참고: 파일명이 '{PLACEHOLDER_PREFIX}' 로 시작하지 않습니다. "
              f"플레이스홀더 에셋이면 접두사 규약(docs/conventions.md)을 지키고 "
              f"manifest.py 로 등록하세요.")

    if args.preview:
        print(ascii_preview(grid, bg=bg, border=border))

    return 0


if __name__ == "__main__":
    raise SystemExit(main())
