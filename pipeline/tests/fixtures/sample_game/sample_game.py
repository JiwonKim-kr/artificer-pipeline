"""sample_game 픽스처 설치 헬퍼 (파이프라인 자체 테스트 전용).

배경: art_reskin / se_attach / play_test 러너는 "실제 게임"이 있어야 왕복을
검증할 수 있다. 예전에는 저장소에 체크인된 로그라이크 데모(player.tscn·player.gd·
grid.gd·PLACEHOLDER 에셋)를 그 대상으로 삼았는데, 그러면 검증 대상 게임이 교체될
때마다 파이프라인 자체 테스트가 깨진다. 그래서 그 데모를 이 디렉토리로 옮겨
**테스트가 소유하는 픽스처**로 만들고, 각 테스트는 임시 복제본에 이 픽스처를
설치해 쓴다. 저장소(main)에는 게임 콘텐츠가 없다.

godot 는 `pipeline/tests/fixtures/.gdignore` 때문에 이 트리를 임포트/컴파일하지
않는다(전역 클래스 Player/Grid 오염·불필요한 임포트 방지). 대신 install() 이
복제본의 정규 경로(scenes/·src/core/·assets/)로 복사하면, 복제본에서는 godot 가
정상 임포트한다.

stdlib 만 사용.
"""
from __future__ import annotations

import shutil
import subprocess
import sys
from pathlib import Path

FIXTURE_DIR = Path(__file__).resolve().parent
# fixtures/sample_game -> fixtures -> tests -> pipeline -> repo_root
REPO_ROOT = FIXTURE_DIR.parents[3]
SCRIPTS = REPO_ROOT / "pipeline" / "scripts"

# 복제본 안에서의 대상 경로(파이프라인 규약 경로)
SCENE_REL = "scenes/player.tscn"
PLACEHOLDER_PNG_REL = "assets/art/sprites/player/PLACEHOLDER_player_idle.png"
REAL_PNG_REL = "assets/art/sprites/player/player_idle.png"
PLACEHOLDER_OGG_REL = "assets/audio/se/PLACEHOLDER_player_step.ogg"
REAL_OGG_REL = "assets/audio/se/player_step.ogg"
PLAYER_GD_REL = "src/core/player.gd"
GRID_GD_REL = "src/core/grid.gd"
# 수용 스크립트는 gdignore 밖(복제본의 pipeline/tests/ 직속)에 두어야 godot 가 읽는다.
ACCEPT_SCRIPT_REL = "pipeline/tests/acceptance_player_movement.gd"

ART_ENTRY_ID = "art:player/player_idle"
SE_ENTRY_ID = "se:player_step"
ART_SPEC = "플레이어 대기 스프라이트. 정면 1프레임, 타일 크기에 맞는 정사각"
SE_SPEC = "한 칸 이동 완료 시 발소리 효과음"
ART_REQUESTED_BY = "scene_node:scenes/player.tscn::Player/Sprite2D"
SE_REQUESTED_BY = "code_event:src/core/player.gd::on_step_complete"

# godot 가 --import 시 완전 재생성하는 최소 텍스처 .import 스텁.
# reskin 이 낡은 placeholder 의 .import 사이드카까지 지우는지 검증하려면 존재해야 한다.
_PNG_IMPORT_STUB = (
    "[remap]\n\n"
    'importer="texture"\n'
    'type="CompressedTexture2D"\n\n'
    "[deps]\n\n"
    'source_file="res://{src}"\n'
)


def _copytree_overlay(src: Path, dst: Path) -> None:
    shutil.copytree(src, dst, dirs_exist_ok=True)


def install(clone: Path, *, with_import_sidecar: bool = True) -> None:
    """복제본에 sample_game 을 정규 경로로 설치한다.

    - scenes/ · src/ · assets/ 서브트리를 복제본에 겹쳐 복사
    - 수용 스크립트를 복제본의 pipeline/tests/(gdignore 밖)로 복사
    - placeholder png 의 .import 사이드카를 생성(reskin 정리 검증용)
    매니페스트 등록은 register_manifest() 로 분리(테스트마다 필요 entry 가 다름).
    """
    for sub in ("scenes", "src", "assets"):
        _copytree_overlay(FIXTURE_DIR / sub, clone / sub)

    accept_dst = clone / ACCEPT_SCRIPT_REL
    accept_dst.parent.mkdir(parents=True, exist_ok=True)
    shutil.copy(FIXTURE_DIR / "acceptance_player_movement.gd", accept_dst)

    if with_import_sidecar:
        png = clone / PLACEHOLDER_PNG_REL
        (png.parent / (png.name + ".import")).write_text(
            _PNG_IMPORT_STUB.format(src=PLACEHOLDER_PNG_REL), encoding="utf-8"
        )


def _manifest(clone: Path, *args: str) -> subprocess.CompletedProcess[str]:
    mpath = clone / "pipeline" / "manifest.json"
    spath = clone / "pipeline" / "schemas" / "asset-manifest.schema.json"
    return subprocess.run(
        [sys.executable, str(clone / "pipeline" / "scripts" / "manifest.py"),
         "--manifest", str(mpath), "--schema", str(spath), *args],
        capture_output=True, text=True,
    )


def register_art(clone: Path) -> subprocess.CompletedProcess[str]:
    return _manifest(
        clone, "add", "--id", ART_ENTRY_ID, "--track", "art", "--status", "placeholder",
        "--spec", ART_SPEC, "--requested-by", ART_REQUESTED_BY, "--file", PLACEHOLDER_PNG_REL,
    )


def register_se(clone: Path) -> subprocess.CompletedProcess[str]:
    return _manifest(
        clone, "add", "--id", SE_ENTRY_ID, "--track", "se", "--status", "placeholder",
        "--spec", SE_SPEC, "--requested-by", SE_REQUESTED_BY, "--file", PLACEHOLDER_OGG_REL,
    )


def register_manifest(clone: Path) -> None:
    """art·se 두 entry 를 모두 등록(검증된 단일 창구 manifest.py 경유)."""
    register_art(clone)
    register_se(clone)
