#!/usr/bin/env python3
"""Scenario API 클라이언트 (stdlib `urllib` 전용, Python 3.14).

art 트랙의 `art lock`(커스텀 스타일 모델 학습) / `art gen`(커스텀 모델 생성) /
플랫폼 후처리(배경 제거)를 위한 Scenario 플랫폼 REST 호출 창구다. (HANDOFF §2, §6-1)

────────────────────────────────────────────────────────────────────────────
설계 핵심 — **라이브 호출 없이 검증 가능**하도록 요청 구성과 전송을 분리했다.
  · `prepare_*()`  : 순수 함수. (method, url, headers, body) 를 담은
                     `PreparedRequest` 를 만든다. 네트워크·키 없이 단위 검증 가능.
  · `send()`       : 실제 urllib 전송. 키·네트워크 오류를 graceful 하게 처리.
  · `--dry-run`    : prepare 결과만(비밀값 마스킹) 출력하고 전송하지 않는다.
키가 없으면 스택트레이스 없이 한국어 안내 + 종료 코드 3 으로 끝난다.
────────────────────────────────────────────────────────────────────────────

종료 코드: 0 = 성공, 1 = API/HTTP/네트워크 오류, 2 = 실행/인자 오류,
          3 = 미설정(SCENARIO_API_KEY/SECRET 부재).
"""
from __future__ import annotations

import argparse
import base64
import json
import mimetypes
import os
import sys
import time
import ssl
import urllib.error
import urllib.parse
import urllib.request
from dataclasses import dataclass, field
from pathlib import Path

sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))
import env_config  # noqa: E402

# macOS 등에서 Python 이 시스템 CA 번들을 못 찾아 SSL 검증이 실패하는 것을 막는다.
# certifi 가 있으면 그 CA 로 컨텍스트를 구성하고, 없으면 시스템 기본(None)을 쓴다.
try:
    import certifi  # noqa: E402
    _SSL_CTX: ssl.SSLContext | None = ssl.create_default_context(cafile=certifi.where())
except Exception:  # certifi 미설치 등 — 기본 컨텍스트로 폴백
    _SSL_CTX = None

# ===========================================================================
# 엔드포인트 단일 진실 공급원 (SINGLE SOURCE OF TRUTH)
# ---------------------------------------------------------------------------
# ⚠️ TODO(라이브 검증 필요): 아래 경로/응답 스키마는 공개 문서(docs.scenario.com,
#    help.scenario.com) 조사 기준이다. 키 발급 후 실호출로 반드시 재확인할 것.
#    - 확인됨: BASE, Basic 인증, /generate/txt2img, /generate/custom/{modelId},
#              /jobs/{jobId}(status="success"), 학습 4단계(/models ...).
#    - 미확정: 배경 제거 엔드포인트, /assets/{assetId} 응답에서 다운로드 URL 필드명,
#              잡 결과에서 이미지/에셋을 꺼내는 정확한 경로.
#    이 블록 밖에는 하드코딩된 URL 을 두지 않는다. (수정 지점 단일화)
# ===========================================================================
_DEFAULT_BASE = "https://api.cloud.scenario.com/v1"


class Api:
    """URL 빌더. 모든 경로는 여기서만 조립한다."""

    @staticmethod
    def base() -> str:
        # 테스트/미러링을 위해 SCENARIO_API_BASE 로 재정의 가능.
        return (env_config.get("SCENARIO_API_BASE") or _DEFAULT_BASE).rstrip("/")

    # --- 생성 -------------------------------------------------------------
    @classmethod
    def generate_txt2img(cls) -> str:
        return f"{cls.base()}/generate/txt2img"

    @classmethod
    def generate_custom(cls, model_id: str) -> str:
        return f"{cls.base()}/generate/custom/{urllib.parse.quote(model_id, safe='')}"

    @classmethod
    def job(cls, job_id: str) -> str:
        return f"{cls.base()}/jobs/{urllib.parse.quote(job_id, safe='')}"

    # --- 학습(커스텀 모델) -------------------------------------------------
    @classmethod
    def models(cls, project_id: str | None = None) -> str:
        url = f"{cls.base()}/models"
        return cls._with_project(url, project_id)

    @classmethod
    def model(cls, model_id: str, project_id: str | None = None) -> str:
        url = f"{cls.base()}/models/{urllib.parse.quote(model_id, safe='')}"
        return cls._with_project(url, project_id)

    @classmethod
    def training_images(cls, model_id: str, project_id: str | None = None) -> str:
        url = f"{cls.base()}/models/{urllib.parse.quote(model_id, safe='')}/training-images"
        return cls._with_project(url, project_id)

    @classmethod
    def train(cls, model_id: str, project_id: str | None = None) -> str:
        url = f"{cls.base()}/models/{urllib.parse.quote(model_id, safe='')}/train"
        return cls._with_project(url, project_id)

    # --- 후처리 / 에셋 (미확정: 라이브 검증 필요) --------------------------
    @classmethod
    def remove_background(cls) -> str:
        # TODO(라이브 검증 필요): 실제 경로 확인 전 잠정값.
        return f"{cls.base()}/generate/remove-background"

    @classmethod
    def asset(cls, asset_id: str) -> str:
        # TODO(라이브 검증 필요): 응답에서 다운로드 URL 필드명 확인 필요.
        return f"{cls.base()}/assets/{urllib.parse.quote(asset_id, safe='')}"

    @staticmethod
    def _with_project(url: str, project_id: str | None) -> str:
        if project_id:
            return f"{url}?{urllib.parse.urlencode({'projectId': project_id})}"
        return url


# 잡 상태값 (신형 통합 API 기준). classic /models/{id}/inferences 를 쓰는 배포에서는
# "succeeded" 를 쓸 수 있어 둘 다 성공으로 취급한다. (라이브 검증 필요)
_JOB_SUCCESS = {"success", "succeeded", "done", "complete", "completed"}
_JOB_FAILURE = {"failure", "failed", "error", "canceled", "cancelled"}

REQUIRED_KEYS = ["SCENARIO_API_KEY", "SCENARIO_API_SECRET"]

_ISSUE_GUIDANCE = (
    "      Scenario API 키 발급 방법:\n"
    "        1) https://app.scenario.com 로그인 → 우상단 계정 → API Keys\n"
    "        2) 'Create API Key' 로 Key 와 Secret 을 발급 (커스텀 모델 학습 가능 플랜 확인)\n"
    "      저장소 루트에 .env 파일을 만들고 아래 형식으로 기입 (.gitignore 등재됨, 커밋 금지):\n"
    "        SCENARIO_API_KEY=발급받은_KEY\n"
    "        SCENARIO_API_SECRET=발급받은_SECRET\n"
    "        # (선택) SCENARIO_PROJECT_ID=프로젝트_ID   # 학습/생성에 projectId 가 필요한 경우\n"
    "      키 없이 요청 구성만 확인하려면 각 명령에 --dry-run 을 붙이세요."
)


# ---------------------------------------------------------------------------
# 예외 / 요청 표현
# ---------------------------------------------------------------------------
class ScenarioApiError(Exception):
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
        """비밀값(Authorization)·대용량(data base64)을 마스킹한 표시용 dict."""
        headers = dict(self.headers)
        if "Authorization" in headers:
            scheme = headers["Authorization"].split(" ", 1)[0]
            headers["Authorization"] = f"{scheme} ****(마스킹)"
        body = self.body
        if isinstance(body, dict) and "data" in body and isinstance(body["data"], str):
            body = dict(body)
            body["data"] = f"<base64 {len(self.body['data'])} chars 마스킹>"
        return {"method": self.method, "url": self.url, "headers": headers, "body": body}


# ---------------------------------------------------------------------------
# 인증 헤더
# ---------------------------------------------------------------------------
def build_auth_header(key: str, secret: str) -> str:
    """Scenario Basic 인증 헤더값: 'Basic base64(key:secret)'."""
    token = base64.b64encode(f"{key}:{secret}".encode("utf-8")).decode("ascii")
    return f"Basic {token}"


def resolve_auth(
    *, path: str | None = None, environ: dict[str, str] | None = None
) -> str:
    """`.env`/환경변수에서 키를 읽어 Authorization 헤더를 만든다.
    없으면 `env_config.MissingKeysError`."""
    creds = env_config.require(REQUIRED_KEYS, path=path, environ=environ)
    return build_auth_header(creds["SCENARIO_API_KEY"], creds["SCENARIO_API_SECRET"])


def _json_headers(auth: str) -> dict[str, str]:
    return {"Authorization": auth, "Content-Type": "application/json", "Accept": "application/json"}


# ---------------------------------------------------------------------------
# prepare_* (순수 — 네트워크 없음, 단위 검증 대상)
# ---------------------------------------------------------------------------
def prepare_generate(
    *,
    model_id: str,
    prompt: str,
    auth: str,
    custom: bool = True,
    num_samples: int = 1,
    width: int = 512,
    height: int = 512,
    guidance: float = 3.5,
    num_inference_steps: int = 28,
    aspect_ratio: str | None = None,
) -> PreparedRequest:
    """생성 요청 구성. custom=True 면 커스텀(잠긴 스타일) 모델 엔드포인트."""
    if custom:
        body: dict = {"prompt": prompt, "numSamples": num_samples}
        if aspect_ratio:
            body["aspectRatio"] = aspect_ratio
        else:
            body["width"] = width
            body["height"] = height
        return PreparedRequest("POST", Api.generate_custom(model_id), _json_headers(auth), body)
    body = {
        "modelId": model_id,
        "prompt": prompt,
        "numSamples": num_samples,
        "width": width,
        "height": height,
        "guidance": guidance,
        "numInferenceSteps": num_inference_steps,
    }
    return PreparedRequest("POST", Api.generate_txt2img(), _json_headers(auth), body)


def prepare_job_status(job_id: str, auth: str) -> PreparedRequest:
    return PreparedRequest("GET", Api.job(job_id), _json_headers(auth))


def prepare_model_create(
    *, name: str, model_type: str, auth: str, project_id: str | None = None
) -> PreparedRequest:
    return PreparedRequest(
        "POST", Api.models(project_id), _json_headers(auth), {"name": name, "type": model_type}
    )


def prepare_training_image(
    *, model_id: str, name: str, data_uri: str, auth: str, project_id: str | None = None
) -> PreparedRequest:
    return PreparedRequest(
        "POST",
        Api.training_images(model_id, project_id),
        _json_headers(auth),
        {"name": name, "data": data_uri},
    )


def prepare_train_start(
    *, model_id: str, auth: str, seed: int | None = None, project_id: str | None = None
) -> PreparedRequest:
    params: dict = {}
    if seed is not None:
        params["seed"] = seed
    return PreparedRequest(
        "PUT", Api.train(model_id, project_id), _json_headers(auth), {"parameters": params}
    )


def prepare_model_status(
    *, model_id: str, auth: str, project_id: str | None = None
) -> PreparedRequest:
    return PreparedRequest("GET", Api.model(model_id, project_id), _json_headers(auth))


def prepare_remove_background(*, image_ref: str, auth: str) -> PreparedRequest:
    # image_ref: assetId 또는 이미지 URL/데이터. (라이브 검증 필요)
    return PreparedRequest(
        "POST", Api.remove_background(), _json_headers(auth), {"image": image_ref}
    )


def prepare_asset_get(asset_id: str, auth: str) -> PreparedRequest:
    return PreparedRequest("GET", Api.asset(asset_id), _json_headers(auth))


# ---------------------------------------------------------------------------
# 전송 (실제 네트워크)
# ---------------------------------------------------------------------------
def send(prepared: PreparedRequest, *, timeout: float = 60.0) -> dict:
    """PreparedRequest 를 실제로 전송하고 JSON 응답을 반환. 오류는 ScenarioApiError."""
    data = None
    if prepared.body is not None:
        data = json.dumps(prepared.body).encode("utf-8")
    req = urllib.request.Request(
        prepared.url, data=data, headers=prepared.headers, method=prepared.method
    )
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            raw = resp.read().decode("utf-8")
            return json.loads(raw) if raw.strip() else {}
    except urllib.error.HTTPError as exc:
        detail = ""
        try:
            detail = exc.read().decode("utf-8")[:500]
        except Exception:  # noqa: BLE001 - 진단용 부가정보일 뿐
            pass
        hint = " (인증 실패 — 키/시크릿 확인)" if exc.code in (401, 403) else ""
        raise ScenarioApiError(
            f"HTTP {exc.code}{hint}: {prepared.method} {prepared.url}\n{detail}",
            status=exc.code,
        ) from exc
    except urllib.error.URLError as exc:
        raise ScenarioApiError(f"네트워크 오류: {exc.reason} ({prepared.url})") from exc
    except TimeoutError as exc:
        raise ScenarioApiError(f"요청 타임아웃({timeout}s): {prepared.url}") from exc
    except json.JSONDecodeError as exc:
        raise ScenarioApiError(f"응답 JSON 파싱 실패: {exc}") from exc


def poll_job(job_id: str, auth: str, *, timeout: float, interval: float = 3.0) -> dict:
    """잡이 성공/실패로 끝날 때까지 폴링. 최종 job dict 반환."""
    deadline = time.monotonic() + timeout
    while True:
        resp = send(prepare_job_status(job_id, auth), timeout=30.0)
        job = resp.get("job", resp)
        status = str(job.get("status", "")).lower()
        if status in _JOB_SUCCESS:
            return job
        if status in _JOB_FAILURE:
            raise ScenarioApiError(f"잡 실패: status={status} job={job_id}")
        if time.monotonic() >= deadline:
            raise ScenarioApiError(f"잡 폴링 타임아웃({timeout}s): status={status} job={job_id}")
        time.sleep(interval)


def _download(url: str, dest: Path, *, timeout: float = 120.0) -> None:
    req = urllib.request.Request(url, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=timeout, context=_SSL_CTX) as resp:
            dest.parent.mkdir(parents=True, exist_ok=True)
            dest.write_bytes(resp.read())
    except (urllib.error.URLError, TimeoutError) as exc:
        raise ScenarioApiError(f"이미지 다운로드 실패: {url} ({exc})") from exc


def file_to_data_uri(path: Path) -> str:
    mime, _ = mimetypes.guess_type(str(path))
    mime = mime or "application/octet-stream"
    b64 = base64.b64encode(path.read_bytes()).decode("ascii")
    return f"data:{mime};base64,{b64}"


# ---------------------------------------------------------------------------
# 표시 헬퍼
# ---------------------------------------------------------------------------
def _print_dry_run(title: str, prepared: PreparedRequest | list[PreparedRequest]) -> None:
    preps = prepared if isinstance(prepared, list) else [prepared]
    print(f"[dry-run] {title} — 전송하지 않고 요청 구성만 출력합니다 ({len(preps)}건):")
    for i, p in enumerate(preps, 1):
        print(f"  ({i}) " + json.dumps(p.to_display(), ensure_ascii=False, indent=2).replace("\n", "\n      "))


# ---------------------------------------------------------------------------
# CLI 핸들러
# ---------------------------------------------------------------------------
def _resolve_auth_or_exit(args: argparse.Namespace) -> str | int:
    """auth 헤더를 반환하거나, 미설정이면 안내 후 종료 코드(3)를 반환."""
    try:
        return resolve_auth(path=args.env)
    except env_config.MissingKeysError as exc:
        print(exc.render(_ISSUE_GUIDANCE), file=sys.stderr)
        return 3


def _cmd_check_auth(args: argparse.Namespace) -> int:
    auth = _resolve_auth_or_exit(args)
    if isinstance(auth, int):
        return auth
    # 인증 확인용 경량 요청: 모델 목록 GET (프로젝트 지정 시 해당 프로젝트).
    prepared = PreparedRequest("GET", Api.models(args.project_id), _json_headers(auth))
    if args.dry_run:
        _print_dry_run("check-auth (모델 목록 GET)", prepared)
        print("키는 존재합니다. 실제 인증 확인은 --dry-run 없이 실행하세요.")
        return 0
    try:
        send(prepared, timeout=args.timeout)
    except ScenarioApiError as exc:
        print(f"인증 확인 실패: {exc}", file=sys.stderr)
        return 1
    print("인증 성공: 자격 증명이 유효합니다.")
    return 0


def _cmd_generate(args: argparse.Namespace) -> int:
    auth = _resolve_auth_or_exit(args)
    if isinstance(auth, int):
        return auth
    prepared = prepare_generate(
        model_id=args.model_id,
        prompt=args.prompt,
        auth=auth,
        custom=not args.base_model,
        num_samples=args.num_samples,
        width=args.width,
        height=args.height,
        aspect_ratio=args.aspect_ratio,
    )
    if args.dry_run:
        _print_dry_run("generate", prepared)
        return 0
    try:
        resp = send(prepared, timeout=args.timeout)
        job = resp.get("job", resp)
        job_id = job.get("jobId") or job.get("id")
        if not job_id:
            raise ScenarioApiError(f"응답에서 jobId 를 찾지 못함: {json.dumps(resp)[:300]}")
        print(f"생성 잡 시작: {job_id} — 폴링 중...")
        done = poll_job(job_id, auth, timeout=args.timeout)
        # TODO(라이브 검증 필요): 잡 결과에서 assetIds/이미지 URL 추출 경로 확정.
        asset_ids = (done.get("metadata") or {}).get("assetIds") or done.get("assetIds") or []
        out_dir = Path(args.out_dir)
        saved: list[str] = []
        for idx, asset_id in enumerate(asset_ids):
            meta = send(prepare_asset_get(asset_id, auth), timeout=30.0)
            url = meta.get("url") or meta.get("downloadUrl") or (meta.get("asset") or {}).get("url")
            if not url:
                print(f"경고: 에셋 {asset_id} 응답에서 URL 을 찾지 못함(스키마 확인 필요).", file=sys.stderr)
                continue
            dest = out_dir / f"{args.name or args.model_id.replace('/', '_')}_{idx:02d}.png"
            _download(url, dest, timeout=args.timeout)
            saved.append(str(dest))
        if not saved:
            print("완료했지만 저장된 이미지가 없습니다(에셋 URL 스키마 확인 필요).", file=sys.stderr)
            return 1
        print("저장됨:\n  " + "\n  ".join(saved))
        return 0
    except ScenarioApiError as exc:
        print(f"생성 실패: {exc}", file=sys.stderr)
        return 1


def _cmd_train(args: argparse.Namespace) -> int:
    auth = _resolve_auth_or_exit(args)
    if isinstance(auth, int):
        return auth

    # 상태 조회 모드
    if args.status:
        if not args.model_id:
            print("오류: --status 에는 --model-id 가 필요합니다.", file=sys.stderr)
            return 2
        prepared = prepare_model_status(model_id=args.model_id, auth=auth, project_id=args.project_id)
        if args.dry_run:
            _print_dry_run("train --status", prepared)
            return 0
        try:
            resp = send(prepared, timeout=args.timeout)
        except ScenarioApiError as exc:
            print(f"상태 조회 실패: {exc}", file=sys.stderr)
            return 1
        model = resp.get("model", resp)
        print(f"모델 {args.model_id} status={model.get('status')}")
        return 0

    # 학습 시작 플로우: 모델 생성 → 학습 이미지 업로드 → 학습 시작
    if not args.name or not args.type:
        print("오류: 학습 시작에는 --name 과 --type 이 필요합니다 "
              "(또는 --status --model-id).", file=sys.stderr)
        return 2
    images = [Path(p) for p in (args.image or [])]
    missing = [str(p) for p in images if not p.exists()]
    if missing:
        print("오류: 학습 이미지 파일이 없습니다: " + ", ".join(missing), file=sys.stderr)
        return 2

    create_req = prepare_model_create(
        name=args.name, model_type=args.type, auth=auth, project_id=args.project_id
    )
    if args.dry_run:
        # 실제 model_id 를 아직 모르므로 플레이스홀더로 구성해 흐름을 보여준다.
        placeholder_id = "PENDING_MODEL_ID"
        preps = [create_req]
        for p in images:
            preps.append(
                prepare_training_image(
                    model_id=placeholder_id, name=p.name,
                    data_uri=file_to_data_uri(p), auth=auth, project_id=args.project_id,
                )
            )
        preps.append(
            prepare_train_start(
                model_id=placeholder_id, auth=auth, seed=args.seed, project_id=args.project_id
            )
        )
        _print_dry_run("train (create → upload → start)", preps)
        return 0
    try:
        created = send(create_req, timeout=args.timeout)
        model = created.get("model", created)
        model_id = model.get("id") or model.get("modelId")
        if not model_id:
            raise ScenarioApiError(f"모델 생성 응답에서 id 를 찾지 못함: {json.dumps(created)[:300]}")
        print(f"모델 생성됨: {model_id}")
        for p in images:
            send(
                prepare_training_image(
                    model_id=model_id, name=p.name, data_uri=file_to_data_uri(p),
                    auth=auth, project_id=args.project_id,
                ),
                timeout=args.timeout,
            )
            print(f"  학습 이미지 업로드: {p.name}")
        send(
            prepare_train_start(
                model_id=model_id, auth=auth, seed=args.seed, project_id=args.project_id
            ),
            timeout=args.timeout,
        )
        print(f"학습 시작됨: {model_id} — 상태는 `train --status --model-id {model_id}` 로 확인.")
        return 0
    except ScenarioApiError as exc:
        print(f"학습 실패: {exc}", file=sys.stderr)
        return 1


def _cmd_remove_bg(args: argparse.Namespace) -> int:
    auth = _resolve_auth_or_exit(args)
    if isinstance(auth, int):
        return auth
    prepared = prepare_remove_background(image_ref=args.image, auth=auth)
    if args.dry_run:
        _print_dry_run("remove-bg (엔드포인트 미확정 — 라이브 검증 필요)", prepared)
        return 0
    try:
        resp = send(prepared, timeout=args.timeout)
    except ScenarioApiError as exc:
        print(f"배경 제거 실패: {exc}", file=sys.stderr)
        return 1
    print("배경 제거 요청 응답:\n" + json.dumps(resp, ensure_ascii=False, indent=2)[:800])
    return 0


# ---------------------------------------------------------------------------
# 파서
# ---------------------------------------------------------------------------
def _add_common(sp: argparse.ArgumentParser) -> None:
    sp.add_argument("--env", default=None, help=".env 경로 (기본: <repo>/.env)")
    sp.add_argument("--dry-run", action="store_true", help="전송하지 않고 요청 구성만 출력")
    sp.add_argument("--timeout", type=float, default=120.0, help="요청 타임아웃(초)")
    sp.add_argument("--project-id", default=env_config.get("SCENARIO_PROJECT_ID"),
                    help="projectId (기본: .env 의 SCENARIO_PROJECT_ID)")


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="scenario_client.py",
        description="Scenario API 클라이언트 (urllib). 키 부재/네트워크 오류 graceful. "
                    "--dry-run 으로 라이브 없이 요청 구성 검증.",
    )
    sub = p.add_subparsers(dest="command", required=True)

    pa = sub.add_parser("check-auth", help="키 검증 (경량 인증 요청)")
    _add_common(pa)
    pa.set_defaults(func=_cmd_check_auth)

    pg = sub.add_parser("generate", help="모델 ID+프롬프트 → 이미지 생성·다운로드")
    _add_common(pg)
    pg.add_argument("--model-id", required=True, help="커스텀(잠긴) 모델 ID 또는 base 모델 ID")
    pg.add_argument("--prompt", required=True)
    pg.add_argument("--base-model", action="store_true",
                    help="커스텀 대신 base 모델(txt2img) 엔드포인트 사용")
    pg.add_argument("--num-samples", type=int, default=1)
    pg.add_argument("--width", type=int, default=512)
    pg.add_argument("--height", type=int, default=512)
    pg.add_argument("--aspect-ratio", default=None, help="예: 1:1, 4:3 (커스텀 모델)")
    pg.add_argument("--out-dir", default="assets/art/concepts", help="이미지 저장 디렉토리")
    pg.add_argument("--name", default=None, help="저장 파일 접두사")
    pg.set_defaults(func=_cmd_generate)

    pt = sub.add_parser("train", help="커스텀 모델 학습 시작/상태")
    _add_common(pt)
    pt.add_argument("--status", action="store_true", help="학습 상태 조회 (--model-id 필요)")
    pt.add_argument("--model-id", default=None, help="상태 조회 대상 모델 ID")
    pt.add_argument("--name", default=None, help="새 모델 이름 (학습 시작)")
    pt.add_argument("--type", default=None,
                    help="base 아키텍처 (예: flux.2-dev-lora, qwen-image-lora, zimage-lora)")
    pt.add_argument("--image", action="append", metavar="PATH",
                    help="학습 이미지 파일 (반복). 5~15장 권장.")
    pt.add_argument("--seed", type=int, default=None)
    pt.set_defaults(func=_cmd_train)

    pr = sub.add_parser("remove-bg", help="배경 제거 (플랫폼 후처리)")
    _add_common(pr)
    pr.add_argument("--image", required=True, help="assetId 또는 이미지 URL/데이터")
    pr.set_defaults(func=_cmd_remove_bg)

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
