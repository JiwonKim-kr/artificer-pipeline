#!/usr/bin/env python3
"""se jsfxr 백엔드 Python 래퍼 — 파라미터/프리셋 JSON → WAV (재현 가능).

`se gen` 의 절차적(레트로 톤) 백엔드다. 검증 게임이 픽셀아트로 확정되어
ElevenLabs SFX 와 병행 활성화됐다 (HANDOFF §2, §6-2). 실제 합성은 Node 쪽
`pipeline/scripts/se_node/render_sfxr.js`(jsfxr@1.4.1, 퍼블릭 도메인, 의존성 0)가
수행하고, 이 래퍼는 Claude/파이프라인이 부르는 Python 창구를 제공한다.

재현성 보장: render_sfxr.js 가 jsfxr 로드 전에 Math.random 을 시드된
PRNG(mulberry32)로 교체하므로 **seed + preset(+params) 고정 → 동일 WAV 바이트**.
렌더 결과의 `resolved_params` 를 spec 으로 되먹여도 동일 WAV 가 나온다.
(→ 매니페스트 entry `params.jsfxr` 에 기록해 재생성 근거로 쓴다.)

장르/이벤트 하드코딩 없음 — 프리셋·시드·파라미터는 전부 spec(데이터)으로 받는다.

CLI 서브커맨드:
  check    Node 실행 환경 + jsfxr 설치 여부 보고 (미비 시 한국어 안내, 종료 코드 3)
  presets  사용 가능한 jsfxr 표준 프리셋 목록
  render   spec JSON → WAV 렌더 (+ 렌더 기록 JSON stdout / --save-params)

spec JSON 형식(모든 필드 선택): {"seed": int, "preset": str, "params": {...},
  "sound_vol": f, "sample_rate": int, "sample_size": int}

종료 코드: 0 = 성공, 1 = 렌더 실패, 2 = 실행/인자 오류,
          3 = 미설정(node 또는 jsfxr 미설치 — scenario_client 의 키 부재와 동일 체계).
stdlib 만 사용 (Python 3.14). Node 는 NODE_BIN 으로 재정의 가능.
"""
from __future__ import annotations

import argparse
import json
import os
import shutil
import subprocess
import sys
from pathlib import Path

# jsfxr 표준 프리셋 (render_sfxr.js 의 PRESETS 와 동일해야 한다)
PRESETS = [
    "pickupCoin", "laserShoot", "explosion", "powerUp",
    "hitHurt", "jump", "blipSelect", "synth", "tone", "click", "random",
]

_INSTALL_GUIDANCE = (
    "      jsfxr 백엔드 준비 방법:\n"
    "        1) Node 18+ 설치 확인: node --version\n"
    "        2) cd pipeline/scripts/se_node && npm install\n"
    "      (node_modules/ 는 .gitignore 등재 — 저장소에 커밋하지 않는다.)\n"
    "      Node 실행 파일 경로가 다르면 NODE_BIN 환경변수로 지정하세요."
)


def _node_dir() -> Path:
    # pipeline/scripts/se_jsfxr.py -> pipeline/scripts/se_node
    return Path(__file__).resolve().parent / "se_node"


def _node_bin() -> str:
    return os.environ.get("NODE_BIN", "node")


def _render_script() -> Path:
    return _node_dir() / "render_sfxr.js"


def check_runtime() -> list[str]:
    """실행 환경 문제 목록을 반환한다(빈 리스트 = 준비 완료)."""
    problems: list[str] = []
    node = _node_bin()
    if shutil.which(node) is None and not Path(node).exists():
        problems.append(f"node 실행 파일을 찾을 수 없음: {node!r}")
    if not _render_script().exists():
        problems.append(f"렌더 스크립트 없음: {_render_script()}")
    if not (_node_dir() / "node_modules" / "jsfxr").exists():
        problems.append(f"jsfxr 미설치: {_node_dir() / 'node_modules' / 'jsfxr'}")
    return problems


def render(
    spec: dict,
    out_path: Path,
    *,
    timeout: float = 60.0,
) -> dict:
    """spec 을 render_sfxr.js 로 렌더하고 렌더 기록(dict)을 반환한다.

    RuntimeError = 렌더 실패. 호출 전 check_runtime() 이 비어 있어야 한다.
    """
    proc = subprocess.run(
        [_node_bin(), str(_render_script()), "-", str(out_path)],
        input=json.dumps(spec),
        capture_output=True, text=True, timeout=timeout,
    )
    if proc.returncode != 0:
        raise RuntimeError(
            f"render_sfxr.js 실패(exit={proc.returncode}): {proc.stderr.strip()[-500:]}"
        )
    try:
        return json.loads(proc.stdout)
    except json.JSONDecodeError as exc:
        raise RuntimeError(f"렌더 기록 JSON 파싱 실패: {exc}") from exc


# ---------------------------------------------------------------------------
# CLI 핸들러
# ---------------------------------------------------------------------------
def _require_runtime_or_exit() -> int | None:
    problems = check_runtime()
    if problems:
        print("[se_jsfxr] jsfxr 백엔드 실행 환경이 준비되지 않았습니다:", file=sys.stderr)
        for p in problems:
            print(f"      - {p}", file=sys.stderr)
        print(_INSTALL_GUIDANCE, file=sys.stderr)
        return 3
    return None


def _cmd_check(args: argparse.Namespace) -> int:
    problems = check_runtime()
    print(f"node: {_node_bin()} "
          f"({'있음' if shutil.which(_node_bin()) or Path(_node_bin()).exists() else '없음'})")
    print(f"렌더 스크립트: {_render_script()} ({'있음' if _render_script().exists() else '없음'})")
    jm = _node_dir() / "node_modules" / "jsfxr"
    print(f"jsfxr 모듈: {jm} ({'있음' if jm.exists() else '없음'})")
    if problems:
        print("→ 준비 안 됨:", file=sys.stderr)
        print(_INSTALL_GUIDANCE, file=sys.stderr)
        return 3
    print("→ 준비 완료")
    return 0


def _cmd_presets(args: argparse.Namespace) -> int:
    if args.json:
        print(json.dumps(PRESETS, ensure_ascii=False))
    else:
        print("jsfxr 표준 프리셋:")
        for p in PRESETS:
            print(f"  - {p}")
        print("(재현이 필요하면 'random' 결과의 resolved_params 를 spec 으로 저장해 쓰세요. "
              "seed 고정 시 어떤 프리셋도 결정적입니다.)")
    return 0


def _cmd_render(args: argparse.Namespace) -> int:
    rc = _require_runtime_or_exit()
    if rc is not None:
        return rc

    # spec 로드: --spec 파일('-'=stdin) 또는 빈 spec 에서 시작
    if args.spec == "-":
        raw = sys.stdin.read()
    elif args.spec:
        p = Path(args.spec)
        if not p.exists():
            print(f"오류: spec 파일이 없습니다: {p}", file=sys.stderr)
            return 2
        raw = p.read_text(encoding="utf-8")
    else:
        raw = "{}"
    try:
        spec = json.loads(raw)
    except json.JSONDecodeError as exc:
        print(f"오류: spec JSON 파싱 실패: {exc}", file=sys.stderr)
        return 2
    if not isinstance(spec, dict):
        print("오류: spec 최상위는 객체여야 합니다.", file=sys.stderr)
        return 2

    # CLI 오버라이드 (데이터 우선 원칙: 인자 > spec 파일)
    if args.preset is not None:
        if args.preset not in PRESETS:
            print(f"오류: 알 수 없는 preset: {args.preset} "
                  f"(가능: {', '.join(PRESETS)})", file=sys.stderr)
            return 2
        spec["preset"] = args.preset
    if args.seed is not None:
        spec["seed"] = args.seed

    if not spec.get("preset") and not spec.get("params"):
        print("오류: spec 에 preset 또는 params 중 하나는 있어야 합니다.", file=sys.stderr)
        return 2

    out = Path(args.out)
    try:
        record = render(spec, out, timeout=args.timeout)
    except (RuntimeError, subprocess.TimeoutExpired) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 1

    if args.save_params:
        # 재현 spec: {seed, params=resolved} — 이대로 render 하면 동일 WAV.
        repro = {"seed": record.get("seed", 0), "params": record.get("resolved_params", {})}
        sp = Path(args.save_params)
        sp.parent.mkdir(parents=True, exist_ok=True)
        sp.write_text(json.dumps(repro, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
        record["saved_params"] = str(sp)

    print(json.dumps(record, ensure_ascii=False))
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="se_jsfxr.py",
        description="jsfxr 절차적 SE 백엔드 래퍼 — spec JSON → WAV (seed 고정 시 재현 가능)",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pc = sub.add_parser("check", help="node + jsfxr 설치 여부 보고 (미비 시 종료 코드 3)")
    pc.set_defaults(func=_cmd_check)

    pp = sub.add_parser("presets", help="jsfxr 표준 프리셋 목록")
    pp.add_argument("--json", action="store_true")
    pp.set_defaults(func=_cmd_presets)

    pr = sub.add_parser("render", help="spec JSON → WAV 렌더")
    pr.add_argument("--spec", default=None, help="spec JSON 경로 ('-'=stdin, 생략 시 빈 spec)")
    pr.add_argument("--out", required=True, help="출력 WAV 경로")
    pr.add_argument("--preset", default=None, help=f"프리셋 오버라이드 ({', '.join(PRESETS)})")
    pr.add_argument("--seed", type=int, default=None, help="시드 오버라이드 (재현 키)")
    pr.add_argument("--save-params", default=None, metavar="PATH",
                    help="재현 spec(JSON: seed+resolved params)을 이 경로에 저장")
    pr.add_argument("--timeout", type=float, default=60.0)
    pr.set_defaults(func=_cmd_render)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except KeyboardInterrupt:
        print("중단됨.", file=sys.stderr)
        return 2
    except OSError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
