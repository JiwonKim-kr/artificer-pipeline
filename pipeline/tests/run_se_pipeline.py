#!/usr/bin/env python3
"""se 트랙 파이프라인 테스트 (se_jsfxr · se_post · elevenlabs_client · se_attach).

Phase 1~3 의 run_lore_roundtrip / run_play_pipeline / run_art_pipeline 과 같은
스타일(단일 파일·번호 섹션·check 헬퍼·PASS/FAIL·종료 코드).

  [1] se_jsfxr         : seed+preset/params 고정 → WAV 바이트 재현성,
                         resolved_params 되먹임 재현, --save-params, 인자 오류.
                         ※ node/jsfxr 미비 시 SKIP (graceful).
  [2] se_post          : 실제 ffmpeg 로 2-pass loudnorm → OGG Vorbis 정규화.
                         모노(1ch)·vorbis·-16 LUFS 허용오차 내 **실측** 검증,
                         BGM 프로파일(-14/스테레오) 파라미터화, probe 검증 게이트.
  [3] elevenlabs_client: 키 부재→종료 코드 3 + 안내(크래시 없음), --dry-run 요청
                         구성 정확성(엔드포인트/메서드/바디, 비밀값 마스킹).
                         ※ 라이브 API 호출은 하지 않는다(키 미발급).
  [4] se_attach        : 저장소 전체를 임시 복제해 code_event → 브리지 노드 삽입
                         왕복. 에셋 부재 skip / dry-run 무변경 / 적용 후 tscn·
                         매니페스트 확인 / 멱등 재실행. (godot 있으면 재임포트 +
                         play_test + acceptance 종단 검증.)
  [5] 회귀             : 기존 러너 3종(lore/play/art) 통과 유지.
                         (수용 테스트는 se_attach 의 godot 종단 경로에서 실행.)

CLAUDE.md 규칙: 실데이터(assets/, scenes/, pipeline/manifest.json, src/)는 절대
수정하지 않는다. 모든 쓰기 검사는 임시 사본/임시 디렉토리 대상.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import hashlib
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
import elevenlabs_client as el  # noqa: E402
import env_config as env_mod  # noqa: E402
import se_attach as attach_mod  # noqa: E402
import se_jsfxr as jsfxr_mod  # noqa: E402
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
    return (shutil.which(os.environ.get("FFMPEG_BIN", "ffmpeg")) is not None
            and shutil.which(os.environ.get("FFPROBE_BIN", "ffprobe")) is not None)


def _have_jsfxr() -> bool:
    return not jsfxr_mod.check_runtime()


def _have_elevenlabs_keys() -> bool:
    """실제 ElevenLabs 키가 .env/환경에 있는지 (라이브 검증 가드용)."""
    try:
        env_mod.require(["ELEVENLABS_API_KEY"])
        return True
    except env_mod.MissingKeysError:
        return False


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _run(cmd: list[str], **kw) -> subprocess.CompletedProcess[str]:
    # encoding 고정: Windows 에서 자식 cp949 출력 ↔ 부모 utf-8 디코드가 어긋나면
    # 리더 스레드가 죽어 stdout/stderr 가 None 이 된다.
    return subprocess.run(cmd, capture_output=True, text=True,
                          encoding="utf-8", errors="replace", **kw)


def _jsfxr_render(spec: dict, out: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
        json.dump(spec, f)
        spec_path = f.name
    try:
        return _run([sys.executable, str(SCRIPTS / "se_jsfxr.py"),
                     "render", "--spec", spec_path, "--out", str(out), *extra])
    finally:
        os.unlink(spec_path)


# ---------------------------------------------------------------------------
# [1] se_jsfxr — 재현성
# ---------------------------------------------------------------------------
def section_jsfxr() -> None:
    print("\n[1] se_jsfxr — seed 고정 재현성 (파라미터 JSON → WAV)")
    if not _have_jsfxr():
        print("  [SKIP] node/jsfxr 미비 — `pipeline/scripts/se_node` 에서 npm install 필요")
        return

    r = _run([sys.executable, str(SCRIPTS / "se_jsfxr.py"), "check"])
    check("check → 종료 0 (준비 완료)", r.returncode == 0 and "준비 완료" in r.stdout)
    r = _run([sys.executable, str(SCRIPTS / "se_jsfxr.py"), "presets", "--json"])
    presets = json.loads(r.stdout)
    check("presets 에 표준 프리셋 포함", {"pickupCoin", "jump", "explosion"} <= set(presets))

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        spec = {"seed": 42, "preset": "pickupCoin"}

        # 같은 seed 2회 → 바이트 동일
        r1 = _jsfxr_render(spec, tdp / "a.wav")
        r2 = _jsfxr_render(spec, tdp / "b.wav")
        check("render 종료 0", r1.returncode == 0 and r2.returncode == 0)
        rec1 = json.loads(r1.stdout)
        rec2 = json.loads(r2.stdout)
        check("같은 seed → WAV 바이트 동일 (sha256)",
              _sha256(tdp / "a.wav") == _sha256(tdp / "b.wav"))
        check("렌더 기록 sha256 일치·실파일 일치",
              rec1["sha256"] == rec2["sha256"] == _sha256(tdp / "a.wav"))
        check("WAV 헤더(RIFF)", (tdp / "a.wav").read_bytes()[:4] == b"RIFF")

        # 다른 seed → 다른 결과
        r3 = _jsfxr_render({"seed": 43, "preset": "pickupCoin"}, tdp / "c.wav")
        check("다른 seed → 다른 WAV", r3.returncode == 0
              and _sha256(tdp / "c.wav") != _sha256(tdp / "a.wav"))

        # resolved_params 되먹임 → 동일 WAV (파라미터 JSON 재현 계약)
        rt_spec = {"seed": rec1["seed"], "params": rec1["resolved_params"]}
        r4 = _jsfxr_render(rt_spec, tdp / "rt.wav")
        check("resolved_params 되먹임 → 동일 WAV",
              r4.returncode == 0 and _sha256(tdp / "rt.wav") == _sha256(tdp / "a.wav"))

        # --save-params 재현 spec 저장 → 그 파일로 재렌더해도 동일
        r5 = _jsfxr_render(spec, tdp / "d.wav", "--save-params", str(tdp / "repro.json"))
        check("--save-params 저장", r5.returncode == 0 and (tdp / "repro.json").exists())
        r6 = _run([sys.executable, str(SCRIPTS / "se_jsfxr.py"), "render",
                   "--spec", str(tdp / "repro.json"), "--out", str(tdp / "e.wav")])
        check("저장된 재현 spec → 동일 WAV",
              r6.returncode == 0 and _sha256(tdp / "e.wav") == _sha256(tdp / "a.wav"))

        if _have_ffmpeg():
            probe = _run([os.environ.get("FFPROBE_BIN", "ffprobe"), "-v", "error",
                          "-show_entries", "stream=codec_name,channels,sample_rate",
                          "-of", "csv=p=0", str(tdp / "a.wav")])
            check("WAV 규격: pcm 모노 44100", probe.stdout.strip() == "pcm_s16le,44100,1")

        # 인자 오류: 알 수 없는 preset / 빈 spec → 종료 2 (크래시 아님)
        r7 = _jsfxr_render({"seed": 1}, tdp / "x.wav", "--preset", "nope")
        check("알 수 없는 preset → 종료 2", r7.returncode == 2 and "Traceback" not in r7.stderr)
        r8 = _jsfxr_render({}, tdp / "y.wav")
        check("preset/params 둘 다 없음 → 종료 2", r8.returncode == 2)


# ---------------------------------------------------------------------------
# [2] se_post — 정규화 (-16 LUFS 실측 검증)
# ---------------------------------------------------------------------------
def _make_sine_wav(dst: Path, *, stereo: bool = True, seconds: float = 1.0) -> bool:
    """검증용 사인 톤 WAV 를 ffmpeg lavfi 로 생성 (크고 명확한 라우드니스)."""
    layout = "stereo" if stereo else "mono"
    r = _run([os.environ.get("FFMPEG_BIN", "ffmpeg"), "-y", "-v", "error",
              "-f", "lavfi", "-i", f"sine=frequency=440:duration={seconds}",
              "-af", f"volume=0.8,aformat=channel_layouts={layout}",
              "-c:a", "pcm_s16le", str(dst)])
    return r.returncode == 0


def section_se_post() -> None:
    print("\n[2] se_post — 2-pass loudnorm → OGG Vorbis (모노 -16 LUFS 실측)")
    if not _have_ffmpeg():
        print("  [SKIP] ffmpeg 없음 — se_post 스테이지 생략")
        return

    r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "encoders"])
    enc = json.loads(r.stdout)
    print(f"  (i) 사용 가능 인코더: {enc}")
    if not any(enc.values()):
        print("  [SKIP] Vorbis 인코더 없음 — normalize 스테이지 생략 "
              "(se_node npm install 또는 libvorbis ffmpeg 필요)")
        return

    with tempfile.TemporaryDirectory() as td:
        tdp = Path(td)
        tone = tdp / "tone.wav"
        check("사인 톤 생성", _make_sine_wav(tone, stereo=True, seconds=1.0))

        # SE 프로파일 (기본값): 스테레오 입력 → 모노 vorbis -16 LUFS
        ogg = tdp / "tone.ogg"
        r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "normalize",
                  "--input", str(tone), "--output", str(ogg), "--json"])
        check("normalize 종료 0 (허용오차 내 자기검증 포함)", r.returncode == 0)
        result = json.loads(r.stdout) if r.returncode == 0 else {"output": {}}
        out = result.get("output", {})
        print(f"  (i) 톤 실측: 입력 {result.get('measured', {}).get('input_i')} LUFS → "
              f"출력 {out.get('input_i')} LUFS (인코더: {result.get('encoder')})")
        check("출력 codec=vorbis", out.get("codec") == "vorbis")
        check("출력 모노(1ch)", out.get("channels") == 1)
        check("출력 44100Hz", out.get("sample_rate") == 44100)
        check("출력 -16 LUFS ± 1.0 (실측)",
              isinstance(out.get("input_i"), (int, float))
              and abs(out["input_i"] - (-16.0)) <= 1.0)

        # probe 검증 게이트: 통과 케이스
        r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "probe",
                  "--input", str(ogg), "--expect-codec", "vorbis",
                  "--expect-channels", "1", "--expect-i", "-16", "--tolerance", "1.0"])
        check("probe 게이트 통과 (vorbis·모노·-16±1)", r.returncode == 0)

        # probe 검증 게이트: 불통과 케이스 (정규화 전 원본은 -16 이 아님)
        r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "probe",
                  "--input", str(tone), "--expect-i", "-16", "--tolerance", "1.0"])
        check("정규화 전 원본 probe → 종료 1 (게이트 작동)", r.returncode == 1)

        # 잘못된 출력 확장자 → 명확한 실패
        r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "normalize",
                  "--input", str(tone), "--output", str(tdp / "x.wav")])
        check("출력이 .ogg 아니면 종료 1", r.returncode == 1 and ".ogg" in r.stderr)

        # BGM 프로파일 파라미터화 (장르 상수 하드코딩 없음 증명): -14 / 스테레오
        bgm = tdp / "bgm.ogg"
        r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "normalize",
                  "--input", str(tone), "--output", str(bgm),
                  "--channels", "2", "--target-i", "-14", "--json"])
        if r.returncode == 0:
            bout = json.loads(r.stdout)["output"]
            print(f"  (i) BGM 프로파일 실측: {bout.get('input_i')} LUFS · "
                  f"{bout.get('channels')}ch")
            check("BGM 프로파일: 스테레오 -14±1 (파라미터로 표현)",
                  bout.get("channels") == 2 and abs(bout["input_i"] - (-14.0)) <= 1.0)
        else:
            check("BGM 프로파일 normalize 종료 0", False)

        # jsfxr 산출물 → 정규화 종단 (백엔드 연결 증명)
        if _have_jsfxr():
            wav = tdp / "step.wav"
            r = _jsfxr_render(
                {"seed": 7, "preset": "pickupCoin",
                 "params": {"p_env_sustain": 0.4, "p_env_decay": 0.5}}, wav)
            check("jsfxr 렌더 종료 0", r.returncode == 0)
            se_ogg = tdp / "step.ogg"
            r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "normalize",
                      "--input", str(wav), "--output", str(se_ogg), "--json"])
            ok = r.returncode == 0
            check("jsfxr WAV → OGG 정규화 종료 0", ok)
            if ok:
                sout = json.loads(r.stdout)["output"]
                print(f"  (i) jsfxr SE 실측: {sout.get('input_i')} LUFS · "
                      f"{sout.get('channels')}ch · {sout.get('codec')}")
                check("jsfxr SE: vorbis 모노 -16±1 (실측)",
                      sout.get("codec") == "vorbis" and sout.get("channels") == 1
                      and abs(sout["input_i"] - (-16.0)) <= 1.0)
        else:
            print("  [SKIP] node/jsfxr 미비 — jsfxr→정규화 종단 생략")


# ---------------------------------------------------------------------------
# [3] elevenlabs_client (라이브 호출 없음)
# ---------------------------------------------------------------------------
def section_elevenlabs() -> None:
    print("\n[3] elevenlabs_client — 키 부재 / dry-run / 엔드포인트 (라이브 호출 없음)")

    # 실 키 감지 → 없으면 라이브 생성 검증을 명시적으로 SKIP (아래는 dry-run 계약만).
    if _have_elevenlabs_keys():
        print("  [i] 실 ElevenLabs 키 감지 — 라이브 API 호출은 비용/불안정으로 CI 기본 미실행")
    else:
        print("  [SKIP] ElevenLabs 키 미발급 — 라이브 생성 검증 생략 (아래 dry-run 계약만 검증)")

    # 엔드포인트 상수 (단일 진실 공급원)
    check("BASE 기본값", el.Api.base() == "https://api.elevenlabs.io/v1")
    check("sound-generation URL", el.Api.sound_generation().endswith("/sound-generation"))
    check("output_format 쿼리", "output_format=mp3_44100_128"
          in el.Api.sound_generation("mp3_44100_128"))
    check("user URL (check-auth)", el.Api.user().endswith("/user"))

    # prepare_* 순수 함수 — 네트워크 없이 요청 구성 검증
    p = el.prepare_sound_generation(
        text="짧은 발소리", api_key="k123secret",
        duration_seconds=1.0, prompt_influence=0.5,
    )
    check("generate: POST + sound-generation 엔드포인트",
          p.method == "POST" and p.url.endswith("/sound-generation"))
    check("generate 바디: text/duration_seconds/prompt_influence",
          p.body == {"text": "짧은 발소리", "duration_seconds": 1.0,
                     "prompt_influence": 0.5})
    check("인증 헤더 방식: xi-api-key", p.headers.get("xi-api-key") == "k123secret")
    p2 = el.prepare_sound_generation(text="t", api_key="k")
    check("선택 인자 생략 시 바디에 미포함(서버 기본값 위임)", p2.body == {"text": "t"})
    raised = False
    try:
        el.prepare_sound_generation(text="   ", api_key="k")
    except ValueError:
        raised = True
    check("빈 text → ValueError", raised)

    # 마스킹: 표시용 dict 에 비밀 노출 없음
    disp = json.dumps(p.to_display())
    check("dry-run 표시에 키 마스킹", "k123secret" not in disp and "k123" in disp)

    # CLI: 키 부재 → 종료 코드 3, 스택트레이스 없음
    # ELEVENLABS_* 제거된 깨끗한 환경. PYTHONUTF8 은 남긴다(Windows cp949 출력 방지).
    clean_env = {"PATH": os.environ.get("PATH", ""), "PYTHONUTF8": "1"}
    with tempfile.TemporaryDirectory() as td:
        r = _run([sys.executable, str(SCRIPTS / "elevenlabs_client.py"),
                  "generate", "--text", "x", "--env", str(Path(td) / "none.env")],
                 env=clean_env)
        check("키 부재 generate → 종료 코드 3", r.returncode == 3)
        check("키 부재 안내에 .env 형식 포함", "ELEVENLABS_API_KEY=" in r.stderr)
        check("키 부재 시 Traceback 없음",
              "Traceback" not in r.stderr and "Traceback" not in r.stdout)
        r = _run([sys.executable, str(SCRIPTS / "elevenlabs_client.py"),
                  "check-auth", "--env", str(Path(td) / "none.env")], env=clean_env)
        check("키 부재 check-auth → 종료 코드 3", r.returncode == 3)

        # dry-run: 키가 있으면 전송 없이 요청 구성만, 종료 0
        envp = Path(td) / "ok.env"
        envp.write_text("ELEVENLABS_API_KEY=demokey123\n", encoding="utf-8")
        r = _run([sys.executable, str(SCRIPTS / "elevenlabs_client.py"),
                  "generate", "--text", "돌바닥 발소리", "--duration", "1.0",
                  "--env", str(envp), "--dry-run"], env=clean_env)
        check("dry-run generate → 종료 0", r.returncode == 0)
        check("dry-run 출력에 엔드포인트", "/sound-generation" in r.stdout)
        check("dry-run 출력에 비밀값 없음", "demokey123" not in r.stdout)
        check("dry-run 출력에 text 바디", "돌바닥 발소리" in r.stdout)
        r = _run([sys.executable, str(SCRIPTS / "elevenlabs_client.py"),
                  "check-auth", "--env", str(envp), "--dry-run"], env=clean_env)
        check("dry-run check-auth → 종료 0 + /user", r.returncode == 0 and "/user" in r.stdout)


# ---------------------------------------------------------------------------
# [4] se_attach (임시 복제본 왕복)
# ---------------------------------------------------------------------------
def _clone_repo(dst: Path) -> None:
    # fixtures 제외: sample_game 은 install() 이 정규 경로로 설치한다(픽스처 원본이
    # 복제본에 남으면 gdignore 밖이 아니어도 불필요한 중복이 된다).
    shutil.copytree(
        REPO_ROOT, dst,
        ignore=shutil.ignore_patterns(
            ".git", ".godot", "__pycache__", "*.pyc", "export", "node_modules", "fixtures"),
    )


def _entry(manifest_path: Path, schema_path: Path, entry_id: str) -> dict:
    r = _run([sys.executable, str(SCRIPTS / "manifest.py"),
              "--manifest", str(manifest_path), "--schema", str(schema_path),
              "list", "--json"])
    entries = json.loads(r.stdout)
    return next((e for e in entries if e["id"] == entry_id), {})


def _run_attach(clone: Path, *extra: str) -> subprocess.CompletedProcess[str]:
    """복제본의 se_attach.py 를 복제본에 묶어 실행. --manifest/--schema 는
    지정하지 않는다 — **--project 에서 유도**되는 것 자체가 검증 대상이다."""
    return _run([sys.executable, str(clone / "pipeline" / "scripts" / "se_attach.py"),
                 "--project", str(clone), *extra])


def _make_real_asset(clone: Path) -> str:
    """실제 에셋(player_step.ogg)을 준비한다. 가능하면 **실제 파이프라인**
    (jsfxr 렌더 → se_post 정규화)으로, 미비 시 플레이스홀더 복사로."""
    real = clone / "assets" / "audio" / "se" / "player_step.ogg"
    if _have_jsfxr() and _have_ffmpeg():
        with tempfile.TemporaryDirectory() as td:
            wav = Path(td) / "step.wav"
            r = _jsfxr_render({"seed": 7, "preset": "pickupCoin",
                               "params": {"p_env_sustain": 0.4}}, wav)
            if r.returncode == 0:
                r = _run([sys.executable, str(SCRIPTS / "se_post.py"), "normalize",
                          "--input", str(wav), "--output", str(real)])
                if r.returncode == 0:
                    return "pipeline(jsfxr→se_post)"
    shutil.copy(
        clone / "assets" / "audio" / "se" / "PLACEHOLDER_player_step.ogg", real)
    return "placeholder 복사"


def section_se_attach() -> None:
    print("\n[4] se_attach — code_event → 브리지 삽입 왕복 (저장소 전체 임시 복제)")

    # 단위: 시그널 유도 (sample_game 픽스처의 player.gd 소스 기준)
    player_src = (sample_game.FIXTURE_DIR / "src" / "core" / "player.gd").read_text(encoding="utf-8")
    sig, why = attach_mod.derive_signal(player_src, "on_step_complete")
    check("derive_signal: on_step_complete → step_completed", sig == "step_completed" and why is None)
    sig, why = attach_mod.derive_signal(player_src, "step_completed")
    check("derive_signal: 시그널명 직접 지정도 허용", sig == "step_completed")
    sig, why = attach_mod.derive_signal(player_src, "nope_method")
    check("derive_signal: 없는 메서드 → 사유 반환", sig is None and why is not None)
    check("node_name_for_entry: se:player_step → SePlayerStep",
          attach_mod.node_name_for_entry("se:player_step") == "SePlayerStep")
    check("node_name_for_entry: se:ui/confirm → SeUiConfirm",
          attach_mod.node_name_for_entry("se:ui/confirm") == "SeUiConfirm")

    orig_fixture_scene = (sample_game.FIXTURE_DIR / "scenes" / "player.tscn").read_text(encoding="utf-8")
    orig_manifest_text = (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8")

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
        eid = "se:player_step"

        check("복제본 경로가 원본과 다름", clone != REPO_ROOT)
        check("브리지 스크립트가 복제본에 존재", (clone / "src" / "tools" / "se_emitter.gd").exists())

        # 실제 에셋 부재 → skip (크래시 아님)
        r = _run_attach(clone, "--skip-import")
        check("실제 에셋 부재 → 종료 0(변경 없음)", r.returncode == 0)
        check("부재 시 SKIP 보고(se gen 안내)", "se gen 먼저" in r.stdout)
        check("부재 시 tscn 미변경", "SePlayerStep" not in scene.read_text(encoding="utf-8"))

        # se gen 산출물 준비 (가능하면 실제 파이프라인 경유)
        how = _make_real_asset(clone)
        print(f"  (i) 실제 에셋 준비 방식: {how}")

        # dry-run: 계획만, 변경 없음
        r = _run_attach(clone, "--dry-run")
        check("dry-run 종료 0", r.returncode == 0)
        check("dry-run ATTACH 계획 표시(시그널 유도 포함)",
              "[ATTACH]" in r.stdout and "step_completed" in r.stdout)
        check("dry-run tscn 미변경", "SePlayerStep" not in scene.read_text(encoding="utf-8"))
        check("dry-run 매니페스트 미변경(placeholder)",
              _entry(mpath, spath, eid).get("status") == "placeholder")

        # 적용 (--skip-import): 브리지 삽입 + 매니페스트 갱신
        r = _run_attach(clone, "--skip-import")
        check("적용 종료 0", r.returncode == 0)
        scene_text = scene.read_text(encoding="utf-8")
        check("tscn: 브리지 노드 삽입", '[node name="SePlayerStep" type="AudioStreamPlayer" parent="."]' in scene_text)
        check("tscn: 브리지 스크립트 참조", "res://src/tools/se_emitter.gd" in scene_text)
        check("tscn: 실제 스트림 경로 연결", "res://assets/audio/se/player_step.ogg" in scene_text)
        check("tscn: 시그널 데이터 주입", 'signal_name = &"step_completed"' in scene_text)
        check("tscn: load_steps 갱신(3→5)", "load_steps=5" in scene_text)
        ent = _entry(mpath, spath, eid)
        check("매니페스트 status=generated", ent.get("status") == "generated")
        check("매니페스트 file=실제 경로", ent.get("file") == "assets/audio/se/player_step.ogg")
        check("history 에 generated 추가",
              "generated" in [h["action"] for h in ent.get("history", [])])

        # 갱신 후에도 매니페스트 유효 (단일 창구 통과)
        r = _run([sys.executable, str(SCRIPTS / "manifest.py"),
                  "--manifest", str(mpath), "--schema", str(spath), "validate"])
        check("갱신 후 매니페스트 유효", r.returncode == 0)

        # 멱등: 재실행해도 중복 삽입 없음
        r = _run_attach(clone, "--id", eid, "--skip-import")
        check("재실행 종료 0 + 멱등 보고", r.returncode == 0 and "이미 연결됨" in r.stdout)
        check("브리지 노드 중복 없음",
              scene.read_text(encoding="utf-8").count('name="SePlayerStep"') == 1)

        # 실데이터 보호: 저장소엔 게임 콘텐츠가 없고(픽스처에만), 픽스처·매니페스트 불변
        check("저장소 scenes/ 에 게임 씬 없음(픽스처에만 존재)",
              not (REPO_ROOT / "scenes" / "player.tscn").exists())
        check("픽스처 player.tscn 불변",
              (sample_game.FIXTURE_DIR / "scenes" / "player.tscn").read_text(encoding="utf-8") == orig_fixture_scene)
        check("원본 manifest.json 불변",
              (REPO_ROOT / "pipeline" / "manifest.json").read_text(encoding="utf-8") == orig_manifest_text)

        # godot 있으면 재임포트 + play_test + acceptance 까지 (강한 종단 증명)
        if _have_godot():
            clone2 = Path(td) / "clone2"
            _clone_repo(clone2)
            sample_game.install(clone2)
            sample_game.register_art(clone2)
            sample_game.register_se(clone2)
            _make_real_asset(clone2)
            r = _run_attach(clone2)
            check("(godot) 재임포트 포함 attach 종료 0",
                  r.returncode == 0 and "재임포트 완료" in r.stdout)
            r = _run([sys.executable, str(SCRIPTS / "play_test.py"),
                      "--project", str(clone2),
                      "--manifest", str(clone2 / "pipeline" / "manifest.json"),
                      "--schema", str(clone2 / "pipeline" / "schemas" / "asset-manifest.schema.json")])
            check("(godot) attach 후 play_test 전체 통과",
                  r.returncode == 0 and "전체 통과" in r.stdout)
            r = _run([sys.executable,
                      str(TESTS_DIR / "fixtures" / "sample_game" / "run_acceptance_player_movement.py"),
                      "--project", str(clone2)])
            check("(godot) attach 후 acceptance(이동 수용 기준) 통과", r.returncode == 0)
        else:
            print("  [SKIP] godot 없음 — 재임포트+play_test+acceptance 종단 검증 생략")


# ---------------------------------------------------------------------------
# [5] 회귀 (기존 러너 4종 통과 유지)
# ---------------------------------------------------------------------------
def section_regression() -> None:
    print("\n[5] 회귀 — 기존 러너 통과 유지")
    r = _run([sys.executable, str(TESTS_DIR / "run_lore_roundtrip.py")])
    check("run_lore_roundtrip.py 통과", r.returncode == 0)

    r = _run([sys.executable, str(TESTS_DIR / "run_play_pipeline.py")])
    check("run_play_pipeline.py 통과", r.returncode == 0)

    # 수용 테스트(sample_game 이동 기준)는 section_se_attach 의 godot 경로에서
    # attach 후 종단으로 이미 실행한다. 러너는 픽스처로 이전되어 저장소 게임에
    # 의존하지 않으므로 여기서 별도 호출하지 않는다.

    r = _run([sys.executable, str(TESTS_DIR / "run_art_pipeline.py")])
    check("run_art_pipeline.py 통과", r.returncode == 0)


def main() -> int:
    print("=" * 64)
    print("se 파이프라인 테스트: se_jsfxr · se_post · elevenlabs_client · se_attach")
    print("=" * 64)
    section_jsfxr()
    section_se_post()
    section_elevenlabs()
    section_se_attach()
    section_regression()

    print("\n" + "=" * 64)
    if _failures:
        print(f"결과: 실패 {_failures}건")
        return 1
    print("결과: 전체 통과")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
