#!/usr/bin/env python3
"""art 트랙 파이프라인 테스트 (env_config · scenario_client · art_post · art_reskin).

Phase 1/2 의 run_lore_roundtrip.py / run_play_pipeline.py 와 같은 스타일
(단일 파일·번호 섹션·check 헬퍼·PASS/FAIL·종료 코드).

  [1] env_config      : KEY=value 파싱(주석/공백/따옴표/export), 키 부재→MissingKeysError,
                        환경변수 우선순위, 파일 부재→{}.
  [2] scenario_client : 키 부재→종료 코드 3 + 안내(크래시 없음), --dry-run 요청 구성
                        정확성(엔드포인트/메서드/바디, 비밀값 마스킹), 엔드포인트 상수.
                        ※ 라이브 API 호출은 하지 않는다(키 미발급).
  [3] art_post        : 실제 PNG 를 만들어 resize(nearest)·pack(tile)·probe 실행 검증.
                        투명(alpha) 픽셀 보존을 raw 로 확인.
  [4] art_reskin      : 저장소 전체를 임시 디렉토리에 복제해 placeholder→generated 왕복.
                        dry-run 무변경, 적용 후 tscn 경로·매니페스트 상태 확인,
                        실제 에셋 부재 시 skip. (godot 있으면 재임포트+play_test 까지.)
  [5] 회귀            : 기존 러너(lore roundtrip / play pipeline) 통과 유지.
                        (수용 테스트는 art_reskin 의 godot 종단 경로에서 실행.)

CLAUDE.md 규칙: 실데이터(assets/, scenes/, pipeline/manifest.json, src/)는 절대
수정하지 않는다. 모든 쓰기 검사는 임시 사본/임시 디렉토리 대상.
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
sys.path.insert(0, str(TESTS_DIR / "fixtures" / "sample_game"))
import env_config as env_mod  # noqa: E402
import scenario_client as sc  # noqa: E402
import art_reskin as reskin_mod  # noqa: E402
import placeholder_gen  # noqa: E402
import verify as verify_mod  # noqa: E402
import sample_game  # noqa: E402  (검증 대상 게임에 무관한 테스트 픽스처)

PASS = "PASS"
FAIL = "FAIL"
_failures = 0


def check(label: str, condition: bool) -> None:
    global _failures
    if not condition:
        _failures += 1
    print(f"  [{PASS if condition else FAIL}] {label}")


def _have_godot() -> bool:
    godot = os.environ.get("GODOT_BIN", "godot")
    return shutil.which(godot) is not None or Path(godot).exists()


def _have_ffmpeg() -> bool:
    return shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg")) is not None


def _have_scenario_keys() -> bool:
    """실제 Scenario 키가 .env/환경에 있는지 (라이브 검증 가드용)."""
    try:
        env_mod.require(["SCENARIO_API_KEY", "SCENARIO_API_SECRET"])
        return True
    except env_mod.MissingKeysError:
        return False


# ---------------------------------------------------------------------------
# stdlib PNG 생성기 — 구현은 pipeline/scripts/placeholder_gen.py 로 일원화했다.
# (예전에는 이 파일이 zlib/struct 로 직접 PNG 를 썼다. 동일 로직이 두 곳에
#  존재하지 않도록 정본 구현을 생성기 쪽에 두고 여기서는 얇게 위임한다.)
# ---------------------------------------------------------------------------
def write_png(path: Path, w: int, h: int, pixel) -> None:
    """8-bit RGBA PNG 를 stdlib 만으로 기록. pixel(x,y)->(r,g,b,a)."""
    placeholder_gen.write_rgba_png(path, w, h, pixel)


def _bordered(color: tuple[int, int, int], size: int):
    def px(x: int, y: int):
        if x == 0 or y == 0 or x == size - 1 or y == size - 1:
            return (0, 0, 0, 0)          # 투명 테두리
        return (color[0], color[1], color[2], 255)
    return px


# ---------------------------------------------------------------------------
# [1] env_config
# ---------------------------------------------------------------------------
def section_env_config() -> None:
    print("\n[1] env_config — .env 파싱 / 키 부재 / 우선순위")
    with tempfile.TemporaryDirectory() as td:
        envp = Path(td) / "t.env"
        envp.write_text(
            "# comment\n"
            "export SCENARIO_API_KEY = abc123\n"
            'SCENARIO_API_SECRET="s e cret"  # inline\n'
            "EMPTYVAL=\n"
            "NO EQUALS LINE\n"
            "QUOTED='single q'\n",
            encoding="utf-8",
        )
        vals = env_mod.load_env_file(envp)
        check("export/공백 처리 (SCENARIO_API_KEY=abc123)", vals.get("SCENARIO_API_KEY") == "abc123")
        check("따옴표+인라인주석 (SECRET='s e cret')", vals.get("SCENARIO_API_SECRET") == "s e cret")
        check("단일따옴표 값", vals.get("QUOTED") == "single q")
        check("빈 값 보존", vals.get("EMPTYVAL") == "")
        check("'=' 없는 줄 무시", "NO" not in vals and "BAD" not in vals)

        # 우선순위: 환경변수 > .env
        check(
            "환경변수 우선",
            env_mod.get("SCENARIO_API_KEY", env_values=vals, environ={"SCENARIO_API_KEY": "ENV"}) == "ENV",
        )
        check(
            ".env 값 사용(환경변수 없을 때)",
            env_mod.get("SCENARIO_API_KEY", env_values=vals, environ={}) == "abc123",
        )
        # 요구 키 부재 → MissingKeysError
        raised = False
        try:
            env_mod.require(["SCENARIO_API_KEY", "NOPE"], path=envp, environ={})
        except env_mod.MissingKeysError as exc:
            raised = "NOPE" in exc.keys and "abc" not in exc.render()  # 비밀값 미노출
        check("필수 키 부재 → MissingKeysError(비밀값 미노출)", raised)
        # 파일 부재 → {}
        check("파일 부재 → 빈 dict", env_mod.load_env_file(Path(td) / "none.env") == {})
        # mask
        check("mask 는 앞 4글자만 노출", env_mod.mask("abcdefgh") == "abcd****")


# ---------------------------------------------------------------------------
# [2] scenario_client (라이브 호출 없음)
# ---------------------------------------------------------------------------
def section_scenario_client() -> None:
    print("\n[2] scenario_client — 키 부재/ dry-run / 엔드포인트 (라이브 호출 없음)")

    # 실 키 감지 → 없으면 라이브 생성 검증을 명시적으로 SKIP (아래는 dry-run 계약만).
    if _have_scenario_keys():
        print("  [i] 실 Scenario 키 감지 — 라이브 API 호출은 비용/불안정으로 CI 기본 미실행")
    else:
        print("  [SKIP] Scenario 키 미발급 — 라이브 생성 검증 생략 (아래 dry-run 계약만 검증)")

    # 엔드포인트 상수 (단일 진실 공급원)
    check("BASE 기본값", sc.Api.base() == "https://api.cloud.scenario.com/v1")
    check("generate/custom URL", sc.Api.generate_custom("m1").endswith("/generate/custom/m1"))
    check("generate/txt2img URL", sc.Api.generate_txt2img().endswith("/generate/txt2img"))
    check("jobs URL", sc.Api.job("j1").endswith("/jobs/j1"))
    check("models(projectId) 쿼리", "projectId=p1" in sc.Api.models("p1"))
    check("train PUT 경로", sc.Api.train("m1").endswith("/models/m1/train"))

    # prepare_* 순수 함수 — 네트워크 없이 요청 구성 검증
    auth = sc.build_auth_header("k", "s")
    check("Basic 인증 헤더 형식", auth.startswith("Basic ") and auth != "Basic ")
    g = sc.prepare_generate(model_id="m1", prompt="hi", auth=auth, custom=True, aspect_ratio="1:1")
    check("generate custom: POST + 커스텀 엔드포인트", g.method == "POST" and g.url.endswith("/generate/custom/m1"))
    check("generate custom: 바디 prompt/aspectRatio", g.body["prompt"] == "hi" and g.body["aspectRatio"] == "1:1")
    gb = sc.prepare_generate(model_id="base1", prompt="hi", auth=auth, custom=False)
    check("generate base: txt2img + modelId 바디", gb.url.endswith("/generate/txt2img") and gb.body["modelId"] == "base1")
    tc = sc.prepare_model_create(name="Sty", model_type="flux.2-dev-lora", auth=auth)
    check("train create: POST /models + name/type", tc.method == "POST" and tc.body == {"name": "Sty", "type": "flux.2-dev-lora"})
    ts = sc.prepare_train_start(model_id="m1", auth=auth, seed=7)
    check("train start: PUT + parameters.seed", ts.method == "PUT" and ts.body["parameters"]["seed"] == 7)

    # 마스킹: 표시용 dict 에 비밀 노출 없음
    disp = g.to_display()
    check("dry-run 표시에 Authorization 마스킹", "****" in disp["headers"]["Authorization"] and "k:s" not in json.dumps(disp))

    # CLI: 키 부재 → 종료 코드 3, 스택트레이스 없음
    # SCENARIO_* 제거된 깨끗한 환경. PYTHONUTF8 은 남긴다 — 없으면 Windows 에서 자식이
    # 한글 안내를 cp949 로 내보내고 부모(utf-8 디코드)의 리더 스레드가 UnicodeDecodeError 로
    # 죽어 r.stderr 가 None 이 된다(아래 in 검사에서 TypeError).
    clean_env = {"PATH": os.environ.get("PATH", ""), "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory() as td:
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "scenario_client.py"),
             "generate", "--model-id", "m1", "--prompt", "x", "--env", str(Path(td) / "none.env")],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=clean_env,
        )
        check("키 부재 generate → 종료 코드 3", r.returncode == 3)
        check("키 부재 안내에 .env 형식 포함", "SCENARIO_API_KEY=" in r.stderr)
        check("키 부재 시 Traceback 없음", "Traceback" not in r.stderr and "Traceback" not in r.stdout)

        # dry-run: 키가 있으면 전송 없이 요청 구성만, 종료 0
        envp = Path(td) / "ok.env"
        envp.write_text("SCENARIO_API_KEY=demo\nSCENARIO_API_SECRET=demo\n", encoding="utf-8")
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "scenario_client.py"),
             "generate", "--model-id", "m1", "--prompt", "x", "--env", str(envp), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=clean_env,
        )
        check("dry-run generate → 종료 0", r.returncode == 0)
        check("dry-run 출력에 엔드포인트", "/generate/custom/m1" in r.stdout)
        check("dry-run 출력에 비밀값 없음(demo:demo 미노출)", "demo:demo" not in r.stdout)

        # train dry-run: create→upload→start 3건 구성
        img = Path(td) / "concept.png"
        write_png(img, 8, 8, _bordered((200, 40, 40), 8))
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "scenario_client.py"),
             "train", "--name", "S", "--type", "flux.2-dev-lora", "--image", str(img),
             "--seed", "1", "--env", str(envp), "--dry-run"],
            capture_output=True, text=True, encoding="utf-8", errors="replace", env=clean_env,
        )
        check("dry-run train → 종료 0", r.returncode == 0)
        check("dry-run train 3건(create/upload/start)", "(3)" in r.stdout and "/train" in r.stdout)
        check("dry-run train: base64 마스킹", "마스킹" in r.stdout)


# ---------------------------------------------------------------------------
# [3] art_post (실제 ffmpeg 실행)
# ---------------------------------------------------------------------------
def _probe(path: Path) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "art_post.py"), "probe", "--input", str(path)],
        capture_output=True, text=True,
    )
    return json.loads(r.stdout) if r.returncode == 0 else {}


def section_art_post() -> None:
    print("\n[3] art_post — nearest 리사이즈 · tile 패킹 · 투명 보존 (ffmpeg 실행)")
    if not _have_ffmpeg():
        print("  [SKIP] ffmpeg 없음 — art_post 스테이지 생략")
        return
    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        colors = [(200, 40, 40), (40, 200, 40), (40, 40, 200), (220, 200, 40)]
        frames = []
        for i, c in enumerate(colors):
            fp = tdp / f"frame_{i}.png"
            write_png(fp, 8, 8, _bordered(c, 8))
            frames.append(fp)

        # probe: 원본 투명 확인
        info = _probe(frames[0])
        check("probe 8x8 rgba has_alpha", info.get("width") == 8 and info.get("has_alpha") is True)

        # resize nearest x4 → 32x32, 투명 유지
        out = tdp / "frame0_x4.png"
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "art_post.py"), "resize",
             "--input", str(frames[0]), "--output", str(out), "--scale", "4.0"],
            capture_output=True, text=True,
        )
        check("resize 종료 0", r.returncode == 0)
        ri = _probe(out)
        check("resize 결과 32x32", ri.get("width") == 32 and ri.get("height") == 32)
        check("resize 투명 유지", ri.get("has_alpha") is True)

        # pack tile 4x1 → 32x8, 투명 유지 + 픽셀 검증
        sheet = tdp / "sheet.png"
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "art_post.py"), "pack",
             "--output", str(sheet), "--json", *[str(f) for f in frames]],
            capture_output=True, text=True,
        )
        check("pack 종료 0", r.returncode == 0)
        meta = json.loads(r.stdout) if r.returncode == 0 else {}
        check("pack 메타 4프레임 32x8", meta.get("count") == 4 and meta.get("sheet_width") == 32 and meta.get("sheet_height") == 8)
        si = _probe(sheet)
        check("sheet 투명 유지(pix_fmt rgba)", si.get("has_alpha") is True)

        # 픽셀 수준 투명 보존: 프레임0 코너(투명)·중앙(불투명) 확인
        raw = tdp / "sheet.raw"
        subprocess.run(
            [os.environ.get("FFMPEG_BIN", "ffmpeg"), "-v", "error", "-i", str(sheet),
             "-f", "rawvideo", "-pix_fmt", "rgba", str(raw), "-y"],
            capture_output=True, text=True,
        )
        data = raw.read_bytes()

        def px(x: int, y: int) -> tuple[int, ...]:
            o = (y * 32 + x) * 4
            return tuple(data[o:o + 4])

        check("코너 alpha=0 (투명 보존)", px(0, 0)[3] == 0)
        check("프레임0 중앙 불투명 red", px(3, 3) == (200, 40, 40, 255))
        check("프레임1 중앙 불투명 green", px(11, 3) == (40, 200, 40, 255))

        # 잘못된 입력: 크기 다른 프레임 → 명확한 실패(크래시 아님)
        odd = tdp / "odd.png"
        write_png(odd, 16, 16, _bordered((10, 10, 10), 16))
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "art_post.py"), "pack",
             "--output", str(tdp / "x.png"), str(frames[0]), str(odd)],
            capture_output=True, text=True,
        )
        check("크기 불일치 pack → 종료 1(명확 실패)", r.returncode == 1 and "크기" in r.stderr)


# ---------------------------------------------------------------------------
# [4] art_reskin (임시 복제본)
# ---------------------------------------------------------------------------
def _clone_repo(dst: Path) -> None:
    # fixtures 는 복제하지 않는다: sample_game 은 install() 이 정규 경로로 깔고,
    # 픽스처 안의 player.tscn 이 복제본에 남으면 placeholder 를 참조하는 "다른 씬"으로
    # 오인되어 reskin 이 보수적으로 삭제를 보류한다(테스트 오검출).
    shutil.copytree(
        REPO_ROOT, dst,
        ignore=shutil.ignore_patterns(
            ".git", ".godot", "__pycache__", "*.pyc", "export", "fixtures"),
    )


def _entry(manifest_path: Path, schema_path: Path, entry_id: str) -> dict:
    r = subprocess.run(
        [sys.executable, str(SCRIPTS / "manifest.py"),
         "--manifest", str(manifest_path), "--schema", str(schema_path), "list", "--json"],
        capture_output=True, text=True,
    )
    entries = json.loads(r.stdout)
    return next((e for e in entries if e["id"] == entry_id), {})


def _run_reskin(clone: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """복제본의 art_reskin.py 를 복제본 매니페스트/스키마에 명시적으로 묶어 실행.
    (실데이터 오염 방지: --project/--manifest/--schema 를 전부 복제본으로 고정.)"""
    return subprocess.run(
        [
            sys.executable, str(clone / "pipeline" / "scripts" / "art_reskin.py"),
            "--project", str(clone),
            "--manifest", str(clone / "pipeline" / "manifest.json"),
            "--schema", str(clone / "pipeline" / "schemas" / "asset-manifest.schema.json"),
            *extra,
        ],
        capture_output=True, text=True,
    )


def section_art_reskin() -> None:
    print("\n[4] art_reskin — placeholder→generated 왕복 (저장소 전체 임시 복제)")
    with tempfile.TemporaryDirectory() as td:
        clone = Path(td) / "clone"
        _clone_repo(clone)
        # 검증 대상 게임에 무관한 sample_game 픽스처를 복제본에 설치(저장소엔 게임 없음)
        sample_game.install(clone)
        ra = sample_game.register_art(clone)
        rs = sample_game.register_se(clone)
        check("픽스처 매니페스트 등록 성공", ra.returncode == 0 and rs.returncode == 0)
        mpath = clone / "pipeline" / "manifest.json"
        spath = clone / "pipeline" / "schemas" / "asset-manifest.schema.json"
        scene = clone / "scenes" / "player.tscn"
        real_asset = clone / "assets" / "art" / "sprites" / "player" / "player_idle.png"
        placeholder_asset = clone / "assets" / "art" / "sprites" / "player" / "PLACEHOLDER_player_idle.png"
        eid = "art:player/player_idle"

        # 실데이터 보호: 복제본이지 원본이 아님
        check("복제본 경로가 원본과 다름", clone != REPO_ROOT and str(REPO_ROOT) not in str(mpath.relative_to(td)))

        # 실제 에셋 부재 상태 → reskin 은 skip (크래시 아님)
        r = _run_reskin(clone, "--id", eid, "--skip-import")
        check("실제 에셋 부재 → 종료 0(변경 없음)", r.returncode == 0)
        check("부재 시 SKIP 보고", "art gen 먼저" in r.stdout or "교체할 대상이 없습니다" in r.stdout)
        check("부재 시 tscn 미변경", "PLACEHOLDER_player_idle" in scene.read_text(encoding="utf-8"))

        # art gen 산출물 시뮬레이션: 실제 에셋 생성
        shutil.copy(placeholder_asset, real_asset)

        # 복제본의 placeholder 는 원본에서 온 .import 사이드카를 동반한다(정리 대상 실증).
        placeholder_import = placeholder_asset.parent / (placeholder_asset.name + ".import")
        check("복제본에 placeholder .import 사이드카 존재(정리 전)", placeholder_import.exists())

        # dry-run: 계획만, 변경 없음
        r = _run_reskin(clone, "--id", eid, "--dry-run")
        check("dry-run 종료 0", r.returncode == 0)
        check("dry-run SWAP 계획 표시", "[SWAP]" in r.stdout and "player_idle.png" in r.stdout)
        check("dry-run tscn 미변경", "PLACEHOLDER_player_idle" in scene.read_text(encoding="utf-8"))
        check("dry-run 매니페스트 미변경(placeholder)", _entry(mpath, spath, eid).get("status") == "placeholder")
        check("dry-run: placeholder 파일 유지 + 삭제 예정만 표시",
              placeholder_asset.exists() and "삭제 예정" in r.stdout)

        # 적용 (--skip-import): 씬 교체 + 매니페스트 갱신
        r = _run_reskin(clone, "--id", eid, "--skip-import")
        check("적용 종료 0", r.returncode == 0)
        scene_text = scene.read_text(encoding="utf-8")
        check("tscn: PLACEHOLDER 제거됨", "PLACEHOLDER_player_idle" not in scene_text)
        check("tscn: 실제 경로로 교체됨", "res://assets/art/sprites/player/player_idle.png" in scene_text)
        ent = _entry(mpath, spath, eid)
        check("매니페스트 status=generated", ent.get("status") == "generated")
        check("매니페스트 file=실제 경로", ent.get("file") == "assets/art/sprites/player/player_idle.png")
        check("history 에 generated 추가", "generated" in [h["action"] for h in ent.get("history", [])])

        # 갭 수정 핵심: 교체 성공 후 낡은 placeholder(+.import 사이드카)를 스스로 삭제한다.
        check("적용 후 낡은 placeholder png 삭제됨", not placeholder_asset.exists())
        check("적용 후 낡은 placeholder .import 사이드카 삭제됨", not placeholder_import.exists())
        check("적용 stdout 에 정리 로그", "낡은 placeholder 삭제" in r.stdout)

        # reskin 직후 verify 게이트 #3(undeclared_placeholder)이 통과해야 한다(핵심 회귀).
        violations = verify_mod.check_naming_rules(clone, mpath, spath)
        check(f"reskin 직후 게이트 #3 위반 없음 (위반: {[v.render() for v in violations]})",
              not violations)
        stage4 = verify_mod.play_test_mod.run_manifest_integrity(mpath, spath, clone)
        check("reskin 직후 게이트 #4 정합", stage4.ok)

        # 갱신 후에도 매니페스트 유효 (단일 창구 통과)
        r = subprocess.run(
            [sys.executable, str(SCRIPTS / "manifest.py"),
             "--manifest", str(mpath), "--schema", str(spath), "validate"],
            capture_output=True, text=True,
        )
        check("갱신 후 매니페스트 유효", r.returncode == 0)

        # (c) 보수적 보류: placeholder 를 requested_by 밖의 다른 씬이 아직 참조하면
        #     교체 후에도 삭제하지 않고 보류해야 한다(씬 텍스처 깨짐 방지).
        clone_share = Path(td) / "clone_share"
        _clone_repo(clone_share)
        sample_game.install(clone_share)
        sample_game.register_manifest(clone_share)
        ph_s = clone_share / "assets" / "art" / "sprites" / "player" / "PLACEHOLDER_player_idle.png"
        real_s = clone_share / "assets" / "art" / "sprites" / "player" / "player_idle.png"
        shutil.copy(ph_s, real_s)
        extra_scene = clone_share / "scenes" / "shadow_clone.tscn"
        extra_scene.write_text(
            '[gd_scene format=3]\n\n'
            '[ext_resource type="Texture2D" '
            'path="res://assets/art/sprites/player/PLACEHOLDER_player_idle.png" id="1_x"]\n\n'
            '[node name="ShadowClone" type="Node2D"]\n',
            encoding="utf-8",
        )
        r = _run_reskin(clone_share, "--id", eid, "--skip-import")
        check("(공유) 교체 자체는 종료 0", r.returncode == 0)
        check("(공유) 다른 씬이 참조 → placeholder 삭제 보류",
              "삭제 보류" in r.stdout and ph_s.exists())
        check("(공유) 보류 시 다른 씬의 placeholder 참조 보존",
              "PLACEHOLDER_player_idle" in extra_scene.read_text(encoding="utf-8"))

        # 실데이터 보호: 저장소에는 게임 콘텐츠가 없고(픽스처에만 존재), 픽스처는 불변
        check("저장소 scenes/ 에 게임 씬 없음(픽스처에만 존재)",
              not (REPO_ROOT / "scenes" / "player.tscn").exists())
        check("픽스처 원본 placeholder 불변",
              "PLACEHOLDER_player_idle" in (sample_game.FIXTURE_DIR / "scenes/player.tscn").read_text(encoding="utf-8")
              and (sample_game.FIXTURE_DIR / "assets/art/sprites/player/PLACEHOLDER_player_idle.png").exists())

        # godot 있으면 재임포트 + play_test 까지 (강한 종단 증명)
        if _have_godot():
            clone2 = Path(td) / "clone2"
            _clone_repo(clone2)
            sample_game.install(clone2)
            sample_game.register_manifest(clone2)
            shutil.copy(
                clone2 / "assets/art/sprites/player/PLACEHOLDER_player_idle.png",
                clone2 / "assets/art/sprites/player/player_idle.png",
            )
            r = _run_reskin(clone2, "--id", eid)
            check("(godot) 재임포트 포함 reskin 종료 0", r.returncode == 0 and "재임포트 완료" in r.stdout)
            # play_test 는 복제본 자신의 매니페스트/스키마로 검사해야 한다(실데이터 매니페스트가
            # 아니라). reskin 이 낡은 placeholder 를 지운 뒤이므로, 복제본 매니페스트(player 는
            # generated/실경로, 나머지는 placeholder)와 정합해 게이트 #4 가 통과한다.
            r = subprocess.run(
                [sys.executable, str(SCRIPTS / "play_test.py"), "--project", str(clone2),
                 "--manifest", str(clone2 / "pipeline" / "manifest.json"),
                 "--schema", str(clone2 / "pipeline" / "schemas" / "asset-manifest.schema.json")],
                capture_output=True, text=True,
            )
            check("(godot) reskin 후 play_test 전체 통과", r.returncode == 0 and "전체 통과" in r.stdout)
        else:
            print("  [SKIP] godot 없음 — 재임포트+play_test 종단 검증 생략")


# ---------------------------------------------------------------------------
# [5] 회귀 (기존 러너 통과 유지)
# ---------------------------------------------------------------------------
def section_regression() -> None:
    print("\n[5] 회귀 — 기존 러너 통과 유지")
    r = subprocess.run(
        [sys.executable, str(TESTS_DIR / "run_lore_roundtrip.py")],
        capture_output=True, text=True,
    )
    check("run_lore_roundtrip.py 통과", r.returncode == 0)

    r = subprocess.run(
        [sys.executable, str(TESTS_DIR / "run_play_pipeline.py")],
        capture_output=True, text=True,
    )
    check("run_play_pipeline.py 통과", r.returncode == 0)

    # 수용 러너(sample_game)는 section_art_reskin 의 godot 경로에서 reskin 후
    # play_test 로 종단 검증한다. 픽스처로 이전되어 저장소 게임에 의존하지 않으므로
    # 여기서 별도 호출하지 않는다.


def main() -> int:
    print("=" * 64)
    print("art 파이프라인 테스트: env_config · scenario_client · art_post · art_reskin")
    print("=" * 64)
    section_env_config()
    section_scenario_client()
    section_art_post()
    section_art_reskin()
    section_regression()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
