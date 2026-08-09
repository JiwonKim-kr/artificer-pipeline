# -*- coding: utf-8 -*-
"""제출 문서용 2계층 아키텍처 다이어그램 생성 (PNG).

04_ai_tech_doc.md §2 의 ASCII 다이어그램을 그림으로 대체한다 — Word/PDF 로 뽑을 때
ASCII 블록이 페이지 경계에서 잘려 형태가 무너지는 문제를 없애기 위함.
구조·문구는 ASCII 원본과 동일하게 유지한다.

실행: PYTHONUTF8=1 python pipeline/scripts/gen_arch_diagram.py
출력: docs/submission/word/img/arch_2layer.png (2x 해상도, Word 삽입용)
"""
from __future__ import annotations

from pathlib import Path
from PIL import Image, ImageDraw, ImageFont

S = 2  # 배율(레티나급 선명도 — Word 에서 절반 크기로 배치)
W, H = 1180 * S, 560 * S

NAVY = (31, 56, 100)
INK = (32, 32, 36)
GRAY = (108, 112, 120)
LINE = (150, 155, 165)
BOX_BG = (245, 246, 249)
BOX_BG2 = (237, 241, 248)
EDGE = (176, 182, 194)
WHITE = (255, 255, 255)

F = "C:/Windows/Fonts/malgun.ttf"
FB = "C:/Windows/Fonts/malgunbd.ttf"
FM = "C:/Windows/Fonts/consola.ttf"
FMB = "C:/Windows/Fonts/consolab.ttf"


def font(path: str, size: int) -> ImageFont.FreeTypeFont:
    return ImageFont.truetype(path, size * S)


f_tag = font(FB, 15)      # [검증 계층] 라벨
f_path = font(FMB, 16)    # 파일 경로(고정폭)
f_desc = font(F, 14)      # 설명
f_bul = font(F, 12)       # 불릿
f_note = font(F, 13)      # 화살표 주석


def rrect(d, box, fill, outline, r=10 * S, w=2):
    d.rounded_rectangle(box, radius=r, fill=fill, outline=outline, width=w)


def vline(d, x, y0, y1, w=3):
    d.line([(x, y0), (x, y1)], fill=LINE, width=w * S // 2 or 2)


def arrow_up(d, x, y0, y1):
    """아래(y0) → 위(y1) 방향 화살표."""
    d.line([(x, y0), (x, y1)], fill=NAVY, width=2 * S)
    h = 9 * S
    d.polygon([(x, y1 - 2 * S), (x - h // 2, y1 + h), (x + h // 2, y1 + h)], fill=NAVY)


img = Image.new("RGB", (W, H), WHITE)
d = ImageDraw.Draw(img)

LX = 40 * S           # 좌측 기준
BOXW = 700 * S        # 계층 박스 폭
CX = LX + BOXW // 2   # 세로 연결선 x

# ── [검증 계층] ─────────────────────────────────────────────
y = 26 * S
bh = 108 * S
rrect(d, (LX, y, LX + BOXW, y + bh), BOX_BG, EDGE)
d.rectangle((LX, y, LX + 6 * S, y + bh), fill=NAVY)  # 좌측 강조바
d.text((LX + 20 * S, y + 14 * S), "[검증 계층]", font=f_tag, fill=NAVY)
d.text((LX + 118 * S, y + 12 * S), "sim/opinion-model/*.mjs", font=f_path, fill=INK)
d.text((LX + 20 * S, y + 44 * S), "· 웹 빌드에서 제외 (export exclude_filter)", font=f_bul, fill=GRAY)
d.text((LX + 20 * S, y + 68 * S), "· 시뮬레이션 러너 + 몬테카를로 밸런싱 도구", font=f_bul, fill=GRAY)
# 우측 주석
d.text((LX + BOXW + 22 * S, y + 12 * S), "← 여론 확산 모델의", font=f_note, fill=NAVY)
d.text((LX + BOXW + 22 * S, y + 34 * S), "     원본 구현 (JS)", font=f_note, fill=NAVY)

# ── 연결선 ──────────────────────────────────────────────────
y2 = y + bh
vline(d, CX, y2, y2 + 34 * S)

# ── 공유 config ─────────────────────────────────────────────
y3 = y2 + 34 * S
ch = 76 * S
cw = 470 * S
cx0 = CX - cw // 2
rrect(d, (cx0, y3, cx0 + cw, y3 + ch), BOX_BG2, NAVY, r=8 * S, w=2)
d.text((cx0 + 24 * S, y3 + 12 * S), "같은 config 파일을 읽음", font=f_tag, fill=NAVY)
d.text((cx0 + 24 * S, y3 + 42 * S), "src/core/data/opinion_config.json", font=f_path, fill=INK)
d.text((cx0 + cw + 22 * S, y3 + 28 * S), "← 단일 출처", font=f_note, fill=NAVY)

# ── 연결선 ──────────────────────────────────────────────────
y4 = y3 + ch
vline(d, CX, y4, y4 + 34 * S)

# ── [런타임 계층] ───────────────────────────────────────────
y5 = y4 + 34 * S
bh2 = 76 * S
bh2 = 62 * S
rrect(d, (LX, y5, LX + BOXW, y5 + bh2), BOX_BG, EDGE)
d.rectangle((LX, y5, LX + 6 * S, y5 + bh2), fill=NAVY)
# 검증 계층 박스와 같은 줄 배치(태그 + 경로)로 맞춘다.
d.text((LX + 20 * S, y5 + 22 * S), "[런타임 계층]", font=f_tag, fill=NAVY)
d.text((LX + 118 * S, y5 + 20 * S), "src/core/opinion_model.gd", font=f_path, fill=INK)
d.text((LX + BOXW + 22 * S, y5 + 8 * S), "← AI 가 비트-정확 이식한", font=f_note, fill=NAVY)
d.text((LX + BOXW + 22 * S, y5 + 30 * S), "     게임 엔진 (GDScript)", font=f_note, fill=NAVY)

# ── parity 테스트 (아래에서 위로 화살표) ────────────────────
y6 = y5 + bh2
arrow_up(d, CX, y6 + 52 * S, y6 + 6 * S)
th = 60 * S
tw = 470 * S
tx0 = CX - tw // 2
ty = y6 + 56 * S
rrect(d, (tx0, ty, tx0 + tw, ty + th), WHITE, NAVY, r=8 * S, w=2)
d.text((tx0 + 24 * S, ty + 18 * S), "opinion_parity_test.gd", font=f_path, fill=NAVY)
d.text((tx0 + tw + 22 * S, ty + 8 * S), "← 두 계층의 출력을", font=f_note, fill=NAVY)
d.text((tx0 + tw + 22 * S, ty + 30 * S), "     대조하는 테스트", font=f_note, fill=NAVY)

# 실제 내용 폭에 맞춰 잘라낸다 — 우측 빈 여백이 남으면 Word 에서 그림이 작아 보인다.
right = max(
    LX + BOXW,
    max(d.textlength(t, font=f_note) for t in
        ["← 여론 확산 모델의", "     원본 구현 (JS)", "← AI 가 비트-정확 이식한",
         "     게임 엔진 (GDScript)", "← 두 계층의 출력을", "     대조하는 테스트"])
    + LX + BOXW + 22 * S,
)
out = Path("docs/submission/word/img/arch_2layer.png")
out.parent.mkdir(parents=True, exist_ok=True)
img.crop((0, 0, int(right + 34 * S), int(ty + th + 26 * S))).save(out)
print(f"생성: {out} ({int(right + 34 * S)}x{int(ty + th + 26 * S)})")
