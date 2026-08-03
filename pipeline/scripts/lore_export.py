# -*- coding: utf-8 -*-
"""lore export — 게임 내 텍스트(댓글 뱅크 등) 후보의 기계 검증 + 반영.

계약: pipeline/commands/lore.md §lore export.
역할 분담(HANDOFF §5): 텍스트 '생성'은 Claude(슬래시 커맨드)가, 이 스크립트는
규칙으로 판정 가능한 검증(스키마·정본 topic·중복·슬롯)과 기계적 병합만 담당한다.

사용:
  python lore_export.py validate --input candidates.json [--project .]
  python lore_export.py apply    --input candidates.json [--project .]
  python lore_export.py report   [--project .]            # seg×reaction 커버리지

후보 파일 형식(JSON):
  { "comments": [ { "id": "...", "seg": "...", "reaction": "...",
                    "frame": "찬성각|중립|반대각"|null, "topic": "<canon topic>"|null,
                    "text": "..." }, ... ] }

종료 코드: 0=통과 · 1=검증 실패 · 2=실행 오류.
"""
from __future__ import annotations

import argparse
import json
import re
import sys
from collections import Counter
from pathlib import Path

CONTENT_REL = "src/core/data/content_slice.json"
CONFIG_REL = "src/core/data/opinion_config.json"
CANON_REL = "lore/canon"

# 코어(turn_manager._reaction_for)가 실제로 뽑는 조합만 '살아있는' 셀이다:
#   apathetic -> 항상 "시큰둥" / 그 외 세그먼트 -> "수용" 또는 "역풍".
REACTIONS = {"수용", "역풍", "시큰둥"}
FRAMES = {"찬성각", "중립", "반대각"}
# main.gd COMMENT_SLOTS 가 치환을 지원하는 슬롯. 이 외 {…} 는 리터럴로 노출된다.
ALLOWED_SLOTS = {"키워드", "대상", "수치", "집단"}
ID_RE = re.compile(r"^[a-z][a-z0-9_]{2,63}$")
TEXT_MAX = 120


def _fail(msg: str) -> None:
    print(f"[FAIL] {msg}")


def load_canon_topics(canon_dir: Path) -> list[str]:
    """world.md 의 「이슈 주제(topic) 정본 목록」 문장에서 topic 목록을 파싱한다."""
    world = canon_dir / "world.md"
    if not world.exists():
        raise FileNotFoundError(f"canon 없음: {world}")
    text = world.read_text(encoding="utf-8")
    m = re.search(r"한정한다:\s*([^\n.]+)", text)
    if not m:
        raise ValueError("world.md 에서 topic 정본 목록(『…한정한다: …』)을 찾지 못함")
    topics = [t.strip() for t in m.group(1).split("·") if t.strip()]
    if not topics:
        raise ValueError("topic 정본 목록이 비어 있음")
    return topics


def load_segments(config_path: Path) -> list[str]:
    cfg = json.loads(config_path.read_text(encoding="utf-8"))
    return [str(s["id"]) for s in cfg.get("segments", [])]


def _live_cell(seg: str, reaction: str) -> bool:
    """코어 선택 로직상 실제로 노출될 수 있는 seg×reaction 인가."""
    if seg == "apathetic":
        return reaction == "시큰둥"
    return reaction in ("수용", "역풍")


def validate(candidates: dict, project: Path) -> tuple[list[str], list[str]]:
    """오류 목록과 경고 목록을 돌려준다. 오류가 있으면 반영 불가."""
    errors: list[str] = []
    warnings: list[str] = []

    content_path = project / CONTENT_REL
    content = json.loads(content_path.read_text(encoding="utf-8"))
    existing = content.get("comments", [])
    existing_ids = {str(c.get("id")) for c in existing if c.get("id")}
    existing_texts = {str(c.get("text", "")).strip() for c in existing}

    topics = load_canon_topics(project / CANON_REL)
    segments = set(load_segments(project / CONFIG_REL))

    rows = candidates.get("comments")
    if not isinstance(rows, list) or not rows:
        return (["후보 파일에 comments 배열이 없거나 비어 있음"], [])

    seen_ids: set[str] = set()
    seen_texts: set[str] = set()
    for i, c in enumerate(rows):
        tag = f"comments[{i}]"
        if not isinstance(c, dict):
            errors.append(f"{tag}: 객체가 아님")
            continue
        cid = str(c.get("id", ""))
        seg = str(c.get("seg", ""))
        reaction = str(c.get("reaction", ""))
        frame = c.get("frame")
        topic = c.get("topic")
        text = str(c.get("text", "")).strip()

        if not ID_RE.match(cid):
            errors.append(f"{tag}: id 형식 위반(snake_case ascii): {cid!r}")
        elif cid in existing_ids:
            errors.append(f"{tag}: id 중복(기존 뱅크): {cid}")
        elif cid in seen_ids:
            errors.append(f"{tag}: id 중복(후보 내): {cid}")
        seen_ids.add(cid)

        if seg not in segments:
            errors.append(f"{tag}: 미지의 seg: {seg!r} (허용: {sorted(segments)})")
        if reaction not in REACTIONS:
            errors.append(f"{tag}: 미지의 reaction: {reaction!r} (허용: {sorted(REACTIONS)})")
        elif seg in segments and not _live_cell(seg, reaction):
            errors.append(f"{tag}: 죽은 조합 {seg}×{reaction} — 코어 선택 로직상 노출 불가")
        if frame is not None and str(frame) not in FRAMES:
            errors.append(f"{tag}: 미지의 frame: {frame!r} (허용: {sorted(FRAMES)} 또는 null)")
        if topic is not None and str(topic) not in topics:
            errors.append(f"{tag}: canon 에 없는 topic: {topic!r} (정본: {topics})")

        if not text:
            errors.append(f"{tag}: text 비어 있음")
        elif len(text) > TEXT_MAX:
            errors.append(f"{tag}: text {len(text)}자 — 최대 {TEXT_MAX}자")
        if text in existing_texts:
            errors.append(f"{tag}: text 가 기존 뱅크와 동일: {text[:30]}…")
        elif text in seen_texts:
            errors.append(f"{tag}: text 가 후보 내 중복: {text[:30]}…")
        seen_texts.add(text)

        for slot in re.findall(r"\{([^{}]+)\}", text):
            if slot not in ALLOWED_SLOTS:
                errors.append(f"{tag}: 지원되지 않는 슬롯 {{{slot}}} (허용: {sorted(ALLOWED_SLOTS)})")

    # 기존 뱅크의 죽은 조합은 경고로만 알린다(이 스크립트는 기존 데이터를 지우지 않는다).
    for c in existing:
        seg = str(c.get("seg", ""))
        reaction = str(c.get("reaction", ""))
        if seg in segments and not _live_cell(seg, reaction):
            warnings.append(f"기존 뱅크 죽은 조합: id={c.get('id')} {seg}×{reaction} (노출 불가 — 정리 후보)")
    return errors, warnings


def apply(candidates: dict, project: Path) -> int:
    """검증 통과 후보를 content_slice.json comments 배열 끝에 한 줄 객체로 삽입한다.
    전체 재직렬화(json.dump)는 파일 전체 diff 를 만들므로 하지 않는다 — 텍스트 삽입 후
    반드시 json.loads 재파싱으로 무결성을 확인하고, 실패 시 원본을 건드리지 않는다."""
    content_path = project / CONTENT_REL
    original = content_path.read_text(encoding="utf-8")
    lines = original.splitlines(keepends=True)

    # comments 는 파일 마지막 키다: 끝에서부터 배열 닫힘("  ]")을 찾는다.
    close_idx = -1
    for i in range(len(lines) - 1, -1, -1):
        if lines[i].rstrip("\r\n") == "  ]":
            close_idx = i
            break
    if close_idx <= 0:
        print("[에러] content_slice.json 에서 comments 배열 닫힘('  ]')을 찾지 못함")
        return 2

    # 직전 엔트리에 쉼표 보장.
    prev = close_idx - 1
    while prev > 0 and not lines[prev].strip():
        prev -= 1
    prev_line = lines[prev].rstrip("\r\n")
    if prev_line.endswith("}"):
        lines[prev] = prev_line + ",\n"

    new_lines: list[str] = []
    rows = candidates["comments"]
    for j, c in enumerate(rows):
        obj = {
            "id": c["id"], "seg": c["seg"], "reaction": c["reaction"],
            "frame": c.get("frame"), "topic": c.get("topic"), "text": c["text"],
        }
        line = "    " + json.dumps(obj, ensure_ascii=False, separators=(", ", ": "))
        line = line.replace("{", "{ ", 1)[:-1] + " }"  # 기존 한 줄 스타일 { "id": … } 에 맞춤
        new_lines.append(line + ("\n" if j == len(rows) - 1 else ",\n"))

    merged = "".join(lines[:close_idx]) + "".join(new_lines) + "".join(lines[close_idx:])
    try:
        json.loads(merged)
    except json.JSONDecodeError as e:
        print(f"[에러] 병합 결과가 유효한 JSON 이 아님 — 반영 중단: {e}")
        return 2
    content_path.write_text(merged, encoding="utf-8", newline="\n")
    print(f"[반영] comments {len(rows)}건 추가 → {content_path}")
    return 0


def report(project: Path) -> int:
    content = json.loads((project / CONTENT_REL).read_text(encoding="utf-8"))
    rows = content.get("comments", [])
    cells = Counter((str(c.get("seg")), str(c.get("reaction"))) for c in rows)
    topics = Counter(str(c.get("topic")) for c in rows)
    print(f"댓글 뱅크 총 {len(rows)}건")
    print("seg×reaction:")
    for k in sorted(cells):
        live = "" if _live_cell(k[0], k[1]) else "  ← 죽은 조합(노출 불가)"
        print(f"  {k[0]:>12} × {k[1]}: {cells[k]}{live}")
    print("topic:")
    for t, n in topics.most_common():
        print(f"  {t}: {n}")
    return 0


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description="lore export — 댓글 뱅크 검증/반영")
    parser.add_argument("mode", choices=["validate", "apply", "report"])
    parser.add_argument("--input", help="후보 JSON 파일 (validate/apply)")
    parser.add_argument("--project", default=".", help="저장소 루트 (기본 .)")
    args = parser.parse_args(argv)
    project = Path(args.project).resolve()

    try:
        if args.mode == "report":
            return report(project)
        if not args.input:
            print("[에러] --input 후보 파일이 필요합니다")
            return 2
        candidates = json.loads(Path(args.input).read_text(encoding="utf-8"))
        errors, warnings = validate(candidates, project)
        for w in warnings:
            print(f"[경고] {w}")
        if errors:
            for e in errors:
                _fail(e)
            print(f"검증 실패: 오류 {len(errors)}건")
            return 1
        n = len(candidates.get("comments", []))
        print(f"[검증 통과] 후보 {n}건 (경고 {len(warnings)}건)")
        if args.mode == "apply":
            return apply(candidates, project)
        return 0
    except (OSError, ValueError, KeyError) as e:
        print(f"[에러] {e}")
        return 2


if __name__ == "__main__":
    sys.exit(main())
