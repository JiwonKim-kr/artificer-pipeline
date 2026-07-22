#!/usr/bin/env python3
"""review — 사람 검수 큐 + 승인/반려 반영 (오케스트레이션 공통).

review 는 승인 지점(에셋 approved · spec 승인 · art lock)의 **단일 창구**다.
이 스크립트는 검수 대기 항목을 모아 제시(`list`)하고, **사람이 내린 결정**을
기계적으로 반영(`approve`/`reject`)하는 실행기다. 승인 여부의 판단은 사람이 하며,
슬래시 커맨드(/review)가 그 결정을 수집해 이 스크립트에 넘긴다.
**이 스크립트는 스스로 승인 여부를 판단하지 않는다.**

검수 큐(list)에 모으는 항목:
  (a) status=generated 매니페스트 entry   → approved 후보 (id = entry id)
  (b) status=draft 인 spec 문서            → spec 승인 대기 (id = spec:<이름>)
  (c) manifest.style_guide 미설정          → art lock 미완 표시 (정보 항목, 승인 대상 아님)

반영(사람 결정을 스크립트 경유로):
  approve --id <id>
    - 에셋(entry id): manifest.py update-status --status approved (단일 쓰기 창구)
    - 스펙(spec:<이름>): 문서 status 필드를 approved 로 갱신
  reject --id <id> --reason "..."
    - 에셋: manifest.py update-status --status rejected + history 에 피드백 기록
    - 스펙: status 는 draft 유지(승인 안 됨), 문서에 반려 사유 노트 추가

상태 전이 규칙: 에셋 approve/reject 는 현재 status 가 **generated** 일 때만 허용한다
(생성 → 검수 → 반영). 이미 approved/rejected 면 멱등 안내로 넘어간다.

종료 코드: 0 = 성공, 1 = 반영 오류(매니페스트 쓰기 실패 등), 2 = 인자/상태 오류.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import datetime
import json
import os
import re
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402

SPEC_ID_PREFIX = "spec:"
APPROVABLE_FROM = {"generated"}
REJECTABLE_FROM = {"generated"}


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


def _manifest_py() -> Path:
    return Path(__file__).resolve().parent / "manifest.py"


# ---------------------------------------------------------------------------
# 큐 수집
# ---------------------------------------------------------------------------
_SPEC_STATUS_RE = re.compile(r"^(\s*-\s*\*\*status\*\*\s*:\s*)(\S+)", re.MULTILINE)


def _parse_spec_status(text: str) -> str | None:
    m = _SPEC_STATUS_RE.search(text)
    return m.group(2).strip() if m else None


def build_queue(manifest_path: Path, specs_dir: Path) -> dict:
    """검수 대기 큐를 수집한다. (읽기 전용)"""
    assets_pending: list[dict] = []
    style_guide = None
    try:
        data = manifest_mod.load_manifest(str(manifest_path))
        style_guide = data.get("style_guide")
        for e in data.get("entries", []):
            if e.get("status") == "generated":
                assets_pending.append({
                    "id": e.get("id"),
                    "track": e.get("track"),
                    "spec": e.get("spec"),
                    "file": e.get("file"),
                })
    except (FileNotFoundError, ValueError):
        pass

    specs_pending: list[dict] = []
    if specs_dir.exists():
        for p in sorted(specs_dir.glob("*.md")):
            try:
                st = _parse_spec_status(p.read_text(encoding="utf-8"))
            except OSError:
                st = None
            if st == "draft":
                specs_pending.append({
                    "id": f"{SPEC_ID_PREFIX}{p.stem}",
                    "name": p.stem,
                    "status": st,
                    "path": str(p),
                })

    return {
        "assets_pending": assets_pending,
        "specs_pending": specs_pending,
        "art_lock": {"locked": style_guide is not None, "style_guide": style_guide},
    }


def render_queue(queue: dict) -> str:
    L: list[str] = []
    L.append("=" * 64)
    L.append("review — 사람 검수 큐 (승인 지점 단일 창구)")
    L.append("=" * 64)

    L.append("[에셋 검수 대기 — status=generated → approve/reject 대상]")
    if queue["assets_pending"]:
        for a in queue["assets_pending"]:
            L.append(f"  - {a['id']}  (track={a['track']})")
            L.append(f"      spec: {a['spec']}")
            if a.get("file"):
                L.append(f"      file: {a['file']}")
    else:
        L.append("  (없음)")

    L.append("[스펙 승인 대기 — status=draft → approve/reject 대상]")
    if queue["specs_pending"]:
        for s in queue["specs_pending"]:
            L.append(f"  - {s['id']}  ({s['path']})")
    else:
        L.append("  (없음)")

    lock = queue["art_lock"]
    L.append("[art lock — 스타일 승인 지점 (정보)]")
    if lock["locked"]:
        L.append(f"  잠김: style_guide = {lock['style_guide']}")
    else:
        L.append("  미완: 스타일 미고정 (사람 승인 후 /art lock 필요 — 승인 대상 아님)")

    L.append("-" * 64)
    L.append("반영: review approve --id <id>  |  review reject --id <id> --reason \"...\"")
    L.append("주의: 승인 여부는 사람이 결정한다. 이 도구는 결정을 반영만 한다.")
    return "\n".join(L)


# ---------------------------------------------------------------------------
# 반영 — 에셋 (manifest.py 단일 창구)
# ---------------------------------------------------------------------------
def _find_entry(manifest_path: Path, entry_id: str) -> dict | None:
    try:
        data = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError):
        return None
    for e in data.get("entries", []):
        if e.get("id") == entry_id:
            return e
    return None


def _manifest_update(manifest_path: Path, schema_path: Path, entry_id: str,
                     status: str, feedback: str | None) -> subprocess.CompletedProcess[str]:
    cmd = [
        sys.executable, str(_manifest_py()),
        "--manifest", str(manifest_path), "--schema", str(schema_path),
        "update-status", "--id", entry_id, "--status", status,
    ]
    if feedback:
        cmd += ["--feedback", feedback]
    return subprocess.run(cmd, capture_output=True, text=True)


def apply_asset(manifest_path: Path, schema_path: Path, entry_id: str,
                action: str, reason: str | None) -> int:
    entry = _find_entry(manifest_path, entry_id)
    if entry is None:
        print(f"오류: 매니페스트에 entry '{entry_id}' 가 없습니다.", file=sys.stderr)
        return 2
    cur = entry.get("status")
    target = "approved" if action == "approve" else "rejected"
    allowed = APPROVABLE_FROM if action == "approve" else REJECTABLE_FROM

    if cur == target:
        print(f"멱등: '{entry_id}' 는 이미 {target} 입니다. (변경 없음)")
        return 0
    if cur not in allowed:
        print(f"오류: '{entry_id}' 의 현재 status='{cur}' 는 {action} 대상이 아닙니다 "
              f"(허용: {', '.join(sorted(allowed))}). "
              f"먼저 생성(generated)해야 합니다.", file=sys.stderr)
        return 2

    r = _manifest_update(manifest_path, schema_path, entry_id, target, reason)
    if r.returncode != 0:
        print("반영 실패 — 매니페스트를 쓰지 못했습니다:", file=sys.stderr)
        print(r.stderr.strip(), file=sys.stderr)
        return 1
    print(f"반영됨: {entry_id} → {target}"
          + (f" (사유: {reason})" if reason and action == "reject" else ""))
    return 0


# ---------------------------------------------------------------------------
# 반영 — 스펙 (문서 status 필드 갱신)
# ---------------------------------------------------------------------------
def _spec_path(specs_dir: Path, spec_id: str) -> Path:
    name = spec_id[len(SPEC_ID_PREFIX):]
    return specs_dir / f"{name}.md"


def apply_spec(specs_dir: Path, spec_id: str, action: str, reason: str | None) -> int:
    path = _spec_path(specs_dir, spec_id)
    if not path.exists():
        print(f"오류: 스펙 문서가 없습니다: {path}", file=sys.stderr)
        return 2
    text = path.read_text(encoding="utf-8")
    cur = _parse_spec_status(text)
    if cur is None:
        print(f"오류: 스펙 '{spec_id}' 에서 status 필드를 찾지 못했습니다.", file=sys.stderr)
        return 2

    today = datetime.date.today().isoformat()
    if action == "approve":
        if cur == "approved":
            print(f"멱등: '{spec_id}' 는 이미 approved 입니다. (변경 없음)")
            return 0
        new_text = _SPEC_STATUS_RE.sub(
            lambda m: f"{m.group(1)}approved", text, count=1)
        new_text += f"\n> [review 승인 {today}] 사람 검수 승인.\n"
        path.write_text(new_text, encoding="utf-8")
        print(f"반영됨: {spec_id} → approved (status 필드 갱신)")
        return 0
    else:  # reject — status 는 draft 유지, 반려 사유 노트 추가
        note = f"\n> [review 반려 {today}] {reason or '(사유 미기재)'} — 수정 후 재승인 필요.\n"
        path.write_text(text + note, encoding="utf-8")
        print(f"반영됨: {spec_id} 반려 기록 (status=draft 유지, 사유: {reason})")
        return 0


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _is_spec_id(entry_id: str) -> bool:
    return entry_id.startswith(SPEC_ID_PREFIX)


def _cmd_list(args: argparse.Namespace, ctx: dict) -> int:
    queue = build_queue(ctx["manifest"], ctx["specs_dir"])
    if args.json:
        print(json.dumps(queue, ensure_ascii=False, indent=2))
    else:
        print(render_queue(queue))
    return 0


def _cmd_approve(args: argparse.Namespace, ctx: dict) -> int:
    if _is_spec_id(args.id):
        return apply_spec(ctx["specs_dir"], args.id, "approve", None)
    return apply_asset(ctx["manifest"], ctx["schema"], args.id, "approve", None)


def _cmd_reject(args: argparse.Namespace, ctx: dict) -> int:
    if not args.reason:
        print("오류: reject 는 --reason 이 필요합니다 (한 줄 피드백).", file=sys.stderr)
        return 2
    if _is_spec_id(args.id):
        return apply_spec(ctx["specs_dir"], args.id, "reject", args.reason)
    return apply_asset(ctx["manifest"], ctx["schema"], args.id, "reject", args.reason)


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="review.py",
        description="사람 검수 큐 + 승인/반려 반영 (승인 지점 단일 창구). "
                    "판단은 사람이, 반영만 이 도구가.",
    )
    p.add_argument("--project", default=str(_repo_root()), help="프로젝트 루트")
    p.add_argument("--manifest", default=None, help="기본: <project>/pipeline/manifest.json")
    p.add_argument("--schema", default=None,
                   help="기본: <project>/pipeline/schemas/asset-manifest.schema.json")
    p.add_argument("--specs-dir", default=None, help="기본: <project>/docs/specs")
    sub = p.add_subparsers(dest="command", required=True)

    pl = sub.add_parser("list", help="검수 대기 큐 출력")
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=_cmd_list)

    pa = sub.add_parser("approve", help="승인 반영 (사람 결정 반영)")
    pa.add_argument("--id", required=True, help="entry id 또는 spec:<이름>")
    pa.set_defaults(func=_cmd_approve)

    pr = sub.add_parser("reject", help="반려 반영 + 한 줄 사유")
    pr.add_argument("--id", required=True, help="entry id 또는 spec:<이름>")
    pr.add_argument("--reason", required=True, help="반려 사유 (한 줄 피드백)")
    pr.set_defaults(func=_cmd_reject)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    project_dir = Path(args.project).resolve()
    ctx = {
        "project": project_dir,
        "manifest": Path(args.manifest) if args.manifest
        else project_dir / "pipeline" / "manifest.json",
        "schema": Path(args.schema) if args.schema
        else project_dir / "pipeline" / "schemas" / "asset-manifest.schema.json",
        "specs_dir": Path(args.specs_dir) if args.specs_dir
        else project_dir / "docs" / "specs",
    }
    try:
        return args.func(args, ctx)
    except (FileNotFoundError, NotADirectoryError, ValueError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
