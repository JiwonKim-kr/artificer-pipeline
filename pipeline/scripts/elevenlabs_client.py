#!/usr/bin/env python3
"""ElevenLabs SFX API 클라이언트 (stdlib `urllib` 전용, Python 3.14).

se 트랙의 프롬프트 기반 기본 백엔드다 — `se gen` 의 텍스트 명세를 그대로
효과음 생성 요청으로 잇는다 (HANDOFF §2, §6-2: ElevenLabs SFX 기본 +
jsfxr 병행). 절차적(레트로 톤) 백엔드는 `se_jsfxr.py` 참조.

────────────────────────────────────────────────────────────────────────────
설계 핵심 — scenario_client.py 와 동일하게 **라이브 호출 없이 검증 가능**.
  · `prepare_*()`  : 순수 함수. (method, url, headers, body) 를 담은
                     `PreparedRequest` 를 만든다. 네트워크·키 없이 단위 검증 가능.
  · `send_*()`     : 실제 urllib 전송. 키·네트워크 오류를 graceful 하게 처리.
                     (sound-generation 응답은 JSON 이 아니라 **오디오 바이트**다.)
  · `--dry-run`    : prepare 결과만(비밀값 마스킹) 출력하고 전송하지 않는다.
키가 없으면 스택트레이스 없이 한국어 안내 + 종료 코드 3 으로 끝난다.
────────────────────────────────────────────────────────────────────────────

종료 코드: 0 = 성공, 1 = API/HTTP/네트워크 오류, 2 = 실행/인자 오류,
          3 = 미설정(ELEVENLABS_API_KEY 부재).  (scenario_client 와 동일 체계)
"""
from __future__ import annotations

import argparse
import json
import os
import sys
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env_config  # noqa: E402

# ===========================================================================
# 엔드포인트 단일 진실 공급원 (SINGLE SOURCE OF TRUTH)
# ---------------------------------------------------------------------------
# ⚠️ TODO(라이브 검증 필요): 아래 경로/파라미터는 공개 문서(elevenlabs.io/docs)
#    기억 기준이며 키 미발급으로 실호출 검증을 하지 못했다. 키 발급 후 반드시:
#    - POST /v1/sound-generation 경로·요청 바디(text, duration_seconds,
#      prompt_influence)·output_format 쿼리 지원 여부를 실호출로 확인할 것.
#    - check-auth 용 GET /v1/user 응답 스키마 확인.
#    - 응답이 오디오 바이트 스트림(기본 mp3)인지, 포맷 협상 방법 확인.
#    이 블록 밖에는 하드코딩된 URL 을 두지 않는다. (수정 지점 단일화)
# ===========================================================================
_DEFAULT_BASE = "https://api.elevenlabs.io/v1"


class Api:
    """URL 빌더. 모든 경로는 여기서만 조립한다."""

    @staticmethod
    def base() -> str:
        # 테스트/미러링을 위해 ELEVENLABS_API_BASE 로 재정의 가능.
        return (env_config.get("ELEVENLABS_API_BASE") or _DEFAULT_BASE).rstrip("/")

    @classmethod
    def sound_generation(cls, output_format: str | None = None) -> str:
        # TODO(라이브 검증 필요): output_format 쿼리 파라미터 지원 여부.
        url = f"{cls.base()}/sound-generation"
        if output_format:
            url += "?" + urllib.parse.urlencode({"output_format": output_format})
        return url

    @classmethod
    def user(cls) -> str:
        # check-auth 용 경량 인증 확인 엔드포인트.
        return f"{cls.base()}/user"


REQUIRED_KEYS = ["ELEVENLABS_API_KEY"]

_ISSUE_GUIDANCE = (
    "      ElevenLabs API 키 발급 방법:\n"
    "        1) https://elevenlabs.io 로그인 → 좌하단 프로필 → API Keys\n"
    "        2) 'Create API Key' 로 키 발급 (SFX(sound-generation) 접근 가능 플랜 확인)\n"
    "      저장소 루트에 .env 파일을 만들고 아래 형식으로 기입 (.gitignore 등재됨, 커밋 금지):\n"
    "        ELEVENLABS_API_KEY=발급받은_KEY\n"
    "      키 없이 요청 구성만 확인하려면 각 명령에 --dry-run 을 붙이세요."
)


# ---------------------------------------------------------------------------
# 예외 / 요청 표현
# ---------------------------------------------------------------------------
class ElevenLabsApiError(Exception):
    """HTTP/네트워크 오류. CLI 는 종료 코드 1 로 변환한다."""

    def __init__(self, message: str, *, status: int | None = None):
        self.status = status
        super().__init__(message)


@dataclass
class PreparedRequest:
    """전송 전 요청. 네트워크 없이 검증·표시 가능."""

    method: str
    url: str
    headers: dict[str, str] = field(default_factory=dict)
    body: dict | None = None  # JSON 직렬화 대상. None 이면 바디 없음.

    def to_display(self) -> dict:
        """비밀값(xi-api-key)을 마스킹한 표시용 dict."""
        headers = dict(self.headers)
        if "xi-api-key" in headers:
            headers["xi-api-key"] = env_config.mask(headers["xi-api-key"])
        return {"method": self.method, "url": self.url, "headers": headers, "body": self.body}


# ---------------------------------------------------------------------------
# 인증 (헤더 방식: xi-api-key)
# ---------------------------------------------------------------------------
def resolve_api_key(
    *, path: str | None = None, environ: dict[str, str] | None = None
) -> str:
    """`.env`/환경변수에서 키를 읽는다. 없으면 `env_config.MissingKeysError`."""
    creds = env_config.require(REQUIRED_KEYS, path=path, environ=environ)
    return creds["ELEVENLABS_API_KEY"]


def _json_headers(api_key: str) -> dict[str, str]:
    return {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "application/json",
    }


def _audio_headers(api_key: str) -> dict[str, str]:
    # sound-generation 응답은 오디오 바이트 (기본 mp3). Accept 는 명시적 표시용.
    return {
        "xi-api-key": api_key,
        "Content-Type": "application/json",
        "Accept": "audio/mpeg",
    }


# ---------------------------------------------------------------------------
# prepare_* (순수 — 네트워크 없음, 단위 검증 대상)
# ---------------------------------------------------------------------------
def prepare_sound_generation(
    *,
    text: str,
    api_key: str,
    duration_seconds: float | None = None,
    prompt_influence: float | None = None,
    output_format: str | None = None,
) -> PreparedRequest:
    """SFX 생성 요청 구성 (text → sound effect).

    duration_seconds: 생략 시 서버가 텍스트에서 자동 판단(문서 기준 0.5~22s).
    prompt_influence: 0~1. 높을수록 프롬프트에 충실(기본 0.3, 서버 기본값 위임).
    """
    if not text.strip():
        raise ValueError("text 가 비어 있습니다.")
    body: dict = {"text": text}
    if duration_seconds is not None:
        body["duration_seconds"] = duration_seconds
    if prompt_influence is not None:
        body["prompt_influence"] = prompt_influence
    return PreparedRequest(
        "POST", Api.sound_generation(output_format), _audio_headers(api_key), body
    )


def prepare_user_info(api_key: str) -> PreparedRequest:
    """check-auth 용 경량 요청 (GET /v1/user)."""
    return PreparedRequest("GET", Api.user(), _json_headers(api_key))


# ---------------------------------------------------------------------------
# 전송 (실제 네트워크)
# ---------------------------------------------------------------------------
def _open(prepared: PreparedRequest, *, timeout: float):
    data = None
    if prepared.body is not None:
        data = json.dumps(prepared.body).encode("utf-8")
    req = urllib.request.Request(
        prepared.url, data=data, headers=prepared.headers, method=prepared.method
    )
    return urllib.request.urlopen(req, timeout=timeout)


def _raise_api_error(prepared: PreparedRequest, exc: Exception) -> None:
    if isinstance(exc, urllib.error.HTTPError):
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:  # noqa: BLE001 - 진단용 부가정보일 뿐
            pass
        hint = " (인증 실패 — 키 확인)" if exc.code in (401, 403) else ""
        raise ElevenLabsApiError(
            f"HTTP {exc.code}{hint}: {prepared.method} {prepared.url}\n{detail}",
            status=exc.code,
        ) from exc
    if isinstance(exc, urllib.error.URLError):
        raise ElevenLabsApiError(f"네트워크 오류: {exc.reason} ({prepared.url})") from exc
    if isinstance(exc, TimeoutError):
        raise ElevenLabsApiError(f"요청 타임아웃: {prepared.url}") from exc
    raise exc


def send_json(prepared: PreparedRequest, *, timeout: float = 60.0) -> dict:
    """JSON 응답 요청 전송 (check-auth 등). 오류는 ElevenLabsApiError."""
    try:
        with _open(prepared, timeout=timeout) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        _raise_api_error(prepared, exc)
        raise  # unreachable — 타입 체커용
    except json.JSONDecodeError as exc:
        raise ElevenLabsApiError(f"응답 JSON 파싱 실패: {exc}") from exc


def send_audio(prepared: PreparedRequest, dest: Path, *, timeout: float = 120.0) -> int:
    """오디오 바이트 응답 요청 전송(sound-generation) → dest 저장. 바이트 수 반환."""
    try:
        with _open(prepared, timeout=timeout) as resp:
            payload: bytes = resp.read()
    except (urllib.error.HTTPError, urllib.error.URLError, TimeoutError) as exc:
        _raise_api_error(prepared, exc)
        raise  # unreachable
    if not payload:
        raise ElevenLabsApiError("응답이 비어 있습니다 (오디오 바이트 없음).")
    dest.parent.mkdir(parents=True, exist_ok=True)
    dest.write_bytes(payload)
    return len(payload)


# ---------------------------------------------------------------------------
# 표시 헬퍼
# ---------------------------------------------------------------------------
def _print_dry_run(title: str, prepared: PreparedRequest) -> None:
    print(f"[dry-run] {title} — 전송하지 않고 요청 구성만 출력합니다:")
    print("  " + json.dumps(prepared.to_display(), ensure_ascii=False, indent=2)
          .replace("\n", "\n  "))


# ---------------------------------------------------------------------------
# CLI 핸들러
# ---------------------------------------------------------------------------
def _resolve_key_or_exit(args: argparse.Namespace) -> str | int:
    """API 키를 반환하거나, 미설정이면 안내 후 종료 코드(3)를 반환."""
    try:
        return resolve_api_key(path=args.env)
    except env_config.MissingKeysError as exc:
        print(exc.render(_ISSUE_GUIDANCE), file=sys.stderr)
        return 3


def _cmd_check_auth(args: argparse.Namespace) -> int:
    key = _resolve_key_or_exit(args)
    if isinstance(key, int):
        return key
    prepared = prepare_user_info(key)
    if args.dry_run:
        _print_dry_run("check-auth (GET /user)", prepared)
        print("키는 존재합니다. 실제 인증 확인은 --dry-run 없이 실행하세요.")
        return 0
    try:
        info = send_json(prepared, timeout=args.timeout)
    except ElevenLabsApiError as exc:
        print(f"인증 확인 실패: {exc}", file=sys.stderr)
        return 1
    # TODO(라이브 검증 필요): /user 응답 스키마 확인 후 유용한 필드만 출력.
    sub = info.get("subscription") or {}
    tier = sub.get("tier") or "(unknown)"
    print(f"인증 성공: 자격 증명이 유효합니다. (tier={tier})")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    key = _resolve_key_or_exit(args)
    if isinstance(key, int):
        return key
    try:
        prepared = prepare_sound_generation(
            text=args.text,
            api_key=key,
            duration_seconds=args.duration,
            prompt_influence=args.prompt_influence,
            output_format=args.output_format,
        )
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2
    if args.dry_run:
        _print_dry_run("sound-generation", prepared)
        return 0
    dest = Path(args.out)
    try:
        n = send_audio(prepared, dest, timeout=args.timeout)
    except ElevenLabsApiError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
        return 1
    print(f"저장됨: {dest} ({n} bytes)")
    print("다음 단계: se_post.py normalize 로 OGG Vorbis 모노 -16 LUFS 정규화 "
          "(conventions.md 오디오 규격).")
    return 0


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def _add_common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--env", default=None, help=".env 경로 (기본: <repo>/.env)")
    sp.add_argument("--dry-run", action="store_true", help="전송하지 않고 요청 구성만 출력")
    sp.add_argument("--timeout", type=float, default=120.0, help="요청 타임아웃(초)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="elevenlabs_client.py",
        description="ElevenLabs SFX API 클라이언트 (urllib). 키 부재/네트워크 오류 graceful. "
                    "--dry-run 으로 라이브 없이 요청 구성 검증.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("check-auth", help="키 검증 (경량 인증 요청)")
    _add_common(pa)
    pa.set_defaults(func=_cmd_check_auth)

    pg = sub.add_parser("generate", help="텍스트 명세 → 효과음 생성·다운로드")
    _add_common(pg)
    pg.add_argument("--text", required=True, help="효과음 텍스트 명세 (프롬프트)")
    pg.add_argument("--duration", type=float, default=None,
                    help="길이(초). 생략 시 서버 자동 판단 (문서 기준 0.5~22)")
    pg.add_argument("--prompt-influence", type=float, default=None,
                    help="0~1. 높을수록 프롬프트 충실 (생략 시 서버 기본값)")
    pg.add_argument("--output-format", default=None,
                    help="예: mp3_44100_128 (라이브 검증 필요 — 지원 값 확인 후 사용)")
    pg.add_argument("--out", default="sound.mp3", help="응답 오디오 저장 경로")
    pg.set_defaults(func=_cmd_generate)

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
