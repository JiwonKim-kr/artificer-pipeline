#!/usr/bin/env python3
"""오케스트레이션 파이프라인 테스트 (verify · status · review).

Phase 1~4a 의 run_lore_roundtrip / run_play_pipeline / run_art_pipeline /
run_se_pipeline 와 같은 스타일(단일 파일·번호 섹션·check 헬퍼·PASS/FAIL·종료 코드).

  [1] verify 게이트 (정상 저장소): 실제 저장소에서 게이트 1~5 통과 확인
                                   (godot 있으면 임포트·스모크 포함, 없으면 SKIP).
  [2] verify 게이트 #3 위반 검출  : 저장소를 임시 복제해 의도적 위반을 심고
                                   (잘못된 파일명·미등록 PLACEHOLDER·잘못된 오디오
                                   확장자·씬 루트 불일치·스프라이트 경로) 각각
                                   검출되는지 + 정상 복제본은 게이트 3 통과.
  [3] status.py                   : JSON 키 구조 + 비밀값 마스킹(존재 여부만) 확인.
  [4] review.py 왕복 (임시 복제본): 에셋 generated→approve/reject(피드백),
                                   spec draft→approve, placeholder approve 거부.
                                   원본 저장소 불변 확인.
  [5] verify --full 재귀 가드      : 중첩 --full 이 러너 재실행을 생략하는지 +
                                   discover_runners 목록 확인 (무한루프 방지).
  [6] 회귀                        : 기존 러너 4종 통과 유지
                                   (verify --full 안에서 호출되면 중복 실행 생략).

CLAUDE.md 규칙: 실데이터(assets/, scenes/, pipeline/manifest.json, src/core/,
lore/canon/, docs/specs/)는 절대 수정하지 않는다. 쓰기 검사는 전부 임시 복제본 대상.
stdlib 만 사용 (Python 3.14).
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

sys.path.insert(0, str(SCRIPTS))
import verify as verify_mod  # noqa: E402

PASS = "PASS"
FAIL = "FAIL"
_failures = 0

# verify --full 안에서 호출되었는지 (중복 실행/재귀 방지)
UNDER_FULL = os.environ.get(verify_mod.IN_FULL_ENV) == "1"


def check(label: str, condition: bool) -> None:
    global _failures
    if not condition:
        _failures += 1
    print(f"  [{PASS if condition else FAIL}] {label}")


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    # encoding 고정: Windows 에서 자식 cp949 출력 ↔ 부모 utf-8 디코드가 어긋나면
    # 리더 스레드가 죽어 stdout/stderr 가 None 이 된다.
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def _have_godot() -> bool:
    godot = os.environ.get("GODOT_BIN", "godot")
    return shutil.which(godot) is not None or Path(godot).exists()


def _clone_repo(dst: Path) -> None:
    shutil.copytree(
        REPO_ROOT, dst,
        ignore=shutil.ignore_patterns(
            ".git", ".godot", "__pycache__", "*.pyc", "export", "node_modules"),
    )


def _verify(project: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(SCRIPTS / "verify.py"),
                 "--project", str(project), *extra])


def _manifest(mpath: Path, spath: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(SCRIPTS / "manifest.py"),
                 "--manifest", str(mpath), "--schema", str(spath), *args])


def _review(project: Path, *args: str) -> subprocess.CompletedProcess[str]:
    return _run([sys.executable, str(SCRIPTS / "review.py"),
                 "--project", str(project), *args])


def _entry(mpath: Path, spath: Path, eid: str) -> dict:
    r = _manifest(mpath, spath, "list", "--json")
    return next((e for e in json.loads(r.stdout) if e["id"] == eid), {})


# ---------------------------------------------------------------------------
# [1] verify 게이트 (정상 저장소)
# ---------------------------------------------------------------------------
def section_verify_repo() -> None:
    print("\n[1] verify 게이트 — 정상 저장소 (게이트 1~5)")
    extra = () if _have_godot() else ("--skip-godot",)
    if not _have_godot():
        print("  [i] godot 없음 — 게이트 1·2 는 --skip-godot 로 SKIP")
    r = _verify(REPO_ROOT, *extra)
    check("verify 종료 0 (전체 통과)", r.returncode == 0)
    check("결과 '전체 통과' 출력", "전체 통과" in r.stdout)
    check("게이트 #3 PASS", "[PASS] 게이트 #3" in r.stdout)
    check("게이트 #4 PASS", "[PASS] 게이트 #4" in r.stdout)
    # 게이트 5 는 저장소의 canon 상태에 따라 SKIP(미초기화) 또는 PASS(정합)다.
    # 테스트가 canon 유무를 하드코딩 가정하면 안 된다 — 게임 콘텐츠가 canon 을
    # 채우면 PASS, 파이프라인 정본만 있으면 SKIP. 어느 쪽이든 FAIL 이 아니어야 한다.
    g5_skip = "[SKIP] 게이트 #5" in r.stdout
    g5_pass = "[PASS] 게이트 #5" in r.stdout
    check("게이트 #5 통과 (SKIP 또는 PASS, FAIL 아님)", g5_skip or g5_pass)
    if g5_skip:
        check("게이트 #5 SKIP 시 의미 검사=Claude 안내", "Claude" in r.stdout)
    if _have_godot():
        check("게이트 #1 PASS (임포트)", "[PASS] 게이트 #1" in r.stdout)
        check("게이트 #2 PASS (스모크)", "[PASS] 게이트 #2" in r.stdout)


# ---------------------------------------------------------------------------
# [2] verify 게이트 #3 위반 검출 (임시 복제본)
# ---------------------------------------------------------------------------
def section_gate3_violations() -> None:
    print("\n[2] verify 게이트 #3 — 의도적 위반 검출 (임시 복제본)")
    orig_manifest = (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        _clone_repo(clone)

        # 정상 복제본: 게이트 3 통과 (--skip-godot 로 빠르게)
        r = _verify(clone, "--skip-godot")
        check("정상 복제본 게이트 #3 PASS", "[PASS] 게이트 #3" in r.stdout)

        # 의도적 위반 5종 심기.
        # 카테고리 디렉토리는 게임마다 다르므로 존재를 가정하지 않고 직접 만든다.
        (clone / "src" / "tools" / "BadName.gd").write_text("extends Node\n", encoding="utf-8")
        fixture_dir = clone / "assets" / "art" / "sprites" / "fixture"
        fixture_dir.mkdir(parents=True, exist_ok=True)
        (fixture_dir / "PLACEHOLDER_unregistered.png").write_bytes(b"\x89PNG")
        (clone / "assets" / "audio" / "se" / "bad_sound.mp3").write_bytes(b"x")
        (clone / "assets" / "art" / "sprites" / "loose_sprite.png").write_bytes(b"\x89PNG")
        (clone / "scenes" / "wrong.tscn").write_text(
            '[gd_scene format=3]\n\n[node name="Player" type="Node2D"]\n', encoding="utf-8")

        r = _verify(clone, "--skip-godot")
        check("위반 심은 뒤 verify 종료 1", r.returncode == 1)
        check("게이트 #3 FAIL", "[FAIL] 게이트 #3" in r.stdout)
        out = r.stdout
        check("위반: snake_case 파일명 (BadName.gd)",
              "src/tools/BadName.gd:" in out and "snake_case" in out)
        check("위반: 미등록 PLACEHOLDER",
              "PLACEHOLDER_unregistered.png:" in out and "등록되지 않음" in out)
        check("위반: 잘못된 오디오 확장자 (.mp3)",
              "bad_sound.mp3:" in out and ".ogg 만 허용" in out)
        check("위반: 씬 루트 노드 불일치 (wrong.tscn)",
              "scenes/wrong.tscn:" in out and "루트 노드" in out)
        check("위반: 스프라이트 경로 규약 (loose_sprite.png)",
              "loose_sprite.png:" in out and "2단 경로" in out)
        check("`파일:항목` 형식 리포트", ".gd:파일명이" in out)

        # 매니페스트 id 위반도 게이트 3 이 잡는가 (별도 복제본)
        clone2 = Path(td) / "clone2"
        _clone_repo(clone2)
        m2 = clone2 / "pipeline" / "manifest.json"
        data = json.loads(m2.read_text(encoding="utf-8"))
        # 저장소 매니페스트가 비어 있을 수도 있으므로(게임 착수 전) 위반 entry 를
        # 직접 구성한다. 손상 상황 재현이 목적이라 manifest.py 를 일부러 우회한다.
        data["entries"] = [{
            "id": "art:BadCaps",  # 대문자 → 패턴 위반
            "track": "art",
            "status": "placeholder",
            "spec": "게이트 #3 id 형식 위반 검증용 픽스처",
            "requested_by": [{"kind": "scene_node", "path": "scenes/fixture.tscn::Sprite2D"}],
            "file": None,
            "history": [{"at": "2026-07-30T00:00:00+00:00", "action": "registered"}],
        }]
        m2.write_text(json.dumps(data), encoding="utf-8")
        r = _verify(clone2, "--skip-godot")
        check("위반: 매니페스트 id 형식 (게이트 #3)",
              "id 형식" in r.stdout and "[FAIL] 게이트 #3" in r.stdout)

    # 원본 불변
    check("원본 manifest.json 불변",
          (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8") == orig_manifest)


# ---------------------------------------------------------------------------
# [3] status.py (구조 + 비밀값 마스킹)
# ---------------------------------------------------------------------------
def section_status() -> None:
    print("\n[3] status.py — JSON 구조 + 비밀값 마스킹")
    r = _run([sys.executable, str(SCRIPTS / "status.py"), "--json"])
    check("status --json 종료 0", r.returncode == 0)
    data = json.loads(r.stdout)
    for key in ("manifest", "specs", "lore", "env", "tools", "runners"):
        check(f"JSON 최상위 키 '{key}' 존재", key in data)
    check("manifest.by_status 집계 존재", "by_status" in data["manifest"])
    check("env.keys 에 3개 비밀 키 존재 여부", set(data["env"]["keys"]) ==
          {"SCENARIO_API_KEY", "SCENARIO_API_SECRET", "ELEVENLABS_API_KEY"})
    check("runners 목록에 자기 자신 포함",
          "run_orchestration_pipeline.py" in data["runners"])

    # 마스킹: 가짜 비밀값이 담긴 .env 를 줘도 값은 절대 출력되지 않는다
    with tempfile.TemporaryDirectory() as td:
        envp = Path(td) / "fake.env"
        envp.write_text("SCENARIO_API_KEY=SUPERSECRET_TOKEN_XYZ\n", encoding="utf-8")
        # PYTHONUTF8 은 남긴다(Windows 에서 자식 cp949 출력 방지).
        clean_env = {"PATH": os.environ.get("PATH", ""), "PYTHONUTF8": "1"}
        r = _run([sys.executable, str(SCRIPTS / "status.py"),
                  "--env", str(envp), "--json"], env=clean_env)
        data = json.loads(r.stdout)
        check("존재하는 키는 True 로 표시", data["env"]["keys"]["SCENARIO_API_KEY"] is True)
        check("비밀 '값'은 출력에 없음 (마스킹)", "SUPERSECRET_TOKEN_XYZ" not in r.stdout)
        # 텍스트 출력도 값 노출 없음
        r = _run([sys.executable, str(SCRIPTS / "status.py"), "--env", str(envp)],
                 env=clean_env)
        check("텍스트 출력도 값 노출 없음",
              "SUPERSECRET_TOKEN_XYZ" not in r.stdout and "설정됨" in r.stdout)


# ---------------------------------------------------------------------------
# [4] review.py 왕복 (임시 복제본)
# ---------------------------------------------------------------------------
def section_review() -> None:
    print("\n[4] review.py — 큐/approve/reject 왕복 (임시 복제본)")
    orig_manifest = (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8")

    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        _clone_repo(clone)
        mpath = clone / "pipeline" / "manifest.json"
        spath = clone / "pipeline" / "schemas" / "asset-manifest.schema.json"

        # 픽스처는 이 테스트가 복제본 안에 직접 만든다. 저장소에 어떤 게임 콘텐츠가
        # 체크인되어 있든(또는 없든) 결과가 달라지지 않아야 한다 — 검증 대상 게임이
        # 교체되어도 파이프라인 자체 테스트는 그대로 통과해야 하기 때문.
        _manifest(mpath, spath, "add", "--id", "se:fixture_review",
                  "--track", "se", "--status", "placeholder",
                  "--spec", "review 왕복 검증용 픽스처 효과음",
                  "--requested-by", "code_event:src/tools/fixture.gd::on_fixture",
                  "--file", "assets/audio/se/PLACEHOLDER_fixture_review.ogg")
        _manifest(mpath, spath, "add", "--id", "art:fixture/review_reject",
                  "--track", "art", "--status", "placeholder",
                  "--spec", "review 반려 검증용 픽스처 스프라이트",
                  "--requested-by", "scene_node:scenes/fixture.tscn::Sprite2D",
                  "--file", "assets/art/sprites/fixture/PLACEHOLDER_review_reject.png")
        _manifest(mpath, spath, "add", "--id", "art:fixture/review_noreason",
                  "--track", "art", "--status", "placeholder",
                  "--spec", "reject --reason 누락 검증용 픽스처 스프라이트",
                  "--requested-by", "scene_node:scenes/fixture.tscn::Sprite2D2",
                  "--file", "assets/art/sprites/fixture/PLACEHOLDER_review_noreason.png")

        # placeholder 상태에서는 approve 거부 (상태 전이 규칙)
        r = _review(clone, "approve", "--id", "se:fixture_review")
        check("placeholder approve 거부 (종료 2)", r.returncode == 2)
        check("거부 사유에 'generated' 안내", "generated" in r.stderr)

        # generated 로 만든 뒤 approve
        _manifest(mpath, spath, "update-status", "--id", "se:fixture_review",
                  "--status", "generated", "--file", "assets/audio/se/fixture_review.ogg")
        r = _review(clone, "list", "--json")
        queue = json.loads(r.stdout)
        check("큐: generated 에셋이 approve 후보에 등장",
              any(a["id"] == "se:fixture_review" for a in queue["assets_pending"]))
        r = _review(clone, "approve", "--id", "se:fixture_review")
        check("approve 종료 0", r.returncode == 0)
        ent = _entry(mpath, spath, "se:fixture_review")
        check("approve 후 status=approved", ent.get("status") == "approved")
        check("history 에 approved 기록",
              "approved" in [h["action"] for h in ent.get("history", [])])

        # 멱등: 이미 approved → 재승인 안내
        r = _review(clone, "approve", "--id", "se:fixture_review")
        check("재approve 멱등 (종료 0)", r.returncode == 0 and "멱등" in r.stdout)

        # reject + 피드백 (generated 대상)
        _manifest(mpath, spath, "update-status", "--id", "art:fixture/review_reject",
                  "--status", "generated")
        r = _review(clone, "reject", "--id", "art:fixture/review_reject",
                    "--reason", "픽셀 정합 불량")
        check("reject 종료 0", r.returncode == 0)
        ent = _entry(mpath, spath, "art:fixture/review_reject")
        check("reject 후 status=rejected", ent.get("status") == "rejected")
        check("history 피드백 기록",
              ent.get("history", [])[-1].get("feedback") == "픽셀 정합 불량")

        # reject 는 --reason 필수
        _manifest(mpath, spath, "update-status", "--id", "art:fixture/review_noreason",
                  "--status", "generated")
        r = _review(clone, "reject", "--id", "art:fixture/review_noreason")
        check("reject --reason 누락 → 종료 2", r.returncode == 2)

        # 갱신 후에도 매니페스트 유효 (단일 창구 통과)
        r = _manifest(mpath, spath, "validate")
        check("반영 후 매니페스트 유효", r.returncode == 0)

        # spec 승인 왕복 (draft → approved, 문서 status 필드)
        spec = clone / "docs" / "specs" / "test_feature.md"
        spec.write_text("# spec: test_feature\n\n- **status**: draft\n\n## goal\n테스트.\n",
                        encoding="utf-8")
        r = _review(clone, "list", "--json")
        queue = json.loads(r.stdout)
        check("큐: draft 스펙이 승인 후보에 등장",
              any(s["id"] == "spec:test_feature" for s in queue["specs_pending"]))
        r = _review(clone, "approve", "--id", "spec:test_feature")
        check("spec approve 종료 0", r.returncode == 0)
        spec_text = spec.read_text(encoding="utf-8")
        check("spec status 필드 approved 로 갱신", "**status**: approved" in spec_text)
        check("spec 승인 노트 추가", "review 승인" in spec_text)

        # spec reject: status draft 유지 + 사유 노트
        spec2 = clone / "docs" / "specs" / "another.md"
        spec2.write_text("# spec: another\n\n- **status**: draft\n", encoding="utf-8")
        r = _review(clone, "reject", "--id", "spec:another", "--reason", "범위 과다")
        check("spec reject 종료 0", r.returncode == 0)
        s2 = spec2.read_text(encoding="utf-8")
        check("spec reject 후 status=draft 유지", "**status**: draft" in s2)
        check("spec reject 사유 노트", "범위 과다" in s2 and "review 반려" in s2)

    check("원본 manifest.json 불변",
          (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8") == orig_manifest)


# ---------------------------------------------------------------------------
# [5] verify --full 재귀 가드
# ---------------------------------------------------------------------------
def section_full_guard() -> None:
    print("\n[5] verify --full — 재귀 가드 + 러너 발견")
    # discover_runners: 기존 러너 + 자기 자신 포함
    runners = [p.name for p in verify_mod.discover_runners(TESTS_DIR)]
    check("discover_runners 에 5종 이상", len(runners) >= 5)
    check("discover_runners 에 run_orchestration_pipeline 포함",
          "run_orchestration_pipeline.py" in runners)

    # 가드 설정 상태로 --full → 러너 재실행 생략(중첩 감지), 게이트만
    env = dict(os.environ)
    env[verify_mod.IN_FULL_ENV] = "1"
    r = _run([sys.executable, str(SCRIPTS / "verify.py"),
              "--skip-godot", "--full"], env=env)
    check("중첩 --full 종료 0", r.returncode == 0)
    check("중첩 감지 → 러너 재실행 생략", "중첩" in r.stdout and "재귀" in r.stdout)
    check("중첩 시 러너 0종 (무한루프 방지)", "러너 0종" in r.stdout)


# ---------------------------------------------------------------------------
# [6] 회귀 (기존 러너 4종 통과 유지)
# ---------------------------------------------------------------------------
def section_regression() -> None:
    print("\n[6] 회귀 — 기존 러너 4종 통과 유지")
    if UNDER_FULL:
        print("  [SKIP] verify --full 안에서 호출됨 — 러너는 verify --full 이 직접 실행하므로 중복 생략")
        return

    for name in ("run_lore_roundtrip.py", "run_play_pipeline.py",
                 "run_art_pipeline.py", "run_se_pipeline.py"):
        r = _run([sys.executable, str(TESTS_DIR / name)])
        check(f"{name} 통과", r.returncode == 0)

    # 기능 수용 테스트(run_acceptance_*.py)는 검증 대상 게임에 종속이므로 여기서
    # 고정 호출하지 않는다. verify --full 이 pipeline/tests/run_*.py 를 자동 발견해
    # 실행하므로, 새 게임의 play build 가 수용 테스트를 만들면 자동으로 포함된다.


def main() -> int:
    print("=" * 64)
    print("오케스트레이션 파이프라인 테스트: verify · status · review")
    print("=" * 64)
    section_verify_repo()
    section_gate3_violations()
    section_status()
    section_review()
    section_full_guard()
    section_regression()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
