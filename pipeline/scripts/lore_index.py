#!/usr/bin/env python3
"""canon 문서 파싱/색인 헬퍼 (기계적 처리 계층).

이 모듈은 마크다운으로 작성된 lore canon 문서를 읽어:
  - 헤딩 기준 섹션 트리로 분해하고
  - glossary 문서에서 용어 정의를 추출하며
  - 본문 문서에서 후보 용어(**굵게** 강조 span)를 수집하고
  - 키워드로 관련 섹션/용어를 검색(query)한다.

역할 분담 (HANDOFF §5):
  - 이 스크립트 = 기계적 파싱/색인/검색만 담당한다.
  - 자연어 답변 합성과 의미적 판단(모순 여부 등)은
    슬래시 커맨드 프롬프트에서 Claude가 수행한다.

파이프라인 규칙(CLAUDE.md):
  - canon 경로는 항상 인자(--canon)로 받는다. 실제 정본(lore/canon)뿐 아니라
    테스트 fixture 경로도 대상으로 삼을 수 있어야 하기 때문이다.
  - 장르/스타일 의존 로직을 하드코딩하지 않는다. 모든 도메인 지식은
    canon 데이터에만 존재한다.

stdlib만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, field, asdict
from pathlib import Path

# ---------------------------------------------------------------------------
# 정규식 (모듈 전역, 컴파일 1회)
# ---------------------------------------------------------------------------
HEADING_RE = re.compile(r"^(?P<hashes>#{1,6})\s+(?P<title>.+?)\s*#*\s*$")
# glossary 용어 정의 줄:  - **Term** — 설명   /   - **Term**: 설명   /   * **Term** – 설명
GLOSSARY_BULLET_RE = re.compile(
    r"^\s*[-*+]\s*\*\*(?P<term>[^*]+?)\*\*\s*(?:[—:：–\-]\s*(?P<definition>.*))?$"
)
# 본문 강조 후보 용어:  **Term**
BOLD_SPAN_RE = re.compile(r"\*\*(?P<term>[^*\n]+?)\*\*")


def normalize_term(text: str) -> str:
    """표기 변형(대소문자/공백/하이픈/언더스코어)을 흡수한 비교 키."""
    return re.sub(r"[\s\-_]+", " ", text).strip().lower()


# ---------------------------------------------------------------------------
# 데이터 모델
# ---------------------------------------------------------------------------
@dataclass
class Section:
    file: str          # canon 루트 기준 상대 경로
    level: int         # 헤딩 레벨 (1-6)
    title: str
    line: int          # 헤딩이 위치한 줄 (1-based)
    body: str = ""     # 다음 헤딩 전까지의 본문 텍스트


@dataclass
class GlossaryTerm:
    term: str          # 표기 그대로 (canonical surface form)
    definition: str
    file: str
    line: int


@dataclass
class CandidateTerm:
    term: str          # 본문에서 **강조**된 표기
    file: str
    line: int


@dataclass
class CanonIndex:
    canon_root: str
    files: list[str] = field(default_factory=list)
    sections: list[Section] = field(default_factory=list)
    glossary_terms: list[GlossaryTerm] = field(default_factory=list)
    candidate_terms: list[CandidateTerm] = field(default_factory=list)
    # 비-glossary 문서의 원문 (표기 검사/사용 여부 확인용)
    body_texts: dict[str, str] = field(default_factory=dict)

    def to_summary_dict(self) -> dict:
        return {
            "canon_root": self.canon_root,
            "files": self.files,
            "section_count": len(self.sections),
            "glossary_term_count": len(self.glossary_terms),
            "candidate_term_count": len(self.candidate_terms),
            "glossary_terms": [t.term for t in self.glossary_terms],
        }


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------
def is_glossary_file(relpath: str, glossary_name: str) -> bool:
    return os.path.basename(relpath) == glossary_name


def parse_file(text: str, relpath: str) -> tuple[list[Section], list[CandidateTerm]]:
    """단일 마크다운 문서를 섹션 목록 + 후보 용어 목록으로 분해."""
    lines = text.splitlines()
    sections: list[Section] = []
    candidates: list[CandidateTerm] = []
    current: Section | None = None
    body_buf: list[str] = []
    in_code = False

    def flush():
        if current is not None:
            current.body = "\n".join(body_buf).strip()

    for idx, raw in enumerate(lines, start=1):
        # 코드펜스 안의 내용은 헤딩/강조 파싱에서 제외
        if raw.lstrip().startswith("```"):
            in_code = not in_code
            body_buf.append(raw)
            continue
        if not in_code:
            m = HEADING_RE.match(raw)
            if m:
                flush()
                body_buf = []
                current = Section(
                    file=relpath,
                    level=len(m.group("hashes")),
                    title=m.group("title").strip(),
                    line=idx,
                )
                sections.append(current)
                continue
            for bm in BOLD_SPAN_RE.finditer(raw):
                candidates.append(
                    CandidateTerm(term=bm.group("term").strip(), file=relpath, line=idx)
                )
        body_buf.append(raw)

    flush()
    return sections, candidates


def parse_glossary(text: str, relpath: str) -> list[GlossaryTerm]:
    """glossary 문서에서 용어 정의를 추출.

    지원 형식:
      - **Term** — 설명        (bullet + 굵게)
      - **Term**: 설명
      ### Term                 (레벨 3+ 헤딩을 용어로 취급)
    """
    terms: list[GlossaryTerm] = []
    lines = text.splitlines()
    in_code = False
    for idx, raw in enumerate(lines, start=1):
        if raw.lstrip().startswith("```"):
            in_code = not in_code
            continue
        if in_code:
            continue
        bm = GLOSSARY_BULLET_RE.match(raw)
        if bm:
            terms.append(
                GlossaryTerm(
                    term=bm.group("term").strip(),
                    definition=(bm.group("definition") or "").strip(),
                    file=relpath,
                    line=idx,
                )
            )
            continue
        hm = HEADING_RE.match(raw)
        if hm and len(hm.group("hashes")) >= 3:
            terms.append(
                GlossaryTerm(
                    term=hm.group("title").strip(),
                    definition="",
                    file=relpath,
                    line=idx,
                )
            )
    return terms


def load_canon(canon_root: str, glossary_name: str = "glossary.md") -> CanonIndex:
    root = Path(canon_root)
    if not root.exists():
        raise FileNotFoundError(f"canon 경로가 없습니다: {canon_root}")
    if not root.is_dir():
        raise NotADirectoryError(f"canon 경로가 디렉토리가 아닙니다: {canon_root}")

    index = CanonIndex(canon_root=str(root))
    md_files = sorted(p for p in root.rglob("*.md") if p.is_file())
    for path in md_files:
        rel = str(path.relative_to(root))
        text = path.read_text(encoding="utf-8")
        index.files.append(rel)
        sections, candidates = parse_file(text, rel)
        index.sections.extend(sections)
        if is_glossary_file(rel, glossary_name):
            index.glossary_terms.extend(parse_glossary(text, rel))
        else:
            index.candidate_terms.extend(candidates)
            index.body_texts[rel] = text
    return index


# ---------------------------------------------------------------------------
# query (기계적 검색 계층)
# ---------------------------------------------------------------------------
@dataclass
class QueryHit:
    kind: str          # "section" | "glossary"
    file: str
    line: int
    title: str         # 섹션 제목 또는 용어
    score: int
    snippet: str


def _count_ci(haystack: str, needle: str) -> int:
    if not needle:
        return 0
    return haystack.lower().count(needle.lower())


def query_index(index: CanonIndex, query: str, top: int = 5) -> list[QueryHit]:
    tokens = [t for t in re.split(r"\s+", query.strip()) if t]
    if not tokens:
        return []
    hits: list[QueryHit] = []

    for sec in index.sections:
        title_l = sec.title.lower()
        body_l = sec.body.lower()
        score = 0
        for tok in tokens:
            tl = tok.lower()
            score += title_l.count(tl) * 3
            score += body_l.count(tl) * 1
        if score > 0:
            snippet = _make_snippet(sec.body or sec.title, tokens)
            hits.append(
                QueryHit("section", sec.file, sec.line, sec.title, score, snippet)
            )

    for gt in index.glossary_terms:
        blob = f"{gt.term} {gt.definition}"
        score = 0
        for tok in tokens:
            score += _count_ci(gt.term, tok) * 4
            score += _count_ci(gt.definition, tok) * 2
        if score > 0:
            hits.append(
                QueryHit("glossary", gt.file, gt.line, gt.term, score, gt.definition)
            )

    hits.sort(key=lambda h: (-h.score, h.file, h.line))
    return hits[:top]


def _make_snippet(text: str, tokens: list[str], width: int = 120) -> str:
    flat = " ".join(text.split())
    low = flat.lower()
    pos = -1
    for tok in tokens:
        p = low.find(tok.lower())
        if p != -1 and (pos == -1 or p < pos):
            pos = p
    if pos == -1:
        return flat[:width].strip()
    start = max(0, pos - width // 3)
    end = min(len(flat), start + width)
    prefix = "…" if start > 0 else ""
    suffix = "…" if end < len(flat) else ""
    return f"{prefix}{flat[start:end].strip()}{suffix}"


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def default_canon() -> str:
    # pipeline/scripts/lore_index.py -> repo_root/lore/canon
    repo_root = Path(__file__).resolve().parents[2]
    return str(repo_root / "lore" / "canon")


def _cmd_index(args: argparse.Namespace) -> int:
    index = load_canon(args.canon, args.glossary_name)
    if args.json:
        print(json.dumps(index.to_summary_dict(), ensure_ascii=False, indent=2))
        return 0
    print(f"canon 루트: {index.canon_root}")
    print(f"문서 {len(index.files)}개: {', '.join(index.files)}")
    print(f"섹션 {len(index.sections)}개")
    print(f"glossary 용어 {len(index.glossary_terms)}개:")
    for gt in index.glossary_terms:
        print(f"  - {gt.term}  ({gt.file}:{gt.line})")
    print(f"본문 후보 용어(**강조**) {len(index.candidate_terms)}개")
    return 0


def _cmd_query(args: argparse.Namespace) -> int:
    index = load_canon(args.canon, args.glossary_name)
    query = " ".join(args.query)
    hits = query_index(index, query, top=args.top)
    if args.json:
        print(json.dumps([asdict(h) for h in hits], ensure_ascii=False, indent=2))
        return 0
    if not hits:
        print(f"'{query}' 에 대한 canon 매칭 없음.")
        return 0
    print(f"'{query}' 관련 canon 항목 {len(hits)}건:")
    for h in hits:
        tag = "용어" if h.kind == "glossary" else "섹션"
        print(f"\n[{tag}] {h.title}  ({h.file}:{h.line})  score={h.score}")
        if h.snippet:
            print(f"    {h.snippet}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lore_index.py",
        description="canon 문서 파싱/색인/검색 헬퍼 (기계적 처리 계층)",
    )
    p.add_argument(
        "--canon",
        default=default_canon(),
        help="canon 문서 루트 디렉토리 (기본: <repo>/lore/canon). fixture 테스트 시 fixture 경로 지정.",
    )
    p.add_argument(
        "--glossary-name",
        default="glossary.md",
        help="용어집 파일명 (기본: glossary.md)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pi = sub.add_parser("index", help="색인 요약 출력")
    pi.add_argument("--json", action="store_true")
    pi.set_defaults(func=_cmd_index)

    pq = sub.add_parser("query", help="키워드로 관련 섹션/용어 검색")
    pq.add_argument("query", nargs="+", help="검색 키워드")
    pq.add_argument("--top", type=int, default=5, help="상위 N건 (기본 5)")
    pq.add_argument("--json", action="store_true")
    pq.set_defaults(func=_cmd_query)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, NotADirectoryError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
