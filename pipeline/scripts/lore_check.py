#!/usr/bin/env python3
"""lore check — canon 정본에 대한 기계적 정합성 검사 리포터.

이 스크립트는 판단이 필요 없는 '기계적으로 결정 가능한' 결함만 검출한다:
  1) duplicate_glossary_def (error)   : 같은 용어가 glossary에 2회 이상 정의됨
  2) notation_mismatch     (warning)  : glossary 용어가 본문에서 다른 표기로 사용됨
                                        (대소문자/공백/하이픈 변형)
  3) undefined_term        (info)     : 본문에서 **강조**된 후보 용어가 glossary에 없음
  4) orphan_term           (info)     : glossary에 정의됐으나 어느 본문에서도 안 쓰임

의미적 모순(예: 세력 A의 능력 서술이 세계 규칙과 충돌)처럼 판단이 필요한 검사는
이 스크립트가 하지 않는다. 그것은 슬래시 커맨드(Claude)의 몫이다 (HANDOFF §5).

종료 코드:
  0 = error/warning 없음 (info는 통과로 간주)
  1 = error 또는 warning 검출
  2 = 실행 오류 (경로 없음 등)

canon 경로는 --canon 인자로 받는다 (fixture 대상 테스트 가능). stdlib만 사용.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict

# 같은 디렉토리의 lore_index 모듈을 import 가능하게
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
from lore_index import (  # noqa: E402
    CanonIndex,
    load_canon,
    normalize_term,
    default_canon,
)

SEVERITY_ORDER = {"error": 0, "warning": 1, "info": 2}


@dataclass
class Finding:
    code: str
    severity: str      # error | warning | info
    message: str
    file: str
    line: int


# ---------------------------------------------------------------------------
# 개별 검사
# ---------------------------------------------------------------------------
def check_duplicate_glossary(index: CanonIndex) -> list[Finding]:
    findings: list[Finding] = []
    seen: dict[str, tuple[str, int, str]] = {}  # norm -> (surface, line, file)
    for gt in index.glossary_terms:
        key = normalize_term(gt.term)
        if key in seen:
            first_surface, first_line, first_file = seen[key]
            findings.append(
                Finding(
                    code="duplicate_glossary_def",
                    severity="error",
                    message=(
                        f"용어 '{gt.term}' 가 glossary에 중복 정의됨 "
                        f"(최초: {first_file}:{first_line} '{first_surface}')"
                    ),
                    file=gt.file,
                    line=gt.line,
                )
            )
        else:
            seen[key] = (gt.term, gt.line, gt.file)
    return findings


def _term_regex(term: str) -> re.Pattern[str]:
    """용어 표기 변형을 잡는 정규식.

    토큰 사이를 [\\s\\-_]+ 로 허용하고 대소문자 무시.
    양옆은 문자/숫자 경계를 요구해 부분어 오탐을 줄인다.
    """
    tokens = [t for t in re.split(r"[\s\-_]+", term.strip()) if t]
    escaped = [re.escape(t) for t in tokens]
    core = r"[\s\-_]+".join(escaped)
    return re.compile(rf"(?<![\w]){core}(?![\w])", re.IGNORECASE | re.UNICODE)


def check_notation_mismatch(index: CanonIndex) -> list[Finding]:
    findings: list[Finding] = []
    for gt in index.glossary_terms:
        canonical = gt.term
        pattern = _term_regex(canonical)
        for relpath, text in index.body_texts.items():
            for lineno, raw in enumerate(text.splitlines(), start=1):
                for m in pattern.finditer(raw):
                    found = m.group(0)
                    if found != canonical:
                        findings.append(
                            Finding(
                                code="notation_mismatch",
                                severity="warning",
                                message=(
                                    f"'{found}' 는 glossary 표준 표기 '{canonical}' 와 "
                                    f"다릅니다 (표기 통일 필요)"
                                ),
                                file=relpath,
                                line=lineno,
                            )
                        )
    # (found, file, line) 중복 제거
    return _dedupe(findings)


def check_undefined_terms(index: CanonIndex) -> list[Finding]:
    glossary_norms = {normalize_term(gt.term) for gt in index.glossary_terms}
    findings: list[Finding] = []
    reported: set[tuple[str, str, int]] = set()
    for cand in index.candidate_terms:
        key = normalize_term(cand.term)
        if key not in glossary_norms:
            sig = (key, cand.file, cand.line)
            if sig in reported:
                continue
            reported.add(sig)
            findings.append(
                Finding(
                    code="undefined_term",
                    severity="info",
                    message=(
                        f"본문에서 강조된 '{cand.term}' 가 glossary에 없습니다 "
                        f"(용어 등재 후보)"
                    ),
                    file=cand.file,
                    line=cand.line,
                )
            )
    return findings


def check_orphan_terms(index: CanonIndex) -> list[Finding]:
    findings: list[Finding] = []
    for gt in index.glossary_terms:
        pattern = _term_regex(gt.term)
        used = any(pattern.search(text) for text in index.body_texts.values())
        if not used:
            findings.append(
                Finding(
                    code="orphan_term",
                    severity="info",
                    message=(
                        f"용어 '{gt.term}' 가 glossary에만 있고 어느 본문에서도 "
                        f"참조되지 않습니다 (미사용/공백 후보)"
                    ),
                    file=gt.file,
                    line=gt.line,
                )
            )
    return findings


def _dedupe(findings: list[Finding]) -> list[Finding]:
    seen: set[tuple] = set()
    out: list[Finding] = []
    for f in findings:
        sig = (f.code, f.message, f.file, f.line)
        if sig in seen:
            continue
        seen.add(sig)
        out.append(f)
    return out


ALL_CHECKS = [
    check_duplicate_glossary,
    check_notation_mismatch,
    check_undefined_terms,
    check_orphan_terms,
]


def run_checks(index: CanonIndex) -> list[Finding]:
    findings: list[Finding] = []
    for check in ALL_CHECKS:
        findings.extend(check(index))
    findings.sort(key=lambda f: (SEVERITY_ORDER[f.severity], f.file, f.line))
    return findings


# ---------------------------------------------------------------------------
# 리포트 출력
# ---------------------------------------------------------------------------
def render_text_report(index: CanonIndex, findings: list[Finding]) -> str:
    lines: list[str] = []
    lines.append("=" * 64)
    lines.append("lore check — 기계적 정합성 리포트")
    lines.append(f"canon 루트: {index.canon_root}")
    lines.append(
        f"문서 {len(index.files)}개 · glossary 용어 {len(index.glossary_terms)}개 · "
        f"본문 후보 용어 {len(index.candidate_terms)}개"
    )
    lines.append("=" * 64)

    counts = {"error": 0, "warning": 0, "info": 0}
    for f in findings:
        counts[f.severity] += 1

    if not findings:
        lines.append("검출된 항목 없음. (기계적 검사 통과)")
    else:
        for f in findings:
            badge = {"error": "ERROR ", "warning": "WARN  ", "info": "INFO  "}[f.severity]
            lines.append(f"[{badge}] {f.file}:{f.line}  ({f.code})")
            lines.append(f"          {f.message}")

    lines.append("-" * 64)
    lines.append(
        f"요약: error {counts['error']} · warning {counts['warning']} · info {counts['info']}"
    )
    lines.append(
        "참고: 의미적 모순(설정 충돌) 검사는 이 리포트에 포함되지 않습니다. "
        "슬래시 커맨드(/lore-check)의 Claude 판단 단계에서 별도로 수행하세요."
    )
    return "\n".join(lines)


def _cmd(args: argparse.Namespace) -> int:
    index = load_canon(args.canon, args.glossary_name)
    findings = run_checks(index)
    if args.json:
        payload = {
            "canon_root": index.canon_root,
            "files": index.files,
            "findings": [asdict(f) for f in findings],
            "summary": {
                "error": sum(1 for f in findings if f.severity == "error"),
                "warning": sum(1 for f in findings if f.severity == "warning"),
                "info": sum(1 for f in findings if f.severity == "info"),
            },
        }
        print(json.dumps(payload, ensure_ascii=False, indent=2))
    else:
        print(render_text_report(index, findings))

    blocking = sum(1 for f in findings if f.severity in ("error", "warning"))
    return 1 if blocking else 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="lore_check.py",
        description="canon 정본 기계적 정합성 검사 리포터",
    )
    p.add_argument(
        "--canon",
        default=default_canon(),
        help="canon 문서 루트 (기본: <repo>/lore/canon). fixture 테스트 시 fixture 경로 지정.",
    )
    p.add_argument("--glossary-name", default="glossary.md", help="용어집 파일명")
    p.add_argument("--json", action="store_true", help="JSON으로 출력")
    p.set_defaults(func=_cmd)
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
