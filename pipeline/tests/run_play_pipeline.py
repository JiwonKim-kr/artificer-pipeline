#!/usr/bin/env python3
"""play 트랙 파이프라인 테스트 (manifest 검증 · 쓰기 · play_test 러너).

Phase 1 의 run_lore_roundtrip.py 와 같은 스타일(단일 파일·번호 섹션·check 헬퍼).

  [1] manifest 스키마 검증  : valid fixture 통과 / 각 invalid fixture 가
                              의도한 error code 로 검출되는지 확인.
  [2] manifest 쓰기 창구    : 임시 사본에 add/update-status/list 를 실행.
                              중복 ID·잘못된 ID 는 검증 실패로 '쓰이지 않음' 확인.
  [3] play_test 정합성 로직 : run_manifest_integrity 가 파일 누락을 잡고,
                              파일이 존재하면 통과하는지 확인.
  [4] play_test 엔드투엔드   : play_test.py 를 실제 프로젝트에 실행 →
                              임포트 + 스모크 + 매니페스트 정합성 전체 통과.

CLAUDE.md 규칙: 실데이터(pipeline/manifest.json)는 절대 수정하지 않는다.
쓰기 검사는 전부 임시 사본/임시 디렉토리 대상.
"""
from __future__ import annotations

import json
import os
import shutil
import subprocess
import sys
import tempfile
from pathlib import Path

TESTS_DIR = Path(__file__).resolve().parent
REPO_ROOT = TESTS_DIR.parent.parent
SCRIPTS = TESTS_DIR.parent / "scripts"
FX = TESTS_DIR / "fixtures" / "manifest"
SCHEMA = REPO_ROOT / "pipeline" / "schemas" / "asset-manifest.schema.json"

# play_test 모듈을 직접 import (정합성 로직 단위 검증용)
sys.path.insert(0, str(SCRIPTS))
import play_test as play_test_mod  # noqa: E402
import manifest as manifest_mod  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
_failures = 0


def check(label: str, condition: bool) -> None:
    global _failures
    if not condition:
        _failures += 1
    print(f"  [{PASS if condition else FAIL}] {label}")


def _manifest(manifest_path: Path, *args: str) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable, str(SCRIPTS / "manifest.py"),
        "--manifest", str(manifest_path), "--schema", str(SCHEMA), *args,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def _validate_codes(manifest_path: Path) -> tuple[int, list[str]]:
    r = _manifest(manifest_path, "validate", "--json")
    payload = json.loads(r.stdout)
    return r.returncode, [e["code"] for e in payload["errors"]]


def section_schema_validation() -> None:
    print("\n[1] manifest 스키마 검증 (valid / invalid fixtures)")
    rc, codes = _validate_codes(FX / "valid_manifest.json")
    check("valid_manifest 통과 (exit 0)", rc == 0 and not codes)

    expected = {
        "invalid_version": "const",
        "invalid_bad_id": "pattern",
        "invalid_missing_field": "required",
        "invalid_bad_enum": "enum",
        "invalid_id_track_mismatch": "id_track_mismatch",
        "invalid_duplicate_id": "duplicate_id",
    }
    for name, code in expected.items():
        rc, codes = _validate_codes(FX / f"{name}.json")
        check(f"{name} → exit 1", rc == 1)
        check(f"{name} → '{code}' 검출", code in codes)


def section_write_gateway() -> None:
    print("\n[2] manifest 쓰기 창구 (add / update-status / list, 임시 사본)")
    with tempfile.TemporaryDirectory() as td:
        mpath = Path(td) / "manifest.json"
        shutil.copy(FX / "valid_manifest.json", mpath)

        # add 성공
        r = _manifest(
            mpath, "add",
            "--id", "art:enemy/slime_idle", "--track", "art",
            "--spec", "슬라임 대기 스프라이트",
            "--requested-by", "scene_node:scenes/enemy.tscn::Slime/Sprite2D",
        )
        check("add 성공 (exit 0)", r.returncode == 0)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("add 후 entry 3개", len(entries) == 3)
        new = next((e for e in entries if e["id"] == "art:enemy/slime_idle"), None)
        check("추가 entry 존재", new is not None)
        check("추가 entry history=registered 1건",
              new is not None and new["history"][0]["action"] == "registered")

        # 중복 ID → 실패, 파일 미변경
        r = _manifest(
            mpath, "add",
            "--id", "art:enemy/slime_idle", "--track", "art",
            "--spec", "중복", "--requested-by", "scene_node:x.tscn::A",
        )
        check("중복 ID add 실패 (exit 1)", r.returncode == 1)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("중복 add 후에도 entry 3개 (쓰이지 않음)", len(entries) == 3)

        # 잘못된 ID(대문자) → 실패
        r = _manifest(
            mpath, "add",
            "--id", "art:Enemy/Boss", "--track", "art",
            "--spec", "패턴 위반", "--requested-by", "scene_node:x.tscn::A",
        )
        check("잘못된 ID add 실패 (exit 1)", r.returncode == 1)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        check("잘못된 add 후에도 entry 3개 (쓰이지 않음)", len(entries) == 3)

        # update-status
        r = _manifest(
            mpath, "update-status",
            "--id", "art:enemy/slime_idle", "--status", "generated",
            "--file", "assets/art/sprites/enemy/slime_idle.png",
        )
        check("update-status 성공 (exit 0)", r.returncode == 0)
        entries = json.loads(_manifest(mpath, "list", "--json").stdout)
        upd = next((e for e in entries if e["id"] == "art:enemy/slime_idle"), None)
        check("status=generated 반영", upd is not None and upd["status"] == "generated")
        check("history 2건으로 증가", upd is not None and len(upd["history"]) == 2)
        check("file 경로 반영", upd is not None and upd["file"].endswith("slime_idle.png"))

        # list --track 필터
        arts = json.loads(_manifest(mpath, "list", "--track", "art", "--json").stdout)
        check("list --track art 필터 (2건)", len(arts) == 2)

        # 최종 사본이 여전히 유효
        rc, codes = _validate_codes(mpath)
        check("쓰기 이후 사본이 유효", rc == 0 and not codes)


def section_integrity_logic() -> None:
    print("\n[3] play_test 정합성 로직 (파일 누락 검출)")
    schema = manifest_mod.load_schema(str(SCHEMA))
    with tempfile.TemporaryDirectory() as td:
        proj = Path(td)
        mpath = proj / "manifest.json"
        manifest = {
            "version": 1,
            "style_guide": None,
            "entries": [
                {
                    "id": "art:player/player_idle",
                    "track": "art",
                    "status": "placeholder",
                    "spec": "정합성 테스트",
                    "requested_by": [{"kind": "scene_node", "path": "scenes/player.tscn::Player"}],
                    "file": "assets/art/PLACEHOLDER_player_idle.png",
                }
            ],
        }
        mpath.write_text(json.dumps(manifest), encoding="utf-8")

        # 파일 미존재 → 정합성 실패
        st = play_test_mod.run_manifest_integrity(mpath, SCHEMA, proj)
        check("참조 파일 없으면 정합성 FAIL", st.ok is False)
        check("detail 에 missing_file 표시", "missing_file" in st.detail)

        # 파일 생성 후 → 정합성 통과
        fpath = proj / "assets" / "art" / "PLACEHOLDER_player_idle.png"
        fpath.parent.mkdir(parents=True, exist_ok=True)
        fpath.write_bytes(b"\x89PNG placeholder")
        st = play_test_mod.run_manifest_integrity(mpath, SCHEMA, proj)
        check("참조 파일 존재하면 정합성 PASS", st.ok is True)


def section_play_test_e2e() -> None:
    print("\n[4] play_test.py 엔드투엔드 (실제 프로젝트: 임포트 + 스모크 + 정합성)")
    godot = os.environ.get("GODOT_BIN", "godot")
    have_godot = shutil.which(godot) is not None or Path(godot).exists()
    if not have_godot:
        print("  [SKIP] godot 실행 파일을 찾을 수 없어 Godot 스테이지를 건너뜁니다.")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "play_test.py"), "--skip-godot"],
            capture_output=True, text=True,
        )
        check("play_test --skip-godot 통과 (exit 0)", r.returncode == 0)
        return
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "play_test.py")],
        capture_output=True, text=True,
    )
    check("play_test.py 전체 통과 (exit 0)", r.returncode == 0)
    check("출력에 '전체 통과'", "전체 통과" in r.stdout)
    check("임포트 스테이지 PASS", "[PASS] Godot headless 임포트" in r.stdout)
    check("스모크 스테이지 PASS", "[PASS] 스모크 테스트" in r.stdout)


def main() -> int:
    print("=" * 64)
    print("play 파이프라인 테스트: manifest 검증·쓰기 · play_test 러너")
    print("=" * 64)
    section_schema_validation()
    section_write_gateway()
    section_integrity_logic()
    section_play_test_e2e()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
