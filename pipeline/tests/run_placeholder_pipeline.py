#!/usr/bin/env python3
"""placeholder_gen 파이프라인 테스트 (로컬 플레이스홀더 이미지 생성기).

Phase 1~4 의 run_lore_roundtrip / run_play_pipeline / run_art_pipeline /
run_se_pipeline / run_orchestration_pipeline 과 같은 스타일
(단일 파일·번호 섹션·check 헬퍼·PASS/FAIL·종료 코드).

  [1] 폰트/렌더 단위    : 5x7 폰트 데이터 무결성, 색 파싱, 스케일/중앙 배치,
                          알파 합성, 클리핑 감지.
  [2] 결정성            : 동일 인자 2회 → sha256 동일(라이브러리·CLI 양쪽).
                          서로 다른 글리프 → 서로 다른 바이트/픽셀(구분 가능성 증명).
  [3] PNG 규격          : art_post.py probe 로 교차 검증(크기/pix_fmt/alpha) +
                          자체 디코더로 픽셀 단위 투명/불투명·테두리·글리프 확인.
                          ffmpeg rawvideo 로 3자 교차 검증(있을 때).
  [4] CLI 계약          : 미지원 문자 폴백(+경고), 인자 오류 종료 코드,
                          --json/--preview/--list-glyphs, 완전 투명 경고.
  [5] Godot 임포트 호환 : 저장소 임시 복제본에 생성물을 넣고
                          `godot --headless --import` 성공 확인.
  [6] reskin 호환       : 복제본에서 생성 → manifest.py 등록 → verify 게이트 #3 →
                          art_reskin.py 로 실제 에셋 교체까지 왕복.
  [7] 회귀              : 기존 러너 5종 + verify 게이트 통과 유지
                          (verify --full 안에서 호출되면 중복 실행 생략).

CLAUDE.md 규칙: 실데이터(assets/, scenes/, pipeline/manifest.json, src/,
lore/canon/, docs/specs/)는 절대 수정하지 않는다. 쓰기 검사는 전부 임시 복제본 대상.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import hashlib
import json
import os
import shutil
import struct
import subprocess
import sys
import tempfile
import zlib
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
SCRIPTS = TESTS_DIR.parent / "scripts"

sys.path.insert(0, str(SCRIPTS))
import placeholder_gen as pg  # noqa: E402
import verify as verify_mod  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
_failures = 0

# verify --full 안에서 호출되었는지 (중복 실행/재귀 방지)
UNDER_FULL = os.environ.get(verify_mod.IN_FULL_ENV) == "1"

GEN = SCRIPTS / "placeholder_gen.py"


def check(label: str, condition: bool) -> None:
    global _failures
    if not condition:
        _failures += 1
    print(f"  [{PASS if condition else FAIL}] {label}")


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    return subprocess.run(cmd, capture_output=True, text=True, **kw)


def _gen(*args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(GEN), *args])


def _have_godot() -> bool:
    godot = os.environ.get("GODOT_BIN", "godot")
    return shutil.which(godot) is not None or Path(godot).exists()


def _have_ffmpeg() -> bool:
    return (shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg")) is not None
            and shutil.which(os.environ.get("FFPROBE_BIN", "ffprobe")) is not None)


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


# ---------------------------------------------------------------------------
# 최소 PNG 디코더 (검증용 — 생성기와 독립적으로 픽셀을 되읽는다)
# ---------------------------------------------------------------------------
def decode_rgba_png(path: Path) -> tuple[int, int, list[list[tuple[int, ...]]]]:
    """8-bit RGBA / 필터 0 PNG 를 디코드. (width, height, rows) 반환.

    생성기가 실제로 규격에 맞는 PNG 를 쓰는지 **독립적으로** 확인하기 위한 것이므로
    생성기 코드를 재사용하지 않는다(자기 채점 방지).
    """
    data = path.read_bytes()
    if data[:8] != b"\x89PNG\r\n\x1a\n":
        raise ValueError("PNG 시그니처 불일치")
    pos = 8
    width = height = 0
    idat = bytearray()
    tags: list[str] = []
    while pos < len(data):
        (length,) = struct.unpack(">I", data[pos:pos + 4])
        tag = data[pos + 4:pos + 8]
        body = data[pos + 8:pos + 8 + length]
        (crc,) = struct.unpack(">I", data[pos + 8 + length:pos + 12 + length])
        if crc != (zlib.crc32(tag + body) & 0xFFFFFFFF):
            raise ValueError(f"CRC 불일치: {tag!r}")
        tags.append(tag.decode("ascii"))
        if tag == b"IHDR":
            width, height, depth, ctype, comp, filt, inter = struct.unpack(">IIBBBBB", body)
            if (depth, ctype, comp, filt, inter) != (8, 6, 0, 0, 0):
                raise ValueError(f"8-bit RGBA 논인터레이스가 아님: {body!r}")
        elif tag == b"IDAT":
            idat.extend(body)
        pos += 12 + length
    if tags[0] != "IHDR" or tags[-1] != "IEND":
        raise ValueError(f"청크 순서 이상: {tags}")
    raw = zlib.decompress(bytes(idat))
    stride = width * 4
    rows: list[list[tuple[int, ...]]] = []
    off = 0
    for _ in range(height):
        ftype = raw[off]
        if ftype != 0:
            raise ValueError(f"필터 타입 0 만 지원(발견: {ftype})")
        line = raw[off + 1:off + 1 + stride]
        rows.append([tuple(line[i:i + 4]) for i in range(0, stride, 4)])
        off += 1 + stride
    return width, height, rows


def _probe(path: Path) -> dict:
    r = _run([sys.executable, str(SCRIPTS / "art_post.py"), "probe", "--input", str(path)])
    return json.loads(r.stdout) if r.returncode == 0 else {}


# ---------------------------------------------------------------------------
# [1] 폰트/렌더 단위
# ---------------------------------------------------------------------------
def section_font_render() -> None:
    print("\n[1] 폰트/렌더 단위 — 폰트 데이터 · 색 파싱 · 스케일/배치 · 알파 합성")

    # 폰트 데이터 무결성 (모듈 로드 시 _build_font 가 이미 검증하지만 명시적으로 재확인)
    ok_shape = all(
        len(bm) == pg.FONT_HEIGHT and all(len(r) == pg.FONT_WIDTH for r in bm)
        for bm in pg.FONT.values()
    )
    check(f"모든 글리프가 {pg.FONT_WIDTH}x{pg.FONT_HEIGHT} ({len(pg.FONT)}자)", ok_shape)

    required = (
        [chr(c) for c in range(ord("A"), ord("Z") + 1)]
        + [chr(c) for c in range(ord("a"), ord("z") + 1)]
        + [chr(c) for c in range(ord("0"), ord("9") + 1)]
        + list("@#%!?$&*+-.,/\\<>()[]{}=~^_|: ")
    )
    missing = [c for c in required if c not in pg.FONT]
    check(f"필수 문자 집합 전부 지원 (누락 {missing})", not missing)

    # 공백 외에는 켜진 픽셀이 있어야 한다(빈 글리프 = 보이지 않는 플레이스홀더 사고 방지)
    blanks = [c for c, bm in pg.FONT.items()
              if c != " " and not any(any(r) for r in bm)]
    check(f"공백 외 빈 글리프 없음 (빈 글리프: {blanks})", not blanks)

    # 서로 다른 문자는 서로 다른 비트맵이어야 한다(시각적 구분 가능성의 근거)
    seen: dict[tuple, str] = {}
    dupes: list[tuple[str, str]] = []
    for c, bm in pg.FONT.items():
        if bm in seen:
            dupes.append((seen[bm], c))
        seen[bm] = c
    check(f"중복 비트맵 없음 (충돌: {dupes})", not dupes)

    # 색 파싱
    check("#RRGGBB 파싱", pg.parse_color("#ff8000") == (255, 128, 0, 255))
    check("#RRGGBBAA 파싱", pg.parse_color("#00ff0080") == (0, 255, 0, 128))
    check("'#' 생략 허용", pg.parse_color("ff8000") == (255, 128, 0, 255))
    check("transparent 키워드", pg.parse_color("transparent") == (0, 0, 0, 0))
    bad = 0
    for s in ("#ff", "zzzzzz", "#1234567", ""):
        try:
            pg.parse_color(s)
        except ValueError:
            bad += 1
    check("잘못된 색 4종 모두 ValueError", bad == 4)

    # 스케일 계산 / 중앙 배치
    check("16x16 테두리 없음 → 스케일 2", pg.compute_scale(16, 16, 0) == 2)
    check("16x16 테두리 1px → 스케일 2", pg.compute_scale(16, 16, 1) == 2)
    check("32x32 → 스케일 4", pg.compute_scale(32, 32, 0) == 4)
    check("8x8 → 스케일 1(최소값 보장)", pg.compute_scale(8, 8, 0) == 1)
    check("4x4 → 스케일 1(0 방지)", pg.compute_scale(4, 4, 0) == 1)

    fg = (255, 210, 63, 255)
    grid, meta = pg.render_grid(width=16, height=16, glyph="@", fg=fg)
    check("16x16 '@' 자동 스케일 2", meta["glyph_scale"] == 2)
    check("16x16 '@' 잘림 없음", meta["clipped"] is False)
    lit = [(x, y) for y, row in enumerate(grid) for x, px in enumerate(row) if px[3] > 0]
    xs = [x for x, _ in lit]
    ys = [_y for _, _y in lit]
    # 5x7 x2 = 10x14 → ox=3, oy=1. '@' 는 가장자리 열/행을 모두 쓰므로 경계가 정확히 맞음.
    check("글리프 중앙 배치 (x 3..12)", min(xs) == 3 and max(xs) == 12)
    check("글리프 중앙 배치 (y 1..14)", min(ys) == 1 and max(ys) == 14)
    check("글리프 픽셀 색이 fg", all(grid[y][x] == fg for x, y in lit))

    # 투명 배경 = 스프라이트용
    check("bg 미지정 시 비글리프 픽셀 alpha=0", grid[0][0] == (0, 0, 0, 0))

    # 불투명 배경 + 테두리 = 타일용
    bg = (43, 45, 36, 255)
    bd = (63, 67, 52, 255)
    tgrid, tmeta = pg.render_grid(width=16, height=16, glyph=".", fg=fg, bg=bg, border=bd)
    check("타일: 모든 픽셀 불투명", all(px[3] == 255 for row in tgrid for px in row))
    check("타일: 테두리 색 적용", tgrid[0][0] == bd and tgrid[15][15] == bd and tgrid[0][8] == bd)
    check("타일: 안쪽은 배경색", tgrid[3][3] == bg)

    # 알파 합성 (반투명 fg over 불투명 bg)
    half = (255, 0, 0, 128)
    hgrid, _ = pg.render_grid(width=16, height=16, glyph="#", fg=half, bg=(0, 0, 0, 255))
    blended = {px for row in hgrid for px in row} - {(0, 0, 0, 255)}
    check("반투명 fg 는 bg 와 합성되어 불투명 중간색",
          all(px[3] == 255 and 0 < px[0] < 255 for px in blended) and blended)

    # 클리핑 감지 (아주 작은 캔버스)
    _, cmeta = pg.render_grid(width=4, height=4, glyph="A", fg=fg)
    check("4x4 글리프 → clipped=True 보고", cmeta["clipped"] is True)

    # 도형 전용 모드 (글리프 없음)
    sgrid, smeta = pg.render_grid(width=16, height=16, glyph=None, bg=bg, border=bd)
    check("글리프 없음 모드: glyph_scale=0", smeta["glyph_scale"] == 0)
    check("글리프 없음 모드: 테두리+단색만", sgrid[0][0] == bd and sgrid[8][8] == bg)

    # 미지원 문자 폴백 (라이브러리 레벨)
    g, fell = pg.resolve_glyph("가")
    check("미지원 문자 → '?' 폴백 신호", g == pg.FALLBACK_GLYPH and fell is True)
    g, fell = pg.resolve_glyph("@")
    check("지원 문자 → 폴백 아님", g == "@" and fell is False)


# ---------------------------------------------------------------------------
# [2] 결정성 / 구분 가능성
# ---------------------------------------------------------------------------
def section_determinism() -> None:
    print("\n[2] 결정성 — 동일 인자 2회 → 동일 바이트 · 다른 글리프 → 다른 결과")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        a, b = tdp / "a.png", tdp / "b.png"
        args = ["--glyph", "@", "--fg", "#ffd23f", "--bg", "transparent", "--size", "16"]
        r1 = _gen(*args, "--output", str(a))
        r2 = _gen(*args, "--output", str(b))
        check("CLI 2회 실행 종료 0", r1.returncode == 0 and r2.returncode == 0)
        check("CLI 2회 → sha256 동일(결정적)", _sha256(a) == _sha256(b))

        # 라이브러리 레벨에서도 동일 (인코딩 경로 결정성)
        g1, _ = pg.render_grid(width=16, height=16, glyph="@", fg=(255, 210, 63, 255))
        g2, _ = pg.render_grid(width=16, height=16, glyph="@", fg=(255, 210, 63, 255))
        e1 = pg.encode_rgba_png(16, 16, g1)
        e2 = pg.encode_rgba_png(16, 16, g2)
        check("encode_rgba_png 재현성", e1 == e2)
        check("CLI 산출물 == 라이브러리 산출물", a.read_bytes() == e1)

        # 콜백 소스와 격자 소스가 동일한 바이트를 낸다(테스트가 쓰는 두 경로 일치)
        e3 = pg.encode_rgba_png(16, 16, lambda x, y: g1[y][x])
        check("콜백/격자 소스 동일 결과", e3 == e1)

        # 서로 다른 글리프 → 서로 다른 파일/픽셀 (구분 가능성 증명)
        digests: dict[str, str] = {}
        pixmaps: dict[str, str] = {}
        for ch in "@#%$&AZaz09.!?*+-":
            p = tdp / f"g_{ord(ch)}.png"
            r = _gen("--glyph", ch, "--fg", "#ffffff", "--output", str(p))
            assert r.returncode == 0, r.stderr
            digests[ch] = _sha256(p)
            grid, _ = pg.render_grid(width=16, height=16, glyph=ch)
            pixmaps[ch] = pg.ascii_preview(grid)
        check(f"글리프 {len(digests)}종 전부 서로 다른 sha256",
              len(set(digests.values())) == len(digests))
        check(f"글리프 {len(pixmaps)}종 전부 서로 다른 픽셀 맵",
              len(set(pixmaps.values())) == len(pixmaps))

        # 색만 달라도 결과가 달라야 한다(같은 글리프의 색 구분)
        c1, c2 = tdp / "c1.png", tdp / "c2.png"
        _gen("--glyph", "s", "--fg", "#ff0000", "--output", str(c1))
        _gen("--glyph", "s", "--fg", "#00ff00", "--output", str(c2))
        check("같은 글리프 다른 색 → 다른 바이트", _sha256(c1) != _sha256(c2))

        # 스프라이트(투명) vs 타일(불투명) 도 구분된다
        s1, t1 = tdp / "s1.png", tdp / "t1.png"
        _gen("--glyph", ".", "--output", str(s1))
        _gen("--glyph", ".", "--bg", "#2b2d24", "--output", str(t1))
        check("투명/불투명 모드 → 다른 바이트", _sha256(s1) != _sha256(t1))


# ---------------------------------------------------------------------------
# [3] PNG 규격 (art_post probe 교차 검증 + 자체 디코더 + ffmpeg raw)
# ---------------------------------------------------------------------------
def section_png_spec() -> None:
    print("\n[3] PNG 규격 — art_post probe 교차 검증 · 픽셀 단위 투명/불투명")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # (a) 스프라이트: 투명 배경
        sprite = tdp / "PLACEHOLDER_sprite.png"
        r = _gen("--glyph", "@", "--fg", "#ffd23f", "--size", "16", "--output", str(sprite))
        check("스프라이트 생성 종료 0", r.returncode == 0)
        w, h, rows = decode_rgba_png(sprite)
        check("자체 디코드: 16x16 8-bit RGBA", (w, h) == (16, 16))
        check("스프라이트: 코너 alpha=0(투명 배경)", rows[0][0][3] == 0)
        check("스프라이트: 글리프 픽셀 불투명 fg",
              any(px == (255, 210, 63, 255) for row in rows for px in row))
        alphas = {px[3] for row in rows for px in row}
        check("스프라이트: 알파는 0/255 두 값만(반투명 없음)", alphas == {0, 255})

        # (b) 타일: 불투명 배경 + 테두리
        tile = tdp / "PLACEHOLDER_tile.png"
        r = _gen("--glyph", ".", "--fg", "#6b705c", "--bg", "#2b2d24",
                 "--border", "#3f4334", "--size", "16", "--output", str(tile))
        check("타일 생성 종료 0", r.returncode == 0)
        _, _, trows = decode_rgba_png(tile)
        check("타일: 전 픽셀 불투명(alpha=255)",
              all(px[3] == 255 for row in trows for px in row))
        check("타일: 테두리 링 색 정확",
              all(trows[0][x] == (63, 67, 52, 255) for x in range(16))
              and all(trows[15][x] == (63, 67, 52, 255) for x in range(16))
              and all(trows[y][0] == (63, 67, 52, 255) for y in range(16)))
        check("타일: 내부 배경색", trows[3][3] == (43, 45, 36, 255))

        # (c) 비정사각 + 굵은 테두리
        wide = tdp / "wide.png"
        r = _gen("--glyph", "W", "--width", "32", "--height", "16",
                 "--bg", "#101010", "--border", "#ff00ff", "--border-width", "2",
                 "--output", str(wide))
        check("비정사각 생성 종료 0", r.returncode == 0)
        ww, wh, wrows = decode_rgba_png(wide)
        check("비정사각 32x16", (ww, wh) == (32, 16))
        check("테두리 2px 적용",
              wrows[1][1] == (255, 0, 255, 255) and wrows[2][2] != (255, 0, 255, 255))

        # (d) art_post.py probe 교차 검증 (ffprobe 기준의 독립 확인)
        if _have_ffmpeg():
            info = _probe(sprite)
            check("probe: 16x16", info.get("width") == 16 and info.get("height") == 16)
            check("probe: has_alpha", info.get("has_alpha") is True)
            check("probe: pix_fmt rgba 계열", str(info.get("pix_fmt", "")).startswith("rgba"))
            tinfo = _probe(tile)
            check("probe(타일): 16x16 rgba", tinfo.get("width") == 16 and tinfo.get("has_alpha") is True)
            winfo = _probe(wide)
            check("probe(비정사각): 32x16", winfo.get("width") == 32 and winfo.get("height") == 16)

            # ffmpeg rawvideo 로 3자 교차 검증 (디코더 자기 채점 방지)
            raw = tdp / "sprite.raw"
            _run([os.environ.get("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-i", str(sprite),
                  "-f", "rawvideo", "-pix_fmt", "rgba", str(raw), "-y"])
            data = raw.read_bytes()
            same = all(
                tuple(data[(y * 16 + x) * 4:(y * 16 + x) * 4 + 4]) == rows[y][x]
                for y in range(16) for x in range(16)
            )
            check("ffmpeg rawvideo 픽셀 == 자체 디코더 픽셀", same)

            # art_post resize 로 확대해도 격자 보존 (후처리 도구와의 역할 분담 확인)
            big = tdp / "sprite_x4.png"
            r = _run([sys.executable, str(SCRIPTS / "art_post.py"), "resize",
                      "--input", str(sprite), "--output", str(big), "--scale", "4.0"])
            binfo = _probe(big)
            check("art_post resize x4 → 64x64 alpha 유지",
                  r.returncode == 0 and binfo.get("width") == 64 and binfo.get("has_alpha") is True)
        else:
            print("  [SKIP] ffmpeg 없음 — art_post probe/resize 교차 검증 생략")


# ---------------------------------------------------------------------------
# [4] CLI 계약 (폴백 · 오류 · 출력 형식)
# ---------------------------------------------------------------------------
def section_cli_contract() -> None:
    print("\n[4] CLI 계약 — 폴백 · 인자 오류 · 출력 형식")
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)

        # 미지원 문자 → '?' 폴백 + 경고 + 종료 0
        fb = tdp / "fallback.png"
        r = _gen("--glyph", "가", "--output", str(fb))
        check("미지원 문자 → 종료 0(크래시 아님)", r.returncode == 0)
        check("미지원 문자 → 경고 출력", "경고" in r.stderr and "?" in r.stderr)
        q = tdp / "q.png"
        _gen("--glyph", "?", "--output", str(q))
        check("폴백 결과 == '?' 결과", _sha256(fb) == _sha256(q))
        check("Traceback 없음", "Traceback" not in r.stderr)

        # 인자 오류 → 종료 2, 스택트레이스 없음
        r = _gen("--glyph", "ab", "--output", str(tdp / "x.png"))
        check("--glyph 2글자 → 종료 2", r.returncode == 2 and "Traceback" not in r.stderr)
        r = _gen("--fg", "notacolor", "--output", str(tdp / "x.png"))
        check("잘못된 색 → 종료 2", r.returncode == 2 and "색 형식" in r.stderr)
        r = _gen("--size", "0", "--output", str(tdp / "x.png"))
        check("크기 0 → 종료 2", r.returncode == 2)
        r = _gen("--glyph", "@")
        check("--output 누락 → 종료 2(argparse)", r.returncode == 2)

        # 잘림 경고
        r = _gen("--glyph", "A", "--size", "4", "--output", str(tdp / "tiny.png"))
        check("4x4 → 잘림 경고 + 종료 0", r.returncode == 0 and "잘렸" in r.stderr)

        # 완전 투명 경고 (아무것도 안 보이는 사고 방지)
        r = _gen("--output", str(tdp / "empty.png"))
        check("글리프/배경/테두리 없음 → 완전 투명 경고",
              r.returncode == 0 and "완전히 투명" in r.stderr)

        # --json 메타
        jp = tdp / "PLACEHOLDER_j.png"
        r = _gen("--glyph", "@", "--size", "32", "--output", str(jp), "--json")
        meta = json.loads(r.stdout)
        check("--json: width/height/glyph/scale",
              meta["width"] == 32 and meta["height"] == 32
              and meta["glyph"] == "@" and meta["glyph_scale"] == 4)
        check("--json: bytes 가 실제 크기와 일치", meta["bytes"] == jp.stat().st_size)
        check("--json: PLACEHOLDER_ 이름이면 안내문 없음", "[i] 참고" not in r.stdout)
        r = _gen("--glyph", "@", "--output", str(tdp / "noprefix.png"))
        check("PLACEHOLDER_ 아닌 이름 → 접두사 안내", "PLACEHOLDER_" in r.stdout)

        # --preview: 텍스트 픽셀 맵 (Claude 가 판독성을 눈으로 검사하는 경로)
        r = _gen("--glyph", "@", "--output", str(tdp / "p.png"), "--preview")
        lines = [ln for ln in r.stdout.splitlines() if set(ln) <= {"#", ".", "+"} and len(ln) == 16]
        check("--preview: 16행 픽셀 맵 출력", len(lines) == 16)
        check("--preview: 켜진 픽셀 존재", any("#" in ln for ln in lines))
        r = _gen("--glyph", ".", "--bg", "#2b2d24", "--border", "#3f4334",
                 "--output", str(tdp / "p2.png"), "--preview")
        check("--preview(타일): 배경/테두리/글리프 3층 구분",
              "+" in r.stdout and "#" in r.stdout and "." in r.stdout)

        # --list-glyphs
        r = _gen("--list-glyphs")
        check("--list-glyphs 종료 0 + 목록 출력",
              r.returncode == 0 and "@" in r.stdout and "Z" in r.stdout and "z" in r.stdout)

        # 부모 디렉토리 자동 생성
        deep = tdp / "a" / "b" / "PLACEHOLDER_c.png"
        r = _gen("--glyph", "c", "--output", str(deep))
        check("없는 상위 디렉토리 자동 생성", r.returncode == 0 and deep.exists())

        # 매니페스트를 건드리지 않는다 (쓰기 창구는 manifest.py 뿐 — CLAUDE.md 원칙 3):
        # 코드 본문(모듈 docstring 이후)에 manifest 관련 쓰기 경로가 아예 없어야 한다.
        body = GEN.read_text(encoding="utf-8").split('"""', 2)[-1]
        check("생성기 코드 본문에 manifest.json 참조 없음", "manifest.json" not in body)


# ---------------------------------------------------------------------------
# 저장소 복제 헬퍼
# ---------------------------------------------------------------------------
def _clone_repo(dst: Path) -> None:
    shutil.copytree(
        REPO_ROOT, dst,
        ignore=shutil.ignore_patterns(".git", ".godot", "__pycache__", "*.pyc", "export"),
    )


SLIME_TSCN = """[gd_scene load_steps=2 format=3]

[ext_resource type="Texture2D" path="res://assets/art/sprites/enemy/PLACEHOLDER_slime_idle.png" id="1_slime"]

[node name="Slime" type="Node2D"]

[node name="Sprite2D" type="Sprite2D" parent="."]
texture = ExtResource("1_slime")
"""


def _seed_clone_placeholder(clone: Path) -> tuple[Path, str]:
    """복제본에 placeholder 스프라이트 + 씬 + 매니페스트 등록까지 심는다."""
    asset = clone / "assets" / "art" / "sprites" / "enemy" / "PLACEHOLDER_slime_idle.png"
    r = _gen("--glyph", "s", "--fg", "#7fc47f", "--size", "16", "--output", str(asset))
    assert r.returncode == 0, r.stderr
    (clone / "scenes" / "slime.tscn").write_text(SLIME_TSCN, encoding="utf-8")
    entry_id = "art:enemy/slime_idle"
    r = _run([
        sys.executable, str(SCRIPTS / "manifest.py"),
        "--manifest", str(clone / "pipeline" / "manifest.json"),
        "--schema", str(clone / "pipeline" / "schemas" / "asset-manifest.schema.json"),
        "add", "--id", entry_id, "--track", "art", "--status", "placeholder",
        "--spec", "적 슬라임 대기 스프라이트(플레이스홀더: 글리프 's')",
        "--requested-by", "scene_node:scenes/slime.tscn::Slime/Sprite2D",
        "--file", "assets/art/sprites/enemy/PLACEHOLDER_slime_idle.png",
    ])
    assert r.returncode == 0, r.stderr
    return asset, entry_id


# ---------------------------------------------------------------------------
# [5] Godot 임포트 호환
# ---------------------------------------------------------------------------
def section_godot_import() -> None:
    print("\n[5] Godot 임포트 호환 — 임시 복제본에 생성물 배치 후 headless --import")
    if not _have_godot():
        print("  [SKIP] godot 없음 — 임포트 호환 검증 생략")
        return
    godot = os.environ.get("GODOT_BIN", "godot")
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        _clone_repo(clone)
        check("복제본이 원본이 아님", clone.resolve() != REPO_ROOT.resolve())

        # 스프라이트/타일/비정사각/큰 크기 — 다양한 산출물을 한 번에 임포트
        specs = [
            ("enemy/PLACEHOLDER_slime_idle.png", ["--glyph", "s", "--fg", "#7fc47f"]),
            ("tiles/PLACEHOLDER_wall.png",
             ["--glyph", "#", "--fg", "#8d8d8d", "--bg", "#1c1c1c", "--border", "#3a3a3a"]),
            ("item/PLACEHOLDER_potion.png",
             ["--glyph", "!", "--fg", "#e05c5c", "--size", "32"]),
            ("ui_icon/PLACEHOLDER_hp_icon.png",
             ["--glyph", "+", "--fg", "#ff4d4d", "--width", "24", "--height", "12"]),
        ]
        for rel, extra in specs:
            out = clone / "assets" / "art" / "sprites" / rel
            r = _gen(*extra, "--output", str(out))
            assert r.returncode == 0, r.stderr

        r = _run([godot, "--headless", "--path", str(clone), "--import"], timeout=300)
        check("godot --headless --import 종료 0", r.returncode == 0)
        imported = list((clone / ".godot" / "imported").glob("PLACEHOLDER_slime_idle.png-*.ctex"))
        check("생성물이 .ctex 로 임포트됨", bool(imported))
        others = [
            list((clone / ".godot" / "imported").glob(f"{Path(rel).name}-*.ctex"))
            for rel, _ in specs
        ]
        check("4종(스프라이트/타일/32px/비정사각) 전부 임포트", all(others))
        err = (r.stderr or "") + (r.stdout or "")
        check("임포트 로그에 텍스처 오류 없음",
              "Error" not in err and "ERROR: Cannot" not in err)

        # 원본 저장소 불변
        check("원본 assets/ 에 신규 파일 없음",
              not (REPO_ROOT / "assets/art/sprites/enemy").exists())


# ---------------------------------------------------------------------------
# [6] reskin 호환 (PLACEHOLDER_ 규약 · 매니페스트 · art_reskin 왕복)
# ---------------------------------------------------------------------------
def section_reskin_compat() -> None:
    print("\n[6] reskin 호환 — 생성 → manifest 등록 → verify 게이트 → art_reskin 교체")
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        _clone_repo(clone)
        mpath = clone / "pipeline" / "manifest.json"
        spath = clone / "pipeline" / "schemas" / "asset-manifest.schema.json"
        placeholder, entry_id = _seed_clone_placeholder(clone)
        scene = clone / "scenes" / "slime.tscn"
        real = clone / "assets" / "art" / "sprites" / "enemy" / "slime_idle.png"

        check("생성물이 PLACEHOLDER_ 규약 경로에 존재", placeholder.exists())
        r = _run([sys.executable, str(SCRIPTS / "manifest.py"),
                  "--manifest", str(mpath), "--schema", str(spath), "validate"])
        check("등록 후 매니페스트 유효(스키마 통과)", r.returncode == 0)

        # 생성기 자체는 매니페스트를 쓰지 않는다 (실측)
        before = _sha256(mpath)
        _gen("--glyph", "x", "--output", str(clone / "assets/art/sprites/enemy/PLACEHOLDER_x.png"))
        check("placeholder_gen 실행이 매니페스트를 변경하지 않음", _sha256(mpath) == before)
        (clone / "assets/art/sprites/enemy/PLACEHOLDER_x.png").unlink()

        # verify 게이트 #3 (네이밍/디렉토리) — 생성물이 규칙을 위반하지 않는가
        violations = verify_mod.check_naming_rules(clone, mpath, spath)
        check(f"게이트 #3 위반 없음 (위반: {[v.render() for v in violations]})", not violations)

        # 매니페스트 정합성 게이트 #4 (file 이 실제로 존재)
        stage = verify_mod.play_test_mod.run_manifest_integrity(mpath, spath, clone)
        check("게이트 #4 매니페스트↔파일 정합", stage.ok)

        # art_reskin: 실제 에셋 부재 → skip (크래시 아님)
        def reskin(*extra: str) -> subprocess.CompletedProcess[str]:
            return _run([
                sys.executable, str(clone / "pipeline" / "scripts" / "art_reskin.py"),
                "--project", str(clone), "--manifest", str(mpath), "--schema", str(spath),
                *extra,
            ])

        r = reskin("--id", entry_id, "--skip-import")
        check("실제 에셋 부재 → 종료 0 · 무변경", r.returncode == 0)
        check("부재 시 tscn 미변경",
              "PLACEHOLDER_slime_idle" in scene.read_text(encoding="utf-8"))

        # art gen 산출물 시뮬레이션: 같은 도구로 '실제' 에셋을 만든다(다른 글리프)
        r = _gen("--glyph", "S", "--fg", "#3fa63f", "--size", "16", "--output", str(real))
        check("실제 에셋 생성 종료 0", r.returncode == 0)
        check("placeholder 와 실제 에셋은 서로 다른 픽셀",
              _sha256(placeholder) != _sha256(real))

        r = reskin("--id", entry_id, "--dry-run")
        check("dry-run: SWAP 계획 표시 · 무변경",
              r.returncode == 0 and "[SWAP]" in r.stdout
              and "PLACEHOLDER_slime_idle" in scene.read_text(encoding="utf-8"))
        check("dry-run: placeholder 삭제 예정만 표시(실삭제 없음)",
              "삭제 예정" in r.stdout and placeholder.exists())

        r = reskin("--id", entry_id, "--skip-import")
        check("적용 종료 0", r.returncode == 0)
        text = scene.read_text(encoding="utf-8")
        check("tscn: PLACEHOLDER 제거 · 실제 경로로 교체",
              "PLACEHOLDER_slime_idle" not in text
              and "res://assets/art/sprites/enemy/slime_idle.png" in text)
        r = _run([sys.executable, str(SCRIPTS / "manifest.py"),
                  "--manifest", str(mpath), "--schema", str(spath), "list", "--json"])
        entry = next(e for e in json.loads(r.stdout) if e["id"] == entry_id)
        check("매니페스트 status=generated · file=실제 경로",
              entry["status"] == "generated"
              and entry["file"] == "assets/art/sprites/enemy/slime_idle.png")

        # 교체 후 게이트 상태 (재작업 0 증명).
        # art_reskin 은 교체 성공 직후 낡은 PLACEHOLDER_ 파일을 스스로 지우므로,
        # 별도 수작업 정리 없이 verify 게이트 #3(undeclared_placeholder)이 곧바로 통과한다.
        # (art_reskin↔verify 갭 수정: 예전에는 여기서 '미등록 placeholder' 위반이 남았다.)
        check("reskin 이 낡은 placeholder 파일을 스스로 삭제함", not placeholder.exists())
        violations = verify_mod.check_naming_rules(clone, mpath, spath)
        check(f"reskin 직후 게이트 #3 위반 없음 "
              f"(위반: {[v.render() for v in violations]})", not violations)
        stage = verify_mod.play_test_mod.run_manifest_integrity(mpath, spath, clone)
        check("교체 후 게이트 #4 정합 유지", stage.ok)

        # godot 이 있으면 임포트 + play_test 까지 (종단 증명)
        if _have_godot():
            r = _run([sys.executable, str(SCRIPTS / "play_test.py"), "--project", str(clone),
                      "--manifest", str(mpath), "--schema", str(spath)])
            check("(godot) reskin 후 play_test 전체 통과",
                  r.returncode == 0 and "전체 통과" in r.stdout)
        else:
            print("  [SKIP] godot 없음 — play_test 종단 검증 생략")

        # 원본 저장소 불변 확인
        orig = (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8")
        check("원본 매니페스트 불변(slime 엔트리 없음)", "slime_idle" not in orig)


# ---------------------------------------------------------------------------
# [7] 회귀 (기존 러너 5종 + verify 게이트)
# ---------------------------------------------------------------------------
def section_regression() -> None:
    print("\n[7] 회귀 — 기존 러너 5종 + verify 게이트 통과 유지")
    if UNDER_FULL:
        print("  [SKIP] verify --full 안에서 호출됨 — 러너는 verify --full 이 직접 실행하므로 중복 생략")
        return

    for name in ("run_lore_roundtrip.py", "run_play_pipeline.py",
                 "run_art_pipeline.py", "run_se_pipeline.py",
                 "run_orchestration_pipeline.py"):
        r = _run([sys.executable, str(TESTS_DIR / name)])
        check(f"{name} 통과", r.returncode == 0)

    # 기능 수용 테스트(run_acceptance_*.py)는 검증 대상 게임에 종속이므로 여기서
    # 고정 호출하지 않는다. verify --full 이 pipeline/tests/run_*.py 를 자동 발견해
    # 실행하므로, 새 게임의 play build 가 수용 테스트를 만들면 자동으로 포함된다.

    # verify 게이트 (저장소 원본 대상, 읽기 전용)
    gates, exec_errors = verify_mod.run_gates(
        REPO_ROOT,
        REPO_ROOT / "pipeline" / "manifest.json",
        REPO_ROOT / "pipeline" / "schemas" / "asset-manifest.schema.json",
        os.environ.get("GODOT_BIN", "godot"),
        skip_godot=not _have_godot(),
    )
    failed = [f"#{g.num} {g.name}" for g in gates if g.status == "FAIL"]
    check(f"verify 게이트 실패 없음 (실패: {failed})", not failed and exec_errors == 0)


def main() -> int:
    print("=" * 64)
    print("placeholder 파이프라인 테스트: placeholder_gen (로컬 이미지 생성기)")
    print("=" * 64)
    section_font_render()
    section_determinism()
    section_png_spec()
    section_cli_contract()
    section_godot_import()
    section_reskin_compat()
    section_regression()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
