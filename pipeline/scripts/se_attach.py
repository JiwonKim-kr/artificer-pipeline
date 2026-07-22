#!/usr/bin/env python3
"""se attach — 매니페스트 기반 code_event → 씬 효과음 자동 연결 (로컬 메커니즘).

매니페스트의 se entry(`requested_by: code_event:<스크립트>::<메서드>`)를 읽어,
그 스크립트가 붙은 씬(.tscn)에 **AudioStreamPlayer + 범용 브리지
(src/tools/se_emitter.gd)** 노드를 삽입한다. 브리지가 `_ready` 에서 지정
시그널을 구독해 스트림을 재생하므로 **src/core/ 게임 로직은 일절 수정하지
않는다** (CLAUDE.md: src/core 는 승인 spec 없이 수정 금지 / SE 무지 원칙).

연결 정보는 전부 데이터에서 온다 (장르·이벤트 하드코딩 금지, HANDOFF §6-3):
  - 어떤 씬/노드에 붙는가  → 스크립트 ext_resource 를 참조하는 씬을 스캔해 유도
  - 어떤 시그널을 구독하는가 → entry `params.signal` > `--signal`(단일 --id 시)
                              > 스크립트 소스에서 메서드가 emit 하는 선언 시그널 유도
  - 무엇을 재생하는가       → entry `file` 의 PLACEHOLDER_ 규약으로 실제 경로 유도
                              (art_reskin.derive_paths 재사용 — 트랙 무관 경로 규칙)

선택 규칙 (art_reskin 과 동일 철학):
  · 기본: track=se, `status=placeholder` entry 중 **실제 에셋이 디스크에 존재**
    하는 것. (없으면 `se gen 먼저` 로 보고하고 건너뜀 — 크래시 아님.
    `--allow-placeholder` 지정 시 플레이스홀더 스트림으로라도 연결한다.)
  · `--id` 로 특정 entry 만, `--status` 로 선택 상태 변경 가능.
  · 이미 브리지 노드가 있는 씬은 건너뛰되, 스트림이 플레이스홀더인데 실제
    에셋이 생겼으면 경로만 교체(upgrade)한다. (재실행 안전 — 멱등)

반영: 씬 삽입/교체 → **manifest.py update-status** 로 `generated`+`file` 갱신
(단일 창구, 실제 에셋 연결 시에만) → Godot 재임포트(`--skip-import` 로 생략).
최종 `approved` 는 상위 review(사람) 몫이다.

안전장치: `--dry-run` 은 아무것도 쓰지 않고 계획만 출력한다. 테스트는 저장소
전체를 임시 복제해 `--project <복제본>` 으로 실행한다(매니페스트/스키마 기본
경로는 --project 에서 유도) — 실데이터를 건드리지 않는다.

종료 코드: 0 = 성공(연결 or 연결할 것 없음), 1 = 처리 실패(씬/매니페스트/임포트),
          2 = 실행/인자 오류.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import os
import re
import subprocess
import sys
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402
from art_reskin import derive_paths, run_godot_import  # noqa: E402  (경로 규약·재임포트 재사용)

BRIDGE_SCRIPT = "src/tools/se_emitter.gd"  # 범용 브리지 (특정 씬/게임 비참조)

# 확장자 → Godot 리소스 타입 (ext_resource type 힌트)
_STREAM_TYPES = {
    ".ogg": "AudioStreamOggVorbis",
    ".wav": "AudioStreamWAV",
    ".mp3": "AudioStreamMP3",
}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_py() -> Path:
    return Path(__file__).resolve().parent / "manifest.py"


# ---------------------------------------------------------------------------
# 시그널 유도 (스크립트 소스 파싱 — 데이터 기반)
# ---------------------------------------------------------------------------
def derive_signal(script_text: str, method: str) -> tuple[str | None, str | None]:
    """(signal_name, 실패 사유) — 메서드가 emit 하는 선언 시그널을 유도한다.

    규칙: ① method 자체가 선언 시그널 이름이면 그대로 사용.
          ② method 본문에서 `<시그널>.emit(...)` 을 찾아 선언 시그널과 교집합.
             정확히 1개일 때만 성공(복수/0개면 params.signal 명시 필요).
    """
    declared = set(re.findall(r"(?m)^\s*signal\s+([A-Za-z_]\w*)", script_text))
    if method in declared:
        return method, None
    m = re.search(rf"(?m)^(?:static\s+)?func\s+{re.escape(method)}\s*\(", script_text)
    if m is None:
        return None, f"스크립트에서 메서드 '{method}' 를 찾지 못함"
    body_start = m.end()
    nxt = re.search(r"(?m)^(?:static\s+)?func\s+", script_text[body_start:])
    body = script_text[body_start:body_start + nxt.start()] if nxt else script_text[body_start:]
    emits = [e for e in dict.fromkeys(re.findall(r"([A-Za-z_]\w*)\.emit\s*\(", body))
             if e in declared]
    if len(emits) == 1:
        return emits[0], None
    if not emits:
        return None, ("메서드가 emit 하는 선언 시그널을 찾지 못함 "
                      "(entry params.signal 또는 --signal 로 명시 필요)")
    return None, (f"메서드가 복수 시그널을 emit: {emits} "
                  f"(entry params.signal 또는 --signal 로 명시 필요)")


# ---------------------------------------------------------------------------
# .tscn 파싱 (텍스트 기반 — Godot 이 다시 저장하면 정식 포맷으로 재정렬된다)
# ---------------------------------------------------------------------------
_SECTION_RE = re.compile(r"(?m)^\[(\w+)([^\]]*)\]")
_ATTR_RE = re.compile(r'(\w+)="([^"]*)"')


def _parse_ext_resources(scene_text: str) -> list[dict]:
    out: list[dict] = []
    for m in _SECTION_RE.finditer(scene_text):
        if m.group(1) == "ext_resource":
            attrs = dict(_ATTR_RE.findall(m.group(2)))
            attrs["_span"] = m.span()  # type: ignore[assignment]
            out.append(attrs)
    return out


def _iter_node_blocks(scene_text: str):
    """[node ...] 섹션들을 (attrs, block_text, span) 으로 순회."""
    sections = list(_SECTION_RE.finditer(scene_text))
    for i, m in enumerate(sections):
        if m.group(1) != "node":
            continue
        attrs = dict(_ATTR_RE.findall(m.group(2)))
        end = sections[i + 1].start() if i + 1 < len(sections) else len(scene_text)
        yield attrs, scene_text[m.start():end], (m.start(), end)


def find_script_node(scene_text: str, script_res_path: str) -> tuple[str, str] | None:
    """스크립트가 붙은 노드를 찾아 (노드 이름, 새 자식의 parent 속성값)을 반환.

    parent 속성값: 대상 노드가 루트면 '.', 루트 직계면 '<이름>',
    그 외 '<parent>/<이름>' (Godot .tscn parent 표기 규약).
    """
    script_id = None
    for ext in _parse_ext_resources(scene_text):
        if ext.get("type") == "Script" and ext.get("path") == script_res_path:
            script_id = ext.get("id")
            break
    if script_id is None:
        return None
    needle = f'script = ExtResource("{script_id}")'
    for attrs, block, _span in _iter_node_blocks(scene_text):
        if needle in block:
            name = attrs.get("name", "")
            parent = attrs.get("parent")
            if parent is None:
                return name, "."          # 루트 노드
            if parent == ".":
                return name, name          # 루트 직계
            return name, f"{parent}/{name}"
    return None


def _unique_ext_id(scene_text: str, base: str, offset: int = 1) -> str:
    """씬 안에서 유일한 ext_resource id 를 만든다 (Godot 스타일 'N_suffix')."""
    n = len(_parse_ext_resources(scene_text)) + offset
    candidate = f"{n}_{base}"
    while f'id="{candidate}"' in scene_text:
        n += 1
        candidate = f"{n}_{base}"
    return candidate


def _stream_type(asset_path: str) -> str:
    return _STREAM_TYPES.get(Path(asset_path).suffix.lower(), "AudioStream")


def node_name_for_entry(entry_id: str) -> str:
    """매니페스트 ID → PascalCase 노드 이름. 예: se:player_step → SePlayerStep."""
    tail = entry_id.split(":", 1)[-1].replace("/", "_")
    return "Se" + "".join(part.capitalize() for part in tail.split("_") if part)


def insert_bridge_node(
    scene_text: str,
    *,
    node_name: str,
    parent: str,
    stream_path: str,
    signal_name: str,
) -> str:
    """씬 텍스트에 ext_resource 2건 + 브리지 노드 1건을 삽입해 반환한다."""
    script_id = _unique_ext_id(scene_text, "se_emitter")
    # id 는 삽입 전 텍스트 기준으로 만들되 두 id 가 겹치지 않게 순차 유도
    stream_id = _unique_ext_id(scene_text + f' id="{script_id}"', "se_stream", offset=2)

    ext_lines = (
        f'[ext_resource type="Script" path="res://{BRIDGE_SCRIPT}" id="{script_id}"]\n'
        f'[ext_resource type="{_stream_type(stream_path)}" '
        f'path="res://{stream_path}" id="{stream_id}"]\n'
    )

    # 1) load_steps 갱신 (+2). 없으면 추가 (ext 2 + 씬 1 = 3 이상).
    def _bump(m: re.Match[str]) -> str:
        return f"load_steps={int(m.group(1)) + 2}"

    text, n_subs = re.subn(r"load_steps=(\d+)", _bump, scene_text, count=1)
    if n_subs == 0:
        text = text.replace("[gd_scene ", "[gd_scene load_steps=3 ", 1)

    # 2) ext_resource 삽입: 마지막 ext_resource 줄 뒤(없으면 gd_scene 헤더 뒤)
    exts = _parse_ext_resources(text)
    if exts:
        insert_at = text.index("\n", exts[-1]["_span"][1]) + 1  # type: ignore[index]
        text = text[:insert_at] + ext_lines + text[insert_at:]
    else:
        header_end = text.index("\n", text.index("[gd_scene")) + 1
        text = text[:header_end] + "\n" + ext_lines + text[header_end:]

    # 3) 브리지 노드 블록을 파일 끝에 추가 (부모 선언은 항상 앞에 있음)
    if not text.endswith("\n"):
        text += "\n"
    text += (
        f'\n[node name="{node_name}" type="AudioStreamPlayer" parent="{parent}"]\n'
        f'script = ExtResource("{script_id}")\n'
        f'stream = ExtResource("{stream_id}")\n'
        f'target_path = NodePath("..")\n'
        f'signal_name = &"{signal_name}"\n'
    )
    return text


# ---------------------------------------------------------------------------
# 계획 수립
# ---------------------------------------------------------------------------
@dataclass
class SceneAttach:
    scene: str            # 저장소 상대경로
    action: str           # add | upgrade | already | none
    node_name: str = ""
    parent: str = "."
    detail: str = ""


@dataclass
class AttachPlan:
    entry_id: str
    script_path: str = ""
    method: str = ""
    signal: str | None = None
    placeholder_path: str = ""
    real_path: str = ""
    stream_path: str = ""          # 실제 연결할 스트림 (real 또는 placeholder)
    stream_is_real: bool = False
    scenes: list[SceneAttach] = field(default_factory=list)
    skip_reason: str | None = None

    @property
    def actionable(self) -> bool:
        return self.skip_reason is None and any(
            s.action in ("add", "upgrade") for s in self.scenes
        )


def _parse_code_event(entry: dict) -> tuple[str, str] | None:
    for rb in entry.get("requested_by", []):
        if rb.get("kind") == "code_event":
            path = str(rb.get("path", ""))
            if "::" in path:
                script, method = path.split("::", 1)
                return script.strip(), method.strip()
    return None


def build_plans(
    manifest: dict,
    project_dir: Path,
    *,
    status: str | None,
    ids: list[str] | None,
    signal_override: str | None,
    allow_placeholder: bool,
) -> list[AttachPlan]:
    plans: list[AttachPlan] = []
    id_set = set(ids) if ids else None
    for entry in manifest.get("entries", []):
        entry_id = str(entry.get("id", ""))
        if entry.get("track") != "se":
            if id_set is not None and entry_id in id_set:
                plans.append(AttachPlan(entry_id, skip_reason="se 트랙 entry 가 아님"))
            continue
        if id_set is not None:
            if entry_id not in id_set:
                continue
        elif status is not None and entry.get("status") != status:
            continue

        plan = AttachPlan(entry_id)
        ce = _parse_code_event(entry)
        if ce is None:
            plan.skip_reason = "requested_by 에 code_event:<스크립트>::<메서드> 가 없음"
            plans.append(plan)
            continue
        plan.script_path, plan.method = ce

        placeholder, real = derive_paths(entry)
        plan.placeholder_path, plan.real_path = placeholder, real
        real_exists = (project_dir / real).exists()
        placeholder_exists = (project_dir / placeholder).exists()
        if real_exists:
            plan.stream_path, plan.stream_is_real = real, True
        elif allow_placeholder and placeholder_exists:
            plan.stream_path, plan.stream_is_real = placeholder, False
        else:
            plan.skip_reason = f"실제 에셋 없음 → {real} (se gen 먼저 실행 필요)"
            plans.append(plan)
            continue

        # 시그널 결정: params.signal > --signal > 소스 유도
        params = entry.get("params") or {}
        script_abs = project_dir / plan.script_path
        if isinstance(params.get("signal"), str) and params["signal"]:
            plan.signal = params["signal"]
        elif signal_override:
            plan.signal = signal_override
        else:
            if not script_abs.exists():
                plan.skip_reason = f"스크립트 없음: {plan.script_path}"
                plans.append(plan)
                continue
            sig, why = derive_signal(script_abs.read_text(encoding="utf-8"), plan.method)
            if sig is None:
                plan.skip_reason = f"시그널 유도 실패: {why}"
                plans.append(plan)
                continue
            plan.signal = sig

        # 대상 씬 스캔: 스크립트가 붙은 노드를 가진 .tscn
        node_name = node_name_for_entry(entry_id)
        scenes_dir = project_dir / "scenes"
        scene_files = sorted(scenes_dir.rglob("*.tscn")) if scenes_dir.exists() else []
        for scene_abs in scene_files:
            scene_rel = scene_abs.relative_to(project_dir).as_posix()
            text = scene_abs.read_text(encoding="utf-8")
            found = find_script_node(text, f"res://{plan.script_path}")
            if found is None:
                continue
            _owner, parent = found
            if f'[node name="{node_name}"' in text:
                # 이미 연결됨 — 플레이스홀더 → 실제 업그레이드만 검사
                if plan.stream_is_real and f"res://{plan.placeholder_path}" in text:
                    plan.scenes.append(SceneAttach(
                        scene_rel, "upgrade", node_name, parent,
                        f"스트림 교체: {plan.placeholder_path} → {plan.real_path}",
                    ))
                else:
                    plan.scenes.append(SceneAttach(
                        scene_rel, "already", node_name, parent, "이미 연결됨(멱등 skip)",
                    ))
                continue
            plan.scenes.append(SceneAttach(
                scene_rel, "add", node_name, parent,
                f"signal={plan.signal} stream={plan.stream_path}",
            ))
        if not plan.scenes:
            plan.skip_reason = (
                f"스크립트 {plan.script_path} 가 붙은 씬을 scenes/ 에서 찾지 못함"
            )
        plans.append(plan)
    return plans


# ---------------------------------------------------------------------------
# 적용
# ---------------------------------------------------------------------------
def apply_plan(plan: AttachPlan, project_dir: Path) -> int:
    """계획대로 씬을 수정한다. 수정한 씬 수를 반환."""
    changed = 0
    for sa in plan.scenes:
        scene_abs = project_dir / sa.scene
        text = scene_abs.read_text(encoding="utf-8")
        if sa.action == "add":
            new_text = insert_bridge_node(
                text,
                node_name=sa.node_name,
                parent=sa.parent,
                stream_path=plan.stream_path,
                signal_name=plan.signal or "",
            )
        elif sa.action == "upgrade":
            new_text = text.replace(
                f"res://{plan.placeholder_path}", f"res://{plan.real_path}"
            )
        else:
            continue
        if new_text != text:
            scene_abs.write_text(new_text, encoding="utf-8")
            changed += 1
    return changed


def update_manifest_status(
    entry_id: str, *, manifest_path: Path, schema_path: Path,
    new_status: str, file_path: str,
) -> subprocess.CompletedProcess[str]:
    """manifest.py 를 통해서만 상태/파일 경로를 갱신한다 (단일 쓰기 창구)."""
    return subprocess.run(
        [sys.executable, str(_manifest_py()),
         "--manifest", str(manifest_path), "--schema", str(schema_path),
         "update-status", "--id", entry_id,
         "--status", new_status, "--file", file_path],
        capture_output=True, text=True,
    )


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _print_plans(plans: list[AttachPlan]) -> None:
    for p in plans:
        if p.skip_reason:
            print(f"  [SKIP] {p.entry_id}: {p.skip_reason}")
            continue
        src = "실제" if p.stream_is_real else "플레이스홀더"
        print(f"  [ATTACH] {p.entry_id}: {p.script_path}::{p.method} "
              f"→ signal '{p.signal}' → {p.stream_path} ({src})")
        for sa in p.scenes:
            print(f"           {sa.scene}: [{sa.action}] {sa.node_name} "
                  f"(parent={sa.parent}) {sa.detail}")


def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="se_attach.py",
        description="매니페스트 code_event 기반 SE 씬 연결 (브리지 노드 삽입) + 상태 갱신 + 재임포트",
    )
    parser.add_argument("--project", default=str(root), help="Godot 프로젝트 디렉토리")
    # --manifest/--schema 는 기본적으로 --project 하위에서 유도한다. (실데이터 오염 방지:
    # --project 를 임시 복제본으로 지정하면 매니페스트도 자동으로 그 복제본을 가리킨다.)
    parser.add_argument("--manifest", default=None,
                        help="기본: <project>/pipeline/manifest.json")
    parser.add_argument("--schema", default=None,
                        help="기본: <project>/pipeline/schemas/asset-manifest.schema.json")
    parser.add_argument("--status", default="placeholder",
                        help="선택할 entry 상태 (기본: placeholder). --id 지정 시 무시.")
    parser.add_argument("--id", action="append", metavar="ENTRY_ID",
                        help="특정 entry 만 대상(반복 가능). 지정 시 --status 무시.")
    parser.add_argument("--set-status", default="generated",
                        help="실제 에셋 연결 후 지정할 상태 (기본: generated)")
    parser.add_argument("--signal", default=None,
                        help="시그널 이름 강제 지정 (단일 --id 대상에만 허용)")
    parser.add_argument("--allow-placeholder", action="store_true",
                        help="실제 에셋이 없으면 플레이스홀더 스트림으로라도 연결")
    parser.add_argument("--godot", default=os.environ.get("GODOT_BIN", "godot"))
    parser.add_argument("--skip-import", action="store_true",
                        help="Godot 재임포트를 생략(로직만 적용)")
    parser.add_argument("--dry-run", action="store_true",
                        help="아무것도 쓰지 않고 계획만 출력")
    args = parser.parse_args(argv)

    if args.signal and (not args.id or len(args.id) != 1):
        print("오류: --signal 은 --id 를 정확히 1개 지정할 때만 쓸 수 있습니다.",
              file=sys.stderr)
        return 2

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
        manifest, project_dir,
        status=args.status, ids=args.id,
        signal_override=args.signal, allow_placeholder=args.allow_placeholder,
    )

    print("=" * 64)
    print(f"se attach — {'DRY-RUN(미적용)' if args.dry_run else '적용'}")
    print(f"프로젝트: {project_dir}")
    sel = f"id={args.id}" if args.id else f"status={args.status} (track=se)"
    print(f"대상 선택: {sel} · 브리지: {BRIDGE_SCRIPT}")
    print("=" * 64)

    if not plans:
        print("대상 entry 가 없습니다.")
        return 0

    _print_plans(plans)
    actionable = [p for p in plans if p.actionable]

    if args.dry_run:
        print("-" * 64)
        n_scenes = sum(
            1 for p in actionable for s in p.scenes if s.action in ("add", "upgrade")
        )
        print(f"DRY-RUN: 연결 예정 {len(actionable)}개 entry (씬 수정 {n_scenes}건). 변경 없음.")
        return 0

    if not actionable:
        print("-" * 64)
        print("연결할 대상이 없습니다(에셋 부재/씬 없음/이미 연결됨). 변경 없음.")
        return 0

    # 브리지 스크립트 존재 확인 (씬이 참조할 파일)
    if not (project_dir / BRIDGE_SCRIPT).exists():
        print(f"오류: 브리지 스크립트가 없습니다: {BRIDGE_SCRIPT}", file=sys.stderr)
        return 1

    print("-" * 64)
    failures = 0
    attached = 0
    for plan in actionable:
        n = apply_plan(plan, project_dir)
        if plan.stream_is_real:
            res = update_manifest_status(
                plan.entry_id, manifest_path=manifest_path, schema_path=schema_path,
                new_status=args.set_status, file_path=plan.real_path,
            )
            if res.returncode != 0:
                failures += 1
                print(f"[FAIL] {plan.entry_id}: 매니페스트 갱신 실패\n{res.stderr.strip()}")
                continue
            status_note = f"status={args.set_status} · file={plan.real_path}"
        else:
            status_note = "플레이스홀더 연결 — 매니페스트 상태 유지(placeholder)"
        attached += 1
        print(f"[OK] {plan.entry_id}: 씬 {n}건 수정 · signal={plan.signal} · {status_note}")

    if failures:
        print("-" * 64)
        print(f"결과: 실패 {failures}건 / {len(actionable)}")
        return 1

    # 재임포트 (art_reskin 과 동일 흐름)
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
    print(f"결과: {attached}개 entry 연결 완료 (최종 approved 는 review(사람) 몫)")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
