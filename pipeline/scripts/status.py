#!/usr/bin/env python3
"""status — 프로젝트·태스크 현황 리포터 (오케스트레이션 공통).

파이프라인 전체 상태를 한눈에 모아 사람용 텍스트 + 기계용 JSON 으로 출력한다.
`plan` 은 이 현황을 근거로 목표를 트랙별 태스크로 분해하고, `review` 는 이 현황의
검수 대기 항목을 사람에게 제시한다. (읽기 전용 — 어떤 파일도 쓰지 않는다.)

수집 항목:
  - 매니페스트 entry: 트랙별·status별 집계 + id 목록, style_guide(art lock) 여부
  - docs/specs/*: spec 문서별 status(draft/approved 등)
  - lore/canon: 정본 문서 수 (0 이면 미초기화)
  - .env 키: SCENARIO_API_KEY / SCENARIO_API_SECRET / ELEVENLABS_API_KEY 의 **존재 여부만**
             (값은 절대 출력하지 않는다 — 비밀 보호)
  - 도구 버전: godot / ffmpeg / node (best-effort)
  - 테스트 러너: pipeline/tests/run_*.py 목록

--json: 위 전부를 구조화된 JSON 으로. stdlib 만 사용 (Python 3.14).
종료 코드: 0 = 성공, 2 = 실행 오류.
"""
from __future__ import annotations

import argparse
import json
import os
import re
import shutil
import subprocess
import sys
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import manifest as manifest_mod  # noqa: E402
import env_config  # noqa: E402

# 존재 여부만 확인할 비밀 키 (값은 절대 노출하지 않는다)
SECRET_KEYS = ("SCENARIO_API_KEY", "SCENARIO_API_SECRET", "ELEVENLABS_API_KEY")


def _repo_root() -> Path:
    return Path(__file__).resolve().parents[2]


# ---------------------------------------------------------------------------
# 수집기
# ---------------------------------------------------------------------------
def collect_manifest(manifest_path: Path) -> dict:
    try:
        data = manifest_mod.load_manifest(str(manifest_path))
    except (FileNotFoundError, ValueError) as exc:
        return {"error": str(exc), "entries": [], "by_track": {}, "by_status": {},
                "style_guide": None, "total": 0}

    entries = data.get("entries", [])
    by_track: dict[str, list[str]] = {}
    by_status: dict[str, list[str]] = {}
    for e in entries:
        eid = e.get("id", "?")
        by_track.setdefault(e.get("track", "?"), []).append(eid)
        by_status.setdefault(e.get("status", "?"), []).append(eid)
    return {
        "total": len(entries),
        "by_track": by_track,
        "by_status": by_status,
        "style_guide": data.get("style_guide"),
    }


_SPEC_STATUS_RE = re.compile(r"^\s*-\s*\*\*status\*\*\s*:\s*(\S+)", re.MULTILINE)


def parse_spec_status(text: str) -> str | None:
    m = _SPEC_STATUS_RE.search(text)
    return m.group(1).strip() if m else None


def collect_specs(specs_dir: Path) -> list[dict]:
    out: list[dict] = []
    if not specs_dir.exists():
        return out
    for p in sorted(specs_dir.glob("*.md")):
        try:
            text = p.read_text(encoding="utf-8")
        except OSError:
            text = ""
        out.append({
            "name": p.stem,
            "path": str(p.relative_to(specs_dir.parent.parent)) if _repo_root() in p.parents else str(p),
            "status": parse_spec_status(text) or "unknown",
        })
    return out


def collect_lore(canon_dir: Path) -> dict:
    docs = sorted(p.name for p in canon_dir.glob("*.md")) if canon_dir.exists() else []
    return {"doc_count": len(docs), "docs": docs,
            "initialized": len(docs) > 0}


def collect_env(env_path: Path) -> dict:
    values = env_config.load_env_file(str(env_path))
    present: dict[str, bool] = {}
    for k in SECRET_KEYS:
        # 값 노출 없이 존재 여부만. 프로세스 환경변수도 함께 본다.
        present[k] = env_config.get(k, env_values=values) is not None
    return {"path": str(env_path), "exists": env_path.exists(), "keys": present}


def _tool_version(cmd: list[str]) -> str | None:
    exe = cmd[0]
    if shutil.which(exe) is None and not Path(exe).exists():
        return None
    try:
        proc = subprocess.run(cmd, capture_output=True, text=True, timeout=15)
    except (OSError, subprocess.TimeoutExpired):
        return None
    out = (proc.stdout or proc.stderr).strip().splitlines()
    return out[0].strip() if out else None


def collect_tools() -> dict:
    godot = os.environ.get("GODOT_BIN", "godot")
    return {
        "godot": _tool_version([godot, "--version"]),
        "ffmpeg": _tool_version([os.environ.get("FFMPEG_BIN", "ffmpeg"), "-version"]),
        "node": _tool_version([os.environ.get("NODE_BIN", "node"), "--version"]),
    }


def collect_runners(tests_dir: Path) -> list[str]:
    if not tests_dir.exists():
        return []
    return sorted(p.name for p in tests_dir.glob("run_*.py"))


def gather(project_dir: Path, manifest_path: Path, env_path: Path) -> dict:
    return {
        "project": str(project_dir),
        "manifest": collect_manifest(manifest_path),
        "specs": collect_specs(project_dir / "docs" / "specs"),
        "lore": collect_lore(project_dir / "lore" / "canon"),
        "env": collect_env(env_path),
        "tools": collect_tools(),
        "runners": collect_runners(project_dir / "pipeline" / "tests"),
    }


# ---------------------------------------------------------------------------
# 사람용 텍스트 렌더
# ---------------------------------------------------------------------------
def render_text(data: dict) -> str:
    L: list[str] = []
    L.append("=" * 64)
    L.append("status — 프로젝트 현황")
    L.append(f"프로젝트: {data['project']}")
    L.append("=" * 64)

    m = data["manifest"]
    L.append("[매니페스트]")
    if m.get("error"):
        L.append(f"  (로드 실패: {m['error']})")
    else:
        L.append(f"  총 entry: {m['total']}개")
        if m["by_track"]:
            tracks = " · ".join(f"{k} {len(v)}" for k, v in sorted(m["by_track"].items()))
            L.append(f"  트랙별: {tracks}")
        if m["by_status"]:
            for st in ("placeholder", "generated", "approved", "rejected"):
                ids = m["by_status"].get(st)
                if ids:
                    L.append(f"    - {st}: {len(ids)}  [{', '.join(ids)}]")
        sg = m.get("style_guide")
        L.append(f"  art lock(style_guide): {'설정됨 → ' + sg if sg else '미설정 (art lock 대기)'}")

    L.append("[스펙(docs/specs)]")
    if data["specs"]:
        for s in data["specs"]:
            L.append(f"  - {s['name']}: {s['status']}")
    else:
        L.append("  (스펙 문서 없음)")

    lore = data["lore"]
    L.append("[lore/canon]")
    L.append(f"  정본 문서 {lore['doc_count']}개"
             + (f" ({', '.join(lore['docs'])})" if lore["docs"] else " — 미초기화(lore init 대기)"))

    env = data["env"]
    L.append("[.env 키 (존재 여부만, 값 미노출)]")
    L.append(f"  경로: {env['path']} ({'있음' if env['exists'] else '없음'})")
    for k, present in env["keys"].items():
        L.append(f"    - {k}: {'설정됨' if present else '미설정'}")

    tools = data["tools"]
    L.append("[도구 버전]")
    for name in ("godot", "ffmpeg", "node"):
        L.append(f"  - {name}: {tools.get(name) or '(미설치/미발견)'}")

    L.append("[테스트 러너]")
    if data["runners"]:
        for r in data["runners"]:
            L.append(f"  - {r}")
    else:
        L.append("  (러너 없음)")

    return "\n".join(L)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def main(argv: list[str] | None = None) -> int:
    root = _repo_root()
    parser = argparse.ArgumentParser(
        prog="status.py",
        description="프로젝트·태스크 현황 리포터 (읽기 전용). 비밀값은 존재 여부만 노출.",
    )
    parser.add_argument("--project", default=str(root), help="프로젝트 루트")
    parser.add_argument("--manifest", default=None,
                        help="기본: <project>/pipeline/manifest.json")
    parser.add_argument("--env", default=None, help="기본: <project>/.env")
    parser.add_argument("--json", action="store_true", help="JSON 출력")
    args = parser.parse_args(argv)

    project_dir = Path(args.project).resolve()
    manifest_path = (
        Path(args.manifest) if args.manifest
        else project_dir / "pipeline" / "manifest.json"
    )
    env_path = Path(args.env) if args.env else project_dir / ".env"

    data = gather(project_dir, manifest_path, env_path)

    if args.json:
        print(json.dumps(data, ensure_ascii=False, indent=2))
    else:
        print(render_text(data))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
