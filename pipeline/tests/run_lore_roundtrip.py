#!/usr/bin/env python3
"""lore 트랙 왕복 테스트 (init → query → check).

fixture canon 을 대상으로 lore_index / lore_check 의 기계적 계층을 검증한다.

  - init  : lore init 은 Claude 와의 문답으로 canon 을 생성하는 대화형 명령이라
            스크립트로 재현할 수 없다. 여기서는 init 이 만들어낼 산출물의 형태를
            fixture(sample_canon / clean_canon)로 대신한다.
  - query : lore_index.py query 가 관련 섹션/용어를 실제로 반환하는지 확인.
  - check : lore_check.py 가 sample_canon 의 의도적 결함을 검출하고,
            clean_canon 에서는 무결함을 반환하는지 확인.

CLAUDE.md 규칙에 따라 lore/canon 정본은 절대 건드리지 않는다. 오직 fixture 대상.
"""
from __future__ import annotations

import json
import subprocess
import sys
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
SCRIPTS = TESTS_DIR.parent / "scripts"
SAMPLE = TESTS_DIR / "fixtures" / "sample_canon"
CLEAN = TESTS_DIR / "fixtures" / "clean_canon"

PASS = "PASS"
FAIL = "FAIL"
_failures = 0


def _run(script: str, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = [sys.executable, str(SCRIPTS / script), *args]
    return subprocess.run(cmd, capture_output=True, text=True)


def check(label: str, condition: bool) -> None:
    global _failures
    status = PASS if condition else FAIL
    if not condition:
        _failures += 1
    print(f"  [{status}] {label}")


def main() -> int:
    print("=" * 64)
    print("lore 왕복 테스트: init(fixture) → query → check")
    print("=" * 64)

    # --- init 단계 (fixture 로 대체) --------------------------------------
    print("\n[1] init — 산출물 형태를 fixture 로 대체")
    for name, path in (("sample_canon", SAMPLE), ("clean_canon", CLEAN)):
        docs = sorted(p.name for p in path.glob("*.md"))
        print(f"  {name}: {docs}")
        check(f"{name} 에 glossary.md 존재", "glossary.md" in docs)
        check(f"{name} 에 world.md 존재", "world.md" in docs)

    # --- query 단계 -------------------------------------------------------
    print("\n[2] query — 'Aether' 검색 (sample_canon)")
    r = _run("lore_index.py", "--canon", str(SAMPLE), "query", "Aether", "--json")
    check("query 종료코드 0", r.returncode == 0)
    hits = json.loads(r.stdout) if r.stdout.strip() else []
    check("query 결과 1건 이상", len(hits) >= 1)
    check(
        "Aether Crystal 용어가 결과에 포함",
        any(h["kind"] == "glossary" and h["title"] == "Aether Crystal" for h in hits),
    )

    # --- check 단계 (dirty) ----------------------------------------------
    print("\n[3] check — sample_canon (의도적 결함 검출 기대)")
    r = _run("lore_check.py", "--canon", str(SAMPLE), "--json")
    check("check 종료코드 1 (결함 있음)", r.returncode == 1)
    payload = json.loads(r.stdout)
    codes = [f["code"] for f in payload["findings"]]
    check("duplicate_glossary_def 검출 (Rift Walker 중복)", "duplicate_glossary_def" in codes)
    check("notation_mismatch 검출 (Aether crystal 표기 불일치)", "notation_mismatch" in codes)
    check("undefined_term 검출 (Chronomancer 미등재)", "undefined_term" in codes)
    check("orphan_term 검출 (Umbral Sigil 미사용)", "orphan_term" in codes)
    check("notation_mismatch 2건 (대소문자 + 하이픈)", codes.count("notation_mismatch") == 2)

    # --- check 단계 (clean) ----------------------------------------------
    print("\n[4] check — clean_canon (무결함 기대)")
    r = _run("lore_check.py", "--canon", str(CLEAN), "--json")
    check("check 종료코드 0 (무결함)", r.returncode == 0)
    payload = json.loads(r.stdout)
    check("error 0건", payload["summary"]["error"] == 0)
    check("warning 0건", payload["summary"]["warning"] == 0)

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
