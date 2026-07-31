#!/usr/bin/env python3
"""art reskin — 매니페스트 기반 placeholder→실제 에셋 씬 교체 (로컬 메커니즘).

`art gen` 이 실제 에셋 파일을 규칙 경로(assets/art/...)에 만들어 두면, 이 스크립트가
매니페스트를 읽어 씬(.tscn) 안의 **placeholder 텍스처 경로를 실제 에셋 경로로 일괄
교체**하고, 상태를 `placeholder → generated` 로 갱신한 뒤 Godot 재임포트한다.
(command-catalog `art reskin`, HANDOFF §4 Phase 3)

교체가 **성공적으로 끝난 뒤에만** 낡은 `PLACEHOLDER_*.png`(+ `.import`/`.uid` 사이드카)를
디스크에서 지운다. 교체 후 그 파일은 어떤 매니페스트 entry 도 가리키지 않는 "미등록
placeholder" 가 되어 verify 게이트 #3 을 실패시키기 때문이다(이력은 매니페스트 history
에 남으므로 파일 삭제는 안전). 단, 그 placeholder 를 아직 참조하는 씬 노드나 아직
교체되지 않은 다른 entry 가 하나라도 남아 있으면 삭제하지 않고 **보류**한다(씬 텍스처
깨짐·게이트 #4 미존재 파일 방지). 이 정리는 `--dry-run` 에서는 절대 실행되지 않는다.

매니페스트 쓰기는 **manifest.py 를 통해서만** 한다(단일 창구, CLAUDE.md 원칙 3).
읽기는 manifest 모듈 함수를 재사용한다.

경로 규약: placeholder 는 basename 에 `PLACEHOLDER_` 접두사(conventions.md). 실제
경로는 접두사를 제거한 것. 예)
  assets/art/sprites/player/PLACEHOLDER_player_idle.png
    → assets/art/sprites/player/player_idle.png
(엔트리 `params.generated_file` 가 있으면 그 값을 실제 경로로 우선한다.)

선택 규칙:
  · 기본: `status=placeholder` 엔트리 중 **실제 에셋이 디스크에 존재**하는 것.
    (실제 에셋이 아직 없으면 `art gen` 미실행으로 보고 건너뜀 — 크래시 아님.)
  · `--id` 로 특정 엔트리만, `--status` 로 선택 상태를 바꿀 수 있다.
  · `art gen` 이 이미 실제 경로/generated 로 갱신했어도 placeholder↔실제 경로를
    양방향으로 유도해 동작한다.

안전장치: `--dry-run` 은 아무것도 쓰지 않고 계획만 출력한다. 테스트는 저장소 전체를
임시 디렉토리에 복제해 수행하며 실데이터(scenes/, manifest.json, assets/)를 건드리지
않는다. (CLAUDE.md 금지 규칙)

종료 코드: 0 = 성공(교체 or 교체할 것 없음), 1 = 처리 실패(매니페스트 쓰기/임포트),
          2 = 실행/인자 오류.
"""
from __future__ import annotations

import argparse
import os
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402

PLACEHOLDER_PREFIX = "PLACEHOLDER_"


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_py() -> Path:
    return Path(__file__).resolve().parent / "manifest.py"


# ---------------------------------------------------------------------------
# 경로 유도
# ---------------------------------------------------------------------------
def derive_paths(entry: dict) -> tuple[str, str]:
    """엔트리에서 (placeholder_path, real_path) 를 저장소 상대경로로 유도한다.

    우선순위: params.generated_file 가 있으면 그것이 real_path.
    아니면 file 의 basename 에서 PLACEHOLDER_ 접두사를 제거/부착해 상호 유도.
    """
    file_ref = entry.get("file") or ""
    params = entry.get("params") or {}
    p = Path(file_ref)
    base = p.name
    # as_posix(): 매니페스트/res:// 경로는 OS 무관 슬래시 고정 (Windows str() 은 역슬래시)
    if base.startswith(PLACEHOLDER_PREFIX):
        placeholder = file_ref
        real = p.with_name(base[len(PLACEHOLDER_PREFIX):]).as_posix()
    else:
        real = file_ref
        placeholder = p.with_name(PLACEHOLDER_PREFIX + base).as_posix()
    if params.get("generated_file"):
        real = params["generated_file"]
    return placeholder, real


def _scene_paths(entry: dict) -> list[str]:
    """requested_by 에서 scene_node 의 .tscn 경로(:: 앞부분)만 추출(중복 제거)."""
    out: list[str] = []
    for rb in entry.get("requested_by", []):
        if rb.get("kind") == "scene_node":
            scene = str(rb.get("path", "")).split("::", 1)[0].strip()
            if scene and scene not in out:
                out.append(scene)
    return out


# ---------------------------------------------------------------------------
# 계획 수립
# ---------------------------------------------------------------------------
@dataclass
class SceneEdit:
    scene: str          # 저장소 상대경로
    replacements: int


@dataclass
class EntryPlan:
    entry_id: str
    placeholder_path: str
    real_path: str
    asset_exists: bool
    edits: list[SceneEdit] = field(default_factory=list)
    skip_reason: str | None = None

    @property
    def total_replacements(self) -> int:
        return sum(e.replacements for e in self.edits)


def _count_occurrences(scene_text: str, placeholder_path: str) -> int:
    return scene_text.count(f"res://{placeholder_path}")


def build_plans(
    manifest: dict, project_dir: Path, *, status: str | None, ids: list[str] | None
) -> list[EntryPlan]:
    plans: list[EntryPlan] = []
    id_set = set(ids) if ids else None
    for entry in manifest.get("entries", []):
        entry_id = entry.get("id", "")
        if id_set is not None:
            if entry_id not in id_set:
                continue
        elif status is not None and entry.get("status") != status:
            continue

        placeholder, real = derive_paths(entry)
        real_abs = project_dir / real
        plan = EntryPlan(
            entry_id=entry_id,
            placeholder_path=placeholder,
            real_path=real,
            asset_exists=real_abs.exists(),
        )
        if not plan.asset_exists:
            plan.skip_reason = f"실제 에셋 없음 → {real} (art gen 먼저 실행 필요)"
            plans.append(plan)
            continue
        for scene in _scene_paths(entry):
            scene_abs = project_dir / scene
            if not scene_abs.exists():
                plan.edits.append(SceneEdit(scene, 0))
                continue
            text = scene_abs.read_text(encoding="utf-8")
            plan.edits.append(SceneEdit(scene, _count_occurrences(text, placeholder)))
        if plan.total_replacements == 0:
            plan.skip_reason = "씬에서 placeholder 참조를 찾지 못함(교체 대상 없음)"
        plans.append(plan)
    return plans


# ---------------------------------------------------------------------------
# 적용
# ---------------------------------------------------------------------------
def apply_scene_edits(plan: EntryPlan, project_dir: Path) -> int:
    """계획대로 .tscn 파일의 placeholder 경로를 실제 경로로 교체. 총 교체 수 반환."""
    total = 0
    for edit in plan.edits:
        if edit.replacements == 0:
            continue
        scene_abs = project_dir / edit.scene
        text = scene_abs.read_text(encoding="utf-8")
        new_text = text.replace(
            f"res://{plan.placeholder_path}", f"res://{plan.real_path}"
        )
        scene_abs.write_text(new_text, encoding="utf-8")
        total += edit.replacements
    return total


def update_manifest_status(
    plan: EntryPlan, *, manifest_path: Path, schema_path: Path, new_status: str
) -> subprocess.CompletedProcess[str]:
    """manifest.py 를 통해서만 상태/파일 경로를 갱신한다 (단일 쓰기 창구)."""
    cmd = [
        sys.executable, str(_manifest_py()),
        "--manifest", str(manifest_path), "--schema", str(schema_path),
        "update-status", "--id", plan.entry_id,
        "--status", new_status, "--file", plan.real_path,
    ]
    return subprocess.run(cmd, capture_output=True, text=True)


def run_godot_import(godot: str, project_dir: Path) -> subprocess.CompletedProcess[str]:
    return subprocess.run(
        [godot, "--headless", "--path", str(project_dir), "--import"],
        capture_output=True, text=True, timeout=300,
    )


# ---------------------------------------------------------------------------
# 낡은 placeholder 정리 (교체 성공 후, 보수적 안전장치 포함)
# ---------------------------------------------------------------------------
# 교체가 끝나면 낡은 PLACEHOLDER_*.png 는 어떤 매니페스트 entry 도 가리키지 않는
# "미등록 placeholder" 가 되어 verify 게이트 #3 을 실패시킨다. placeholder 는 교체되면
# 역할이 끝났고 이력은 매니페스트 history 에 남으므로, 교체가 **성공적으로 완료된
# 뒤에만** 낡은 파일을 지운다. 단, 그 placeholder 를 아직 참조하는 곳이 하나라도
# 남아 있으면(다른 씬 노드 / 아직 교체되지 않은 다른 entry) 지우지 않고 보류한다
# (씬 텍스처 깨짐·게이트 #4 미존재 파일 방지). — CLAUDE.md 원칙 3

# 참조 스캔에서 제외할 디렉토리 (Godot·VCS·빌드 부산물)
_SKIP_SCAN_DIRS = {".git", ".godot", "__pycache__", "node_modules", "export", ".import"}
# placeholder 파일과 함께 정리할 Godot 사이드카 확장자 (존재할 때만)
_SIDECAR_SUFFIXES = (".import", ".uid")


def _resolve_ref_path(ref: str, project_dir: Path) -> Path:
    """매니페스트 file/res:// 경로를 절대경로로 정규화 (verify 와 동일 규약)."""
    if ref.startswith("res://"):
        return (project_dir / ref[len("res://"):]).resolve()
    p = Path(ref)
    return p.resolve() if p.is_absolute() else (project_dir / p).resolve()


def _rel_to_project(p: Path, project_dir: Path) -> str:
    # as_posix(): 씬 경로 비교(exclude_scenes)는 매니페스트의 슬래시 표기와 맞춘다.
    try:
        return p.resolve().relative_to(project_dir.resolve()).as_posix()
    except ValueError:
        return p.as_posix()


def _iter_scene_like_files(project_dir: Path):
    """프로젝트 안의 .tscn/.tres 파일을 순회(부산물 디렉토리 제외)."""
    for dirpath, dirnames, filenames in os.walk(project_dir):
        dirnames[:] = [d for d in dirnames if d not in _SKIP_SCAN_DIRS]
        for fn in filenames:
            if fn.endswith((".tscn", ".tres")):
                yield Path(dirpath) / fn


def scene_refs_to_placeholder(
    project_dir: Path, placeholder_path: str, exclude_scenes: set[str]
) -> list[str]:
    """placeholder 를 아직 참조하는 씬/리소스 파일들의 상대경로. 방금 교체한
    씬(exclude_scenes)은 제외한다(교체 후엔 실제 경로를 가리키므로 매치되지 않지만,
    dry-run 시 교체 전 상태를 올바르게 시뮬레이션하기 위해 명시적으로 제외)."""
    needle = f"res://{placeholder_path}"
    hits: list[str] = []
    for f in _iter_scene_like_files(project_dir):
        rel = _rel_to_project(f, project_dir)
        if rel in exclude_scenes:
            continue
        try:
            text = f.read_text(encoding="utf-8")
        except OSError:
            continue
        if needle in text:
            hits.append(rel)
    return hits


def manifest_refs_to_placeholder(
    manifest_path: Path, project_dir: Path, placeholder_path: str, exclude_ids: set[str]
) -> list[str]:
    """placeholder 파일을 file 로 가리키는 다른 entry id 들. 이번에 처리한
    entry(exclude_ids)는 제외한다(교체 후 실제 경로를 가리키므로)."""
    try:
        data = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError):
        return []
    ph_abs = _resolve_ref_path(placeholder_path, project_dir)
    hits: list[str] = []
    for entry in data.get("entries", []):
        if entry.get("id") in exclude_ids:
            continue
        ref = entry.get("file")
        if ref and _resolve_ref_path(ref, project_dir) == ph_abs:
            hits.append(entry.get("id", "?"))
    return hits


@dataclass
class PlaceholderCleanup:
    entry_id: str
    placeholder_path: str
    existed: bool = False
    scene_refs: list[str] = field(default_factory=list)     # 아직 참조하는 씬
    manifest_refs: list[str] = field(default_factory=list)  # 아직 참조하는 entry
    candidates: list[str] = field(default_factory=list)     # 삭제 대상(png+사이드카)
    deleted: list[str] = field(default_factory=list)        # 실제 삭제됨(적용 모드)

    @property
    def blocked(self) -> bool:
        return self.existed and bool(self.scene_refs or self.manifest_refs)

    @property
    def safe(self) -> bool:
        return self.existed and not self.scene_refs and not self.manifest_refs


def cleanup_placeholder(
    plan: EntryPlan,
    project_dir: Path,
    manifest_path: Path,
    processed_ids: set[str],
    *,
    dry_run: bool,
) -> PlaceholderCleanup:
    """교체 성공 후 낡은 placeholder(+사이드카) 정리. 참조가 남아 있으면 보류.

    dry_run 이면 아무것도 지우지 않고 계획만 담아 반환한다.
    """
    ph_rel = plan.placeholder_path
    result = PlaceholderCleanup(plan.entry_id, ph_rel)

    # 안전장치 ①: 삭제 대상 basename 은 반드시 PLACEHOLDER_ 접두사여야 한다.
    if not Path(ph_rel).name.startswith(PLACEHOLDER_PREFIX):
        return result
    # 안전장치 ②: 실제 에셋 경로와 동일하면 절대 삭제 금지(실 에셋 오삭제 방지).
    if _resolve_ref_path(ph_rel, project_dir) == _resolve_ref_path(plan.real_path, project_dir):
        return result
    # 안전장치 ③: 파일이 이미 없으면 정리할 것 없음.
    if not (project_dir / ph_rel).exists():
        return result

    result.existed = True
    swapped_scenes = {e.scene for e in plan.edits if e.replacements > 0}
    result.scene_refs = scene_refs_to_placeholder(project_dir, ph_rel, swapped_scenes)
    result.manifest_refs = manifest_refs_to_placeholder(
        manifest_path, project_dir, ph_rel, processed_ids
    )

    # 삭제 후보: placeholder png + 존재하는 사이드카(.import/.uid)
    cands = [ph_rel]
    for suffix in _SIDECAR_SUFFIXES:
        if (project_dir / (ph_rel + suffix)).exists():
            cands.append(ph_rel + suffix)
    result.candidates = cands

    # 안전장치 ④: 참조가 하나라도 남아 있으면 보류(삭제 안 함).
    if result.blocked:
        return result

    if not dry_run:
        for rel in cands:
            try:
                (project_dir / rel).unlink()
                result.deleted.append(rel)
            except OSError:
                pass  # 이미 없거나 삭제 불가 — 치명적 아님(교체 자체는 성공)
    return result


def _print_cleanup(c: PlaceholderCleanup, *, dry_run: bool) -> None:
    if not c.existed:
        return
    if c.blocked:
        refs = c.scene_refs + [f"manifest:{i}" for i in c.manifest_refs]
        verb = "보류 예정" if dry_run else "삭제 보류"
        print(f"        [{verb}] 낡은 placeholder 유지 — 다른 참조 {len(refs)}건: "
              f"{', '.join(refs)}")
    elif dry_run:
        print(f"        [삭제 예정] 낡은 placeholder: {', '.join(c.candidates)}")
    elif c.deleted:
        print(f"        [정리] 낡은 placeholder 삭제: {', '.join(c.deleted)}")


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_plans(plans: list[EntryPlan]) -> None:
    for p in plans:
        if p.skip_reason and p.total_replacements == 0:
            print(f"  [SKIP] {p.entry_id}: {p.skip_reason}")
            continue
        print(f"  [SWAP] {p.entry_id}: {p.placeholder_path} → {p.real_path}")
        for e in p.edits:
            mark = f"{e.replacements}건" if e.replacements else "0건(참조 없음)"
            print(f"           {e.scene}: {mark}")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="art_reskin.py",
        description="매니페스트 기반 placeholder→실제 에셋 씬 교체 + 상태 갱신 + 재임포트",
    )
    parser.add_argument("--project", default=str(root), help="Godot 프로젝트 디렉토리")
    # --manifest/--schema 는 기본적으로 --project 하위에서 유도한다. (실데이터 오염 방지:
    # --project 를 임시 복제본으로 지정하면 매니페스트도 자동으로 그 복제본을 가리킨다.)
    parser.add_argument("--manifest", default=None,
                        help="기본: <project>/pipeline/manifest.json")
    parser.add_argument("--schema", default=None,
                        help="기본: <project>/pipeline/schemas/asset-manifest.schema.json")
    parser.add_argument("--status", default="placeholder",
                        help="선택할 엔트리 상태 (기본: placeholder). --id 지정 시 무시.")
    parser.add_argument("--id", action="append", metavar="ENTRY_ID",
                        help="특정 엔트리만 대상(반복 가능). 지정 시 --status 무시.")
    parser.add_argument("--set-status", default="generated",
                        help="교체 후 지정할 상태 (기본: generated)")
    parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
    parser.add_argument("--skip-import", action="store_true",
                        help="Godot 재임포트를 생략(로직만 적용)")
    parser.add_argument("--dry-run", action="store_true",
                        help="아무것도 쓰지 않고 계획만 출력")
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    manifest_path = (
        Path(args.manifest) if args.manifest
        else project_dir / "pipeline" / "manifest.json"
    )
    schema_path = (
        Path(args.schema) if args.schema
        else project_dir / "pipeline" / "schemas" / "asset-manifest.schema.json"
    )

    try:
        manifest = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError) as exc:
        print(f"오류: 매니페스트 로드 실패: {exc}", file=sys.stderr)
        return 2

    plans = build_plans(
        manifest, project_dir, status=args.status, ids=args.id
    )

    print("=" * 64)
    print(f"art reskin — {'DRY-RUN(미적용)' if args.dry_run else '적용'}")
    print(f"프로젝트: {project_dir}")
    sel = f"id={args.id}" if args.id else f"status={args.status}"
    print(f"대상 선택: {sel} · 후처리 상태: {args.set_status}")
    print("=" * 64)

    if not plans:
        print("대상 엔트리가 없습니다.")
        return 0

    _print_plans(plans)

    actionable = [p for p in plans if p.asset_exists and p.total_replacements > 0]
    processed_ids = {p.entry_id for p in actionable}
    if args.dry_run:
        for plan in actionable:
            c = cleanup_placeholder(
                plan, project_dir, manifest_path, processed_ids, dry_run=True
            )
            _print_cleanup(c, dry_run=True)
        print("-" * 64)
        print(f"DRY-RUN: 교체 예정 {len(actionable)}개 엔트리 "
              f"(총 {sum(p.total_replacements for p in actionable)}건). 변경 없음.")
        return 0

    if not actionable:
        print("-" * 64)
        print("교체할 대상이 없습니다(실제 에셋 부재 또는 참조 없음). 변경 없음.")
        return 0

    # 적용: 씬 교체 → 매니페스트 상태 갱신(단일 창구) → 재임포트
    print("-" * 64)
    failures = 0
    swapped = 0
    for plan in actionable:
        n = apply_scene_edits(plan, project_dir)
        res = update_manifest_status(
            plan, manifest_path=manifest_path, schema_path=schema_path,
            new_status=args.set_status,
        )
        if res.returncode != 0:
            failures += 1
            print(f"[FAIL] {plan.entry_id}: 매니페스트 갱신 실패\n{res.stderr.strip()}")
            continue
        swapped += 1
        print(f"[OK] {plan.entry_id}: 씬 {n}건 교체 · status={args.set_status} · file={plan.real_path}")
        # 교체 성공 직후에만 낡은 placeholder 정리(참조 남아 있으면 보류).
        c = cleanup_placeholder(
            plan, project_dir, manifest_path, processed_ids, dry_run=False
        )
        _print_cleanup(c, dry_run=False)

    if failures:
        print("-" * 64)
        print(f"결과: 실패 {failures}건 / {len(actionable)}")
        return 1

    # 재임포트
    if args.skip_import:
        print("[i] --skip-import: Godot 재임포트 생략")
    else:
        from shutil import which
        if which(args.godot) is None and not Path(args.godot).exists():
            print(f"[i] godot 실행 파일 없음({args.godot!r}) — 재임포트 생략. "
                  f"이후 `godot --headless --import` 를 직접 실행하세요.")
        else:
            try:
                imp = run_godot_import(args.godot, project_dir)
            except subprocess.TimeoutExpired:
                print("[FAIL] 재임포트 타임아웃(300s)")
                return 1
            if imp.returncode != 0:
                print(f"[FAIL] 재임포트 실패(exit={imp.returncode})\n{imp.stderr.strip()[-800:]}")
                return 1
            print("[OK] Godot 재임포트 완료")

    print("-" * 64)
    print(f"결과: {swapped}개 엔트리 교체 완료")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
