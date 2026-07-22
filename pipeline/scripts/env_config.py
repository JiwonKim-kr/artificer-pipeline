#!/usr/bin/env python3
"""`.env` 로더 공용 헬퍼 (stdlib 전용, Python 3.14).

API 키 등 비밀값은 저장소에 커밋하지 않고 `.env`(루트, `.gitignore` 등재)로만
관리한다. 이 모듈은 그 `.env` 를 읽어 `KEY=value` 로 파싱하는 **유일한 공용 창구**다.
art 트랙의 `scenario_client.py` 가 처음 쓰고, 이후 se 트랙(ElevenLabs 등)도
그대로 재사용하도록 트랙 비의존(범용)으로 설계했다. (HANDOFF §7, CLAUDE.md)

설계 원칙:
  - **키 부재는 크래시가 아니다.** 파일이 없으면 빈 dict 를 돌려주고, 필수 키가
    없으면 스택트레이스 대신 `MissingKeysError`(호출자가 한국어 안내 + 종료 코드로
    변환)로 신호한다.
  - **비밀값을 로그에 남기지 않는다.** 표시가 필요하면 `mask()` 로 마스킹한다.
  - 우선순위: **실제 프로세스 환경변수 > `.env` 파일값**. (표준 dotenv 관례 —
    `.env` 는 이미 존재하는 환경변수를 덮어쓰지 않는다.) 테스트는 `environ`/`path`
    를 주입해 완전 격리(hermetic)로 검증한다.

파싱 규칙 (관대하게):
  - 빈 줄·`#` 주석 줄 무시. 앞뒤 공백 허용.
  - `export KEY=value` 의 `export ` 접두사 허용.
  - `KEY = value` 처럼 `=` 양옆 공백 허용.
  - 값이 따옴표(`"..."` / `'...'`)로 감싸지면 벗겨낸다(따옴표 안 공백은 보존).
  - 따옴표 없는 값의 `#` 인라인 주석은 (공백 뒤에서) 제거. 따옴표 값은 그대로.

CLI:
  get   <KEY>            값 출력(있으면), 없으면 종료 코드 3
  check --keys A,B       키 존재 여부를 마스킹해 보고 (전부 있으면 0, 하나라도 없으면 3)
  path                   해석된 `.env` 경로와 존재 여부 출력

종료 코드: 0 = 성공, 2 = 실행 오류(인자 등), 3 = 요청 키 부재.
"""
from __future__ import annotations

import argparse
import os
import sys
from pathlib import Path

DEFAULT_ENV_FILENAME = ".env"


# ---------------------------------------------------------------------------
# 경로 기본값
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    # pipeline/scripts/env_config.py -> repo_root
    return Path(__file__).resolve().parents[2]


def default_env_path() -> Path:
    """저장소 루트의 `.env` 경로(존재 여부와 무관하게 경로만 반환)."""
    return _repo_root() / DEFAULT_ENV_FILENAME


# ---------------------------------------------------------------------------
# 파싱
# ---------------------------------------------------------------------------
def _strip_inline_comment(value: str) -> str:
    """따옴표 없는 값에서 ' #...' 형태의 인라인 주석을 제거한다."""
    out_chars: list[str] = []
    for i, ch in enumerate(value):
        if ch == "#" and (i == 0 or value[i - 1].isspace()):
            break
        out_chars.append(ch)
    return "".join(out_chars).rstrip()


def _unquote(value: str) -> str:
    """따옴표 값이면 여는~닫는 따옴표 사이만 취하고 이후(주석/공백)는 버린다.
    따옴표가 없으면 인라인 주석을 제거한다."""
    value = value.strip()
    if value and value[0] in ("'", '"'):
        quote = value[0]
        end = value.find(quote, 1)
        if end != -1:
            return value[1:end]  # 닫는 따옴표 뒤(예: '  # inline')는 무시
        return value[1:]         # 닫는 따옴표 없는 비정상 값: 여는 따옴표만 제거
    return _strip_inline_comment(value)


def parse_env_text(text: str) -> dict[str, str]:
    """`.env` 텍스트를 {KEY: value} 로 파싱한다. 형식 오류 줄은 조용히 건너뛴다."""
    result: dict[str, str] = {}
    for raw in text.splitlines():
        line = raw.strip()
        if not line or line.startswith("#"):
            continue
        if line.startswith("export "):
            line = line[len("export "):].lstrip()
        if "=" not in line:
            continue  # KEY 만 있고 = 가 없는 줄은 무시
        key, _, value = line.partition("=")
        key = key.strip()
        if not key:
            continue
        result[key] = _unquote(value.strip())
    return result


def load_env_file(path: str | os.PathLike[str] | None = None) -> dict[str, str]:
    """`.env` 파일을 읽어 dict 로 반환. **파일이 없으면 빈 dict**(크래시 없음)."""
    p = Path(path) if path is not None else default_env_path()
    if not p.exists() or not p.is_file():
        return {}
    try:
        return parse_env_text(p.read_text(encoding="utf-8"))
    except OSError:
        return {}


# ---------------------------------------------------------------------------
# 조회 / 요구
# ---------------------------------------------------------------------------
def get(
    key: str,
    *,
    path: str | os.PathLike[str] | None = None,
    env_values: dict[str, str] | None = None,
    environ: dict[str, str] | None = None,
    default: str | None = None,
) -> str | None:
    """단일 키 조회. 우선순위: 프로세스 환경변수 > `.env` 값 > default.

    `env_values`/`environ` 를 주입하면 파일/OS 접근 없이 순수 조회가 되어 테스트에
    유리하다. 빈 문자열("")은 '미설정'으로 간주한다(키만 있고 값이 없는 경우 방지).
    """
    environ = os.environ if environ is None else environ
    env_values = load_env_file(path) if env_values is None else env_values

    v = environ.get(key)
    if v:
        return v
    v = env_values.get(key)
    if v:
        return v
    return default


class MissingKeysError(Exception):
    """필수 키가 없을 때 발생. 호출자가 안내 문구 + 종료 코드로 변환한다."""

    def __init__(self, keys: list[str], env_path: Path | None = None):
        self.keys = keys
        self.env_path = env_path
        super().__init__(f"필수 환경변수 누락: {', '.join(keys)}")

    def render(self, guidance: str = "") -> str:
        """사람이 읽을 한국어 안내문. `guidance` 로 트랙별 발급 안내를 덧붙인다."""
        lines = [
            f"[env] 필수 환경변수가 없습니다: {', '.join(self.keys)}",
        ]
        if self.env_path is not None:
            lines.append(f"      확인한 .env 경로: {self.env_path}")
        if guidance:
            lines.append(guidance.rstrip())
        return "\n".join(lines)


def require(
    keys: list[str],
    *,
    path: str | os.PathLike[str] | None = None,
    environ: dict[str, str] | None = None,
) -> dict[str, str]:
    """여러 키를 한 번에 요구. 하나라도 없으면 `MissingKeysError`.

    반환: {key: value} (모두 존재할 때만).
    """
    resolved_path = Path(path) if path is not None else default_env_path()
    env_values = load_env_file(resolved_path)
    found: dict[str, str] = {}
    missing: list[str] = []
    for k in keys:
        v = get(k, env_values=env_values, environ=environ)
        if v is None:
            missing.append(k)
        else:
            found[k] = v
    if missing:
        raise MissingKeysError(missing, resolved_path)
    return found


def mask(value: str | None, *, show: int = 4) -> str:
    """비밀값을 로그에 안전하게 표시. 앞 `show` 글자만 남기고 나머지는 *."""
    if not value:
        return "(미설정)"
    if len(value) <= show:
        return "*" * len(value)
    return value[:show] + "*" * (len(value) - show)


# ---------------------------------------------------------------------------
# CLI
# ---------------------------------------------------------------------------
def _split_keys(raw: str) -> list[str]:
    return [k.strip() for k in raw.split(",") if k.strip()]


def _cmd_get(args: argparse.Namespace) -> int:
    v = get(args.key, path=args.path)
    if v is None:
        print(f"(키 없음: {args.key})", file=sys.stderr)
        return 3
    print(v)
    return 0


def _cmd_check(args: argparse.Namespace) -> int:
    keys = _split_keys(args.keys)
    if not keys:
        print("오류: --keys 가 비었습니다.", file=sys.stderr)
        return 2
    resolved_path = Path(args.path) if args.path else default_env_path()
    env_values = load_env_file(resolved_path)
    missing: list[str] = []
    print(f".env 경로: {resolved_path} ({'있음' if resolved_path.exists() else '없음'})")
    for k in keys:
        v = get(k, env_values=env_values)
        if v is None:
            missing.append(k)
            print(f"  [MISSING] {k}")
        else:
            print(f"  [OK]      {k} = {mask(v)}")
    if missing:
        print(f"누락 {len(missing)}개: {', '.join(missing)}", file=sys.stderr)
        return 3
    return 0


def _cmd_path(args: argparse.Namespace) -> int:
    p = Path(args.path) if args.path else default_env_path()
    print(f"{p} ({'있음' if p.exists() else '없음'})")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="env_config.py",
        description=".env 로더 공용 헬퍼 (stdlib). 비밀값은 마스킹해서만 표시.",
    )
    p.add_argument("--path", default=None, help=".env 경로 (기본: <repo>/.env)")
    sub = p.add_subparsers(dest="command", required=True)

    pg = sub.add_parser("get", help="단일 키 값 출력 (없으면 종료 코드 3)")
    pg.add_argument("key")
    pg.set_defaults(func=_cmd_get)

    pc = sub.add_parser("check", help="키 존재 여부를 마스킹해 보고")
    pc.add_argument("--keys", required=True, metavar="A,B,C", help="쉼표로 구분")
    pc.set_defaults(func=_cmd_check)

    pp = sub.add_parser("path", help="해석된 .env 경로 출력")
    pp.set_defaults(func=_cmd_path)
    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except OSError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
