#!/usr/bin/env python3
"""폰트 글리프 커버리지 테스트 — 화면에 나가는 문자가 번들 폰트에 전부 있는가.

왜 필요한가
-----------
웹 export 는 시스템 폰트 폴백이 없다(docs/web-export.md). 번들한 neodgm.ttf 에
글리프가 없는 문자를 쓰면 데스크톱 에디터에서는 OS 폰트로 대신 그려져 멀쩡해
보이지만, 배포된 웹 빌드에서는 두부(□)로 나온다. 실제로 두 번 새어 나갔다:
한자 社 8곳, 그리고 기호 10곳(→ ※ ✕ ✓ ⚠ ♪ ✉ ☏ ✎ ❝).

검사 범위는 "플레이어가 보는 문자열"이다:
  - src/**/*.gd 의 큰따옴표 리터럴  (주석 ## 은 제외 — 화면에 안 나간다)
  - src/core/data/*.json 의 모든 문자열 값. 단 _ 로 시작하는 키는 설계 메모라
    렌더되지 않으므로 제외한다(opinion_config 의 _desc 등).

실패하면 어떤 문자가 어디서 쓰였는지 출력한다. 대체 문자는 pipeline/tests 의
후보 목록이 아니라 폰트 cmap 에서 직접 골라야 한다 — 이 스크립트에 --list-symbols
를 주면 폰트가 가진 기호를 뽑아 준다.
"""
from __future__ import annotations

import json
import pathlib
import re
import struct
import sys
import unicodedata

ROOT = pathlib.Path(__file__).resolve().parents[2]
FONT = ROOT / "assets/fonts/neodgm.ttf"
GD_DIRS = [ROOT / "src"]
JSON_DIRS = [ROOT / "src/core/data"]
# 주석 전용 줄(## 또는 #)은 화면에 안 나가므로 문자열 수집에서 뺀다.
COMMENT_RE = re.compile(r"^\s*#")
STR_RE = re.compile(r'"((?:[^"\\]|\\.)*)"')
SKIP_CP = {0x09, 0x0A, 0x0D}


def read_cmap(path: pathlib.Path) -> set[int]:
    """TTF cmap(format 4/12)에서 글리프가 매핑된 코드포인트 집합을 뽑는다."""
    d = path.read_bytes()
    n = struct.unpack(">H", d[4:6])[0]
    off = None
    for i in range(n):
        o = 12 + i * 16
        if d[o:o + 4] == b"cmap":
            off = struct.unpack(">I", d[o + 8:o + 12])[0]
            break
    if off is None:
        raise SystemExit("[font] cmap 테이블 없음")
    best = None
    for i in range(struct.unpack(">H", d[off + 2:off + 4])[0]):
        o = off + 4 + i * 8
        sub = off + struct.unpack(">HHI", d[o:o + 8])[2]
        fmt = struct.unpack(">H", d[sub:sub + 2])[0]
        if fmt == 12:
            best = (12, sub)
            break
        if fmt == 4 and best is None:
            best = (4, sub)
    if best is None:
        raise SystemExit("[font] format 4/12 서브테이블 없음")
    fmt, sub = best
    codes: set[int] = set()
    if fmt == 12:
        for i in range(struct.unpack(">I", d[sub + 12:sub + 16])[0]):
            o = sub + 16 + i * 12
            s, e, _g = struct.unpack(">III", d[o:o + 12])
            codes.update(range(s, e + 1))
        return codes
    segx2 = struct.unpack(">H", d[sub + 6:sub + 8])[0]
    seg = segx2 // 2
    ends = struct.unpack(f">{seg}H", d[sub + 14:sub + 14 + segx2])
    sp = sub + 14 + segx2 + 2
    starts = struct.unpack(f">{seg}H", d[sp:sp + segx2])
    dp = sp + segx2
    deltas = struct.unpack(f">{seg}h", d[dp:dp + segx2])
    rp = dp + segx2
    ranges = struct.unpack(f">{seg}H", d[rp:rp + segx2])
    for i in range(seg):
        for c in range(starts[i], min(ends[i], 0xFFFF) + 1):
            if c == 0xFFFF:
                continue
            if ranges[i] == 0:
                g = (c + deltas[i]) & 0xFFFF
            else:
                gi = rp + i * 2 + ranges[i] + (c - starts[i]) * 2
                if gi + 2 > len(d):
                    continue
                g = struct.unpack(">H", d[gi:gi + 2])[0]
                if g:
                    g = (g + deltas[i]) & 0xFFFF
            if g:
                codes.add(c)
    return codes


def collect() -> dict[str, set[str]]:
    used: dict[str, set[str]] = {}

    def add(ch: str, src: str) -> None:
        if ord(ch) not in SKIP_CP:
            used.setdefault(ch, set()).add(src)

    for base in GD_DIRS:
        for p in sorted(base.rglob("*.gd")):
            rel = p.relative_to(ROOT)
            for ln, line in enumerate(p.read_text(encoding="utf-8").splitlines(), 1):
                if COMMENT_RE.match(line):
                    continue
                for m in STR_RE.finditer(line):
                    for ch in m.group(1):
                        add(ch, f"{rel}:{ln}")

    for base in JSON_DIRS:
        for p in sorted(base.rglob("*.json")):
            rel = str(p.relative_to(ROOT))

            def walk(v: object) -> None:
                if isinstance(v, str):
                    for ch in v:
                        add(ch, rel)
                elif isinstance(v, dict):
                    for k, x in v.items():
                        if isinstance(k, str) and k.startswith("_"):
                            continue  # 설계 메모 — 렌더되지 않는다
                        walk(x)
                elif isinstance(v, list):
                    for x in v:
                        walk(x)

            walk(json.loads(p.read_text(encoding="utf-8")))
    return used


def main() -> int:
    if "--list-symbols" in sys.argv:
        codes = read_cmap(FONT)
        syms = [chr(c) for c in sorted(codes)
                if 0x2000 <= c <= 0x2BFF or 0x00A1 <= c <= 0x00FF or 0x3000 <= c <= 0x303F]
        print("폰트가 가진 기호/문장부호:")
        print("".join(syms))
        return 0

    print("=" * 64)
    print("font coverage — 화면 문자열 ↔ 번들 폰트 글리프 대조")
    print("=" * 64)
    if not FONT.exists():
        print(f"[SKIP] 폰트 없음: {FONT}")
        return 0
    codes = read_cmap(FONT)
    used = collect()
    missing = {ch: src for ch, src in used.items() if ord(ch) not in codes}
    print(f"폰트 글리프 {len(codes)}개 · 화면 문자 {len(used)}종")

    if not missing:
        print("\n결과: 전체 통과 (두부 위험 문자 없음)")
        return 0

    print(f"\n결과: 실패 — 폰트에 없는 문자 {len(missing)}종 (웹에서 □ 로 나온다)\n")
    for ch, src in sorted(missing.items(), key=lambda kv: (-len(kv[1]), kv[0])):
        try:
            name = unicodedata.name(ch)
        except ValueError:
            name = "?"
        s = sorted(src)
        print(f"  {ch!r} U+{ord(ch):04X} {name}")
        print(f"      {', '.join(s[:5])}{' …' if len(s) > 5 else ''}")
    print("\n대체 문자 후보는 --list-symbols 로 확인할 것.")
    return 1


if __name__ == "__main__":
    raise SystemExit(main())
