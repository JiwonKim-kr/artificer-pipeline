# -*- coding: utf-8 -*-
"""lore_export.py 자기검증 러너 — validate 규칙 전 계열 + apply 왕복(임시 복제본).

실제 저장소 데이터는 읽기(validate)로만 쓰고, apply 는 임시 디렉토리에 최소 구조를
복제해 검증한다(원본 불변). 실행: PYTHONUTF8=1 python pipeline/tests/run_lore_export.py
"""
from __future__ import annotations

import json
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

REPO_ROOT = Path(__file__).resolve().parents[2]
SCRIPT = REPO_ROOT / "pipeline" / "scripts" / "lore_export.py"
CONTENT_REL = "src/core/data/content_slice.json"

_failures = 0


def check(name: str, ok: bool) -> None:
    global _failures
    print(f"  [{'PASS' if ok else 'FAIL'}] {name}")
    if not ok:
        _failures += 1


def _run(args: list[str], cwd: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [sys.executable, str(SCRIPT), *args], cwd=cwd,
        capture_output=True, text=True, encoding="utf-8", errors="replace",
    )


def _cand(rows: list[dict]) -> str:
    """후보 JSON 임시 파일을 만들고 경로를 돌려준다."""
    f = tempfile.NamedTemporaryFile("w", suffix=".json", delete=False, encoding="utf-8")
    json.dump({"comments": rows}, f, ensure_ascii=False)
    f.close()
    return f.name


def _base_row(**over) -> dict:
    row = {"id": "lx_test_ok_01", "seg": "sns_swing", "reaction": "수용",
           "frame": "찬성각", "topic": "생산성", "text": "러너 검증용 임시 댓글 텍스트"}
    row.update(over)
    return row


def section_validate() -> None:
    print("\n[1] validate — 규칙 계열별 통과/차단")
    ok = _run(["validate", "--input", _cand([_base_row()]), "--project", str(REPO_ROOT)], REPO_ROOT)
    check("정상 후보 → 통과(종료 0)", ok.returncode == 0)

    cases = [
        ("미지의 seg 차단", _base_row(seg="ghost_seg"), "미지의 seg"),
        ("미지의 reaction 차단", _base_row(reaction="분노"), "미지의 reaction"),
        ("죽은 조합 차단(apathetic×수용)", _base_row(seg="apathetic", reaction="수용"), "죽은 조합"),
        ("죽은 조합 차단(swing×시큰둥)", _base_row(reaction="시큰둥"), "죽은 조합"),
        ("canon 밖 topic 차단", _base_row(topic="날씨"), "canon 에 없는 topic"),
        ("미지원 슬롯 차단", _base_row(text="이 {회사명} 좀 보소"), "지원되지 않는 슬롯"),
        ("id 형식 위반 차단", _base_row(id="BadID"), "id 형식 위반"),
        ("빈 text 차단", _base_row(text="  "), "text 비어"),
    ]
    for name, row, needle in cases:
        r = _run(["validate", "--input", _cand([row]), "--project", str(REPO_ROOT)], REPO_ROOT)
        check(name, r.returncode == 1 and needle in r.stdout)

    dup = [_base_row(), _base_row(id="lx_test_ok_02")]  # 같은 text 2건
    r = _run(["validate", "--input", _cand(dup), "--project", str(REPO_ROOT)], REPO_ROOT)
    check("후보 내 text 중복 차단", r.returncode == 1 and "후보 내 중복" in r.stdout)

    existing = json.loads((REPO_ROOT / CONTENT_REL).read_text(encoding="utf-8"))["comments"]
    first = next(c for c in existing if c.get("id"))
    r = _run(["validate", "--input", _cand([_base_row(id=str(first["id"]))]), "--project", str(REPO_ROOT)], REPO_ROOT)
    check("기존 뱅크 id 중복 차단", r.returncode == 1 and "id 중복(기존 뱅크)" in r.stdout)
    r = _run(["validate", "--input", _cand([_base_row(text=str(first["text"]))]), "--project", str(REPO_ROOT)], REPO_ROOT)
    check("기존 뱅크 text 중복 차단", r.returncode == 1 and "기존 뱅크와 동일" in r.stdout)


def section_apply() -> None:
    print("\n[2] apply — 임시 복제본 왕복 (원본 불변)")
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td)
        for rel in [CONTENT_REL, "src/core/data/opinion_config.json",
                    "lore/canon/world.md"]:
            dst = clone / rel
            dst.parent.mkdir(parents=True, exist_ok=True)
            shutil.copy(REPO_ROOT / rel, dst)
        before = json.loads((clone / CONTENT_REL).read_text(encoding="utf-8"))
        n_before = len(before["comments"])

        rows = [_base_row(), _base_row(id="lx_test_ok_02", text="러너 검증용 두 번째 댓글")]
        r = _run(["apply", "--input", _cand(rows), "--project", str(clone)], REPO_ROOT)
        check("apply 종료 0", r.returncode == 0)
        after_text = (clone / CONTENT_REL).read_text(encoding="utf-8")
        try:
            after = json.loads(after_text)
            check("병합 후 JSON 재파싱 성공", True)
        except json.JSONDecodeError:
            check("병합 후 JSON 재파싱 성공", False)
            return
        check("comments 2건 증가", len(after["comments"]) == n_before + 2)
        check("추가 entry 필드 보존", after["comments"][-1]["id"] == "lx_test_ok_02")
        check("기존 entry 불변", after["comments"][0] == before["comments"][0])
        # 한 줄 스타일 유지: 추가된 줄이 기존처럼 '    { "id": …' 로 시작해야 한다.
        check("한 줄 객체 스타일 유지", '\n    { "id": "lx_test_ok_02"' in after_text)

        r = _run(["report", "--project", str(clone)], REPO_ROOT)
        check("report 종료 0 + 총계 표시", r.returncode == 0 and "총" in r.stdout)

    orig = json.loads((REPO_ROOT / CONTENT_REL).read_text(encoding="utf-8"))
    check("원본 content_slice 불변(러너 id 미존재)",
          not any(str(c.get("id", "")).startswith("lx_test_ok") for c in orig["comments"]))


def main() -> int:
    print("== run_lore_export — lore_export.py 자기검증 ==")
    # 이 러너는 게임 콘텐츠(content_slice.json)를 대상으로 검증한다. 파이프라인 정본
    # 브랜치(main)에는 게임이 없으므로 그때는 통과가 아니라 SKIP 이다 — 러너가 게임
    # 유무에 따라 깨지면 파이프라인 자체를 검증할 수 없다(CI 러너 견고화 원칙).
    if not (REPO_ROOT / CONTENT_REL).exists():
        print(f"  [SKIP] 게임 콘텐츠 없음: {CONTENT_REL}")
        print("         (파이프라인 전용 브랜치 — lore export 대상이 존재하지 않음)")
        print("\n결과: 전체 통과 (SKIP)")
        return 0
    section_validate()
    section_apply()
    print("\n" + ("결과: 전체 통과" if _failures == 0 else f"결과: 실패 {_failures}건"))
    return 0 if _failures == 0 else 1


if __name__ == "__main__":
    sys.exit(main())
