#!/usr/bin/env python3
"""에셋 매니페스트 읽기/쓰기 유일 창구 (HANDOFF §5, CLAUDE.md 원칙 3).

`pipeline/manifest.json` 은 "어떤 노드/이벤트가 어떤 에셋을 필요로 하는가"의
단일 기록이다. play build 가 등록하고, art reskin / se attach 가 소비하며,
verify 가 정합성을 검사한다. 이 파일에 대한 모든 쓰기는 **이 스크립트를 통해서만**
이루어져야 하며, 쓰기 전 반드시 스키마 검증을 통과해야 한다.

외부 패키지(jsonschema) 없이 draft-07 스키마의 **사용된 키워드만**을 직접 구현한
경량 검증기를 포함한다 (지원: type, required, const, enum, pattern, properties,
items, $ref, definitions). 검증기는 스키마 파일을 그대로 읽어 동작하므로
스키마가 바뀌면 검증도 함께 따라간다(하드코딩 최소화).

추가 도메인 규칙 (스키마 표현 밖, conventions.md 근거):
  - ID prefix 는 entry.track 과 일치해야 한다  (id 형식: <track>:<카테고리>/<이름>)
  - manifest 내 ID 는 유일해야 한다

CLI 서브커맨드:
  validate        스키마 + 도메인 규칙 검증 (verify 게이트 #4)
  add             entry 추가 (검증 통과 시에만 기록)
  update-status   entry 의 status 갱신 + history 기록
  set-style-guide art lock 승인 결과(스타일 가이드 경로) 잠금/해제
  list            entry 목록 출력

종료 코드: 0 = 성공/유효, 1 = 검증 실패/규칙 위반, 2 = 실행 오류.
stdlib 만 사용 (Python 3.14).
"""
from __future__ import annotations

import argparse
import json
import os
import re
import sys
from dataclasses import dataclass, asdict
from datetime import datetime, timezone
from pathlib import Path

# ---------------------------------------------------------------------------
# 경로 기본값
# ---------------------------------------------------------------------------
def _repo_root() -> Path:
    # pipeline/scripts/manifest.py -> repo_root
    return Path(__file__).resolve().parents[2]


def default_manifest() -> str:
    return str(_repo_root() / "pipeline" / "manifest.json")


def default_schema() -> str:
    return str(_repo_root() / "pipeline" / "schemas" / "asset-manifest.schema.json")


# status(enum) -> history.action(enum) 매핑.
# 스키마상 status 는 {placeholder, generated, approved, rejected},
# history.action 은 {registered, generated, approved, rejected}.
STATUS_TO_ACTION = {
    "placeholder": "registered",
    "generated": "generated",
    "approved": "approved",
    "rejected": "rejected",
}


# ---------------------------------------------------------------------------
# 경량 JSON Schema 검증기 (draft-07 부분집합, stdlib 만)
# ---------------------------------------------------------------------------
@dataclass
class ValidationError:
    code: str          # type | const | enum | pattern | required | ref
    path: str          # JSON 포인터 유사 경로 (예: $.entries[0].id)
    message: str


_JSON_TYPE_CHECKS = {
    "object": lambda v: isinstance(v, dict),
    "array": lambda v: isinstance(v, list),
    "string": lambda v: isinstance(v, str),
    # bool 은 int 의 서브클래스이므로 명시적으로 제외한다.
    "integer": lambda v: isinstance(v, int) and not isinstance(v, bool),
    "number": lambda v: isinstance(v, (int, float)) and not isinstance(v, bool),
    "boolean": lambda v: isinstance(v, bool),
    "null": lambda v: v is None,
}


def _type_name(v: object) -> str:
    if v is None:
        return "null"
    if isinstance(v, bool):
        return "boolean"
    if isinstance(v, str):
        return "string"
    if isinstance(v, int):
        return "integer"
    if isinstance(v, float):
        return "number"
    if isinstance(v, list):
        return "array"
    if isinstance(v, dict):
        return "object"
    return type(v).__name__


def _check_type(value: object, type_spec) -> bool:
    types = type_spec if isinstance(type_spec, list) else [type_spec]
    return any(_JSON_TYPE_CHECKS.get(t, lambda _v: False)(value) for t in types)


def _resolve_ref(ref: str, root: dict) -> dict:
    if not ref.startswith("#/"):
        raise ValueError(f"지원하지 않는 $ref 형식: {ref}")
    node: object = root
    for part in ref[2:].split("/"):
        # JSON 포인터 이스케이프 해제
        part = part.replace("~1", "/").replace("~0", "~")
        node = node[part]
    if not isinstance(node, dict):
        raise ValueError(f"$ref 대상이 스키마 객체가 아님: {ref}")
    return node


def validate_against_schema(
    instance: object, schema: dict, root: dict | None = None, path: str = "$"
) -> list[ValidationError]:
    """instance 를 schema 로 검증. 지원 키워드만 처리한다."""
    root = schema if root is None else root
    errors: list[ValidationError] = []

    if "$ref" in schema:
        try:
            resolved = _resolve_ref(schema["$ref"], root)
        except (KeyError, ValueError) as exc:
            errors.append(ValidationError("ref", path, f"$ref 해석 실패: {exc}"))
            return errors
        return validate_against_schema(instance, resolved, root, path)

    if "type" in schema:
        if not _check_type(instance, schema["type"]):
            errors.append(
                ValidationError(
                    "type",
                    path,
                    f"타입이 {schema['type']} 여야 합니다 (실제: {_type_name(instance)})",
                )
            )
            return errors  # 타입이 틀리면 하위 검사는 의미 없음

    if "const" in schema and instance != schema["const"]:
        errors.append(
            ValidationError(
                "const", path, f"값이 {schema['const']!r} 여야 합니다 (실제: {instance!r})"
            )
        )

    if "enum" in schema and instance not in schema["enum"]:
        errors.append(
            ValidationError(
                "enum",
                path,
                f"값이 {schema['enum']} 중 하나여야 합니다 (실제: {instance!r})",
            )
        )

    if "pattern" in schema and isinstance(instance, str):
        if re.search(schema["pattern"], instance) is None:
            errors.append(
                ValidationError(
                    "pattern",
                    path,
                    f"패턴 {schema['pattern']} 과 불일치 (실제: {instance!r})",
                )
            )

    if isinstance(instance, dict):
        for req in schema.get("required", []):
            if req not in instance:
                errors.append(
                    ValidationError("required", f"{path}.{req}", f"필수 필드 '{req}' 누락")
                )
        props = schema.get("properties", {})
        for key, subschema in props.items():
            if key in instance:
                errors.extend(
                    validate_against_schema(instance[key], subschema, root, f"{path}.{key}")
                )

    if isinstance(instance, list):
        items_schema = schema.get("items")
        if isinstance(items_schema, dict):
            for i, element in enumerate(instance):
                errors.extend(
                    validate_against_schema(element, items_schema, root, f"{path}[{i}]")
                )

    return errors


# ---------------------------------------------------------------------------
# 도메인 규칙 (스키마 밖, conventions.md 근거)
# ---------------------------------------------------------------------------
def check_domain_rules(manifest: dict) -> list[ValidationError]:
    """스키마로 표현하기 어려운 매니페스트 고유 규칙을 검사."""
    errors: list[ValidationError] = []
    entries = manifest.get("entries")
    if not isinstance(entries, list):
        return errors  # 스키마 검증이 이미 잡음

    seen_ids: dict[str, int] = {}
    for i, entry in enumerate(entries):
        if not isinstance(entry, dict):
            continue
        path = f"$.entries[{i}]"
        entry_id = entry.get("id")
        track = entry.get("track")

        # 규칙 1: ID 유일성
        if isinstance(entry_id, str):
            if entry_id in seen_ids:
                errors.append(
                    ValidationError(
                        "duplicate_id",
                        f"{path}.id",
                        f"중복 ID '{entry_id}' (최초: entries[{seen_ids[entry_id]}])",
                    )
                )
            else:
                seen_ids[entry_id] = i

        # 규칙 2: ID prefix == track  (id 형식: <track>:<카테고리>/<이름>)
        if isinstance(entry_id, str) and isinstance(track, str) and ":" in entry_id:
            prefix = entry_id.split(":", 1)[0]
            if prefix != track:
                errors.append(
                    ValidationError(
                        "id_track_mismatch",
                        f"{path}.id",
                        f"ID prefix '{prefix}' 가 track '{track}' 와 불일치 "
                        f"(id 형식: <track>:<카테고리>/<이름>)",
                    )
                )
    return errors


def validate_manifest(manifest: object, schema: dict) -> list[ValidationError]:
    """스키마 검증 + 도메인 규칙 검증 결과를 합쳐 반환."""
    errors = validate_against_schema(manifest, schema, schema, "$")
    # 스키마 통과 여부와 무관하게 도메인 규칙도 최대한 검사(중복 리포트 방지 위해
    # manifest 가 dict 일 때만)
    if isinstance(manifest, dict):
        errors.extend(check_domain_rules(manifest))
    return errors


# ---------------------------------------------------------------------------
# 읽기/쓰기 (유일 창구)
# ---------------------------------------------------------------------------
def load_schema(schema_path: str) -> dict:
    p = Path(schema_path)
    if not p.exists():
        raise FileNotFoundError(f"스키마 파일이 없습니다: {schema_path}")
    return json.loads(p.read_text(encoding="utf-8"))


def load_manifest(manifest_path: str) -> dict:
    p = Path(manifest_path)
    if not p.exists():
        raise FileNotFoundError(f"매니페스트 파일이 없습니다: {manifest_path}")
    data = json.loads(p.read_text(encoding="utf-8"))
    if not isinstance(data, dict):
        raise ValueError("매니페스트 최상위는 객체여야 합니다.")
    return data


def save_manifest(manifest: dict, manifest_path: str, schema: dict) -> None:
    """검증을 통과한 경우에만 원자적으로 기록한다. (유일한 쓰기 경로)"""
    errors = validate_manifest(manifest, schema)
    if errors:
        raise ManifestValidationError(errors)
    target = Path(manifest_path)
    tmp = target.with_suffix(target.suffix + ".tmp")
    tmp.write_text(
        json.dumps(manifest, ensure_ascii=False, indent=2) + "\n", encoding="utf-8"
    )
    os.replace(tmp, target)


class ManifestValidationError(Exception):
    def __init__(self, errors: list[ValidationError]):
        self.errors = errors
        super().__init__(f"매니페스트 검증 실패: {len(errors)}건")


def _now_iso() -> str:
    return datetime.now(timezone.utc).isoformat()


# ---------------------------------------------------------------------------
# entry 조립
# ---------------------------------------------------------------------------
def _parse_requested_by(raw_items: list[str]) -> list[dict]:
    """'kind:path' 문자열을 requested_by 객체로 변환. path 는 첫 ':' 뒤 전부."""
    out: list[dict] = []
    for raw in raw_items:
        if ":" not in raw:
            raise ValueError(
                f"--requested-by 형식은 'kind:path' 여야 합니다 (받음: {raw!r}). "
                f"kind 는 scene_node|code_event|ui|doc."
            )
        kind, path = raw.split(":", 1)
        out.append({"kind": kind.strip(), "path": path.strip()})
    return out


def build_entry(
    entry_id: str,
    track: str,
    status: str,
    spec: str,
    requested_by: list[dict],
    file: str | None = None,
    lore_refs: list[str] | None = None,
) -> dict:
    entry: dict = {
        "id": entry_id,
        "track": track,
        "status": status,
        "spec": spec,
        "requested_by": requested_by,
        "file": file,
        "history": [{"at": _now_iso(), "action": STATUS_TO_ACTION.get(status, "registered")}],
    }
    if lore_refs:
        entry["lore_refs"] = lore_refs
    return entry


# ---------------------------------------------------------------------------
# CLI 핸들러
# ---------------------------------------------------------------------------
def _print_errors(errors: list[ValidationError]) -> None:
    for e in errors:
        print(f"  [{e.code}] {e.path}: {e.message}", file=sys.stderr)


def _cmd_validate(args: argparse.Namespace) -> int:
    schema = load_schema(args.schema)
    manifest = load_manifest(args.manifest)
    errors = validate_manifest(manifest, schema)
    if args.json:
        print(
            json.dumps(
                {"valid": not errors, "errors": [asdict(e) for e in errors]},
                ensure_ascii=False,
                indent=2,
            )
        )
    else:
        if errors:
            print(f"검증 실패: {len(errors)}건", file=sys.stderr)
            _print_errors(errors)
        else:
            print(f"유효한 매니페스트: {args.manifest} (entry {len(manifest['entries'])}개)")
    return 1 if errors else 0


def _cmd_add(args: argparse.Namespace) -> int:
    schema = load_schema(args.schema)
    manifest = load_manifest(args.manifest)
    try:
        requested_by = _parse_requested_by(args.requested_by or [])
    except ValueError as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2

    entry = build_entry(
        entry_id=args.id,
        track=args.track,
        status=args.status,
        spec=args.spec,
        requested_by=requested_by,
        file=args.file,
        lore_refs=args.lore_ref or [],
    )
    manifest.setdefault("entries", []).append(entry)

    try:
        save_manifest(manifest, args.manifest, schema)
    except ManifestValidationError as exc:
        print("entry 추가 실패 — 검증 통과하지 못해 매니페스트를 쓰지 않았습니다:", file=sys.stderr)
        _print_errors(exc.errors)
        return 1
    print(f"추가됨: {args.id} (track={args.track}, status={args.status}) → {args.manifest}")
    return 0


def _cmd_update_status(args: argparse.Namespace) -> int:
    schema = load_schema(args.schema)
    manifest = load_manifest(args.manifest)
    target = None
    for entry in manifest.get("entries", []):
        if entry.get("id") == args.id:
            target = entry
            break
    if target is None:
        print(f"오류: ID '{args.id}' 를 찾을 수 없습니다.", file=sys.stderr)
        return 2

    target["status"] = args.status
    hist = {"at": _now_iso(), "action": STATUS_TO_ACTION.get(args.status, "registered")}
    if args.feedback:
        hist["feedback"] = args.feedback
    target.setdefault("history", []).append(hist)
    if args.file is not None:
        target["file"] = args.file

    try:
        save_manifest(manifest, args.manifest, schema)
    except ManifestValidationError as exc:
        print("상태 갱신 실패 — 검증 통과하지 못해 매니페스트를 쓰지 않았습니다:", file=sys.stderr)
        _print_errors(exc.errors)
        return 1
    print(f"갱신됨: {args.id} → status={args.status}")
    return 0


def _cmd_set_style_guide(args: argparse.Namespace) -> int:
    """art lock 승인 결과(스타일 가이드 문서 경로)를 매니페스트에 잠근다.

    사람 승인 후에만 호출되어야 한다(art lock 은 생략 불가한 승인 지점).
    `--clear` 로 잠금 해제(null)도 가능하다.
    """
    schema = load_schema(args.schema)
    manifest = load_manifest(args.manifest)

    if args.clear:
        manifest["style_guide"] = None
    else:
        if not args.path:
            print("오류: --path 또는 --clear 가 필요합니다.", file=sys.stderr)
            return 2
        target = Path(args.path)
        if not target.exists():
            print(f"오류: 스타일 가이드 문서가 없습니다: {args.path}", file=sys.stderr)
            return 2
        manifest["style_guide"] = args.path

    try:
        save_manifest(manifest, args.manifest, schema)
    except ManifestValidationError as exc:
        print("style_guide 설정 실패 — 검증 통과하지 못해 매니페스트를 쓰지 않았습니다:", file=sys.stderr)
        _print_errors(exc.errors)
        return 1
    print(f"style_guide = {manifest['style_guide']!r} → {args.manifest}")
    return 0


def _cmd_list(args: argparse.Namespace) -> int:
    manifest = load_manifest(args.manifest)
    entries = manifest.get("entries", [])
    if args.track:
        entries = [e for e in entries if e.get("track") == args.track]
    if args.status:
        entries = [e for e in entries if e.get("status") == args.status]
    if args.json:
        print(json.dumps(entries, ensure_ascii=False, indent=2))
        return 0
    if not entries:
        print("(조건에 맞는 entry 없음)")
        return 0
    print(f"entry {len(entries)}개:")
    for e in entries:
        rb = ", ".join(f"{r.get('kind')}:{r.get('path')}" for r in e.get("requested_by", []))
        print(f"  - {e.get('id')}  [{e.get('status')}]  track={e.get('track')}")
        print(f"      spec: {e.get('spec')}")
        if rb:
            print(f"      requested_by: {rb}")
        if e.get("file"):
            print(f"      file: {e.get('file')}")
    return 0


def build_parser() -> argparse.ArgumentParser:
    p = argparse.ArgumentParser(
        prog="manifest.py",
        description="에셋 매니페스트 읽기/쓰기 유일 창구 (스키마 검증 후 쓰기)",
    )
    p.add_argument("--manifest", default=default_manifest(), help="매니페스트 경로")
    p.add_argument("--schema", default=default_schema(), help="스키마 경로")
    sub = p.add_subparsers(dest="command", required=True)

    pv = sub.add_parser("validate", help="스키마 + 도메인 규칙 검증")
    pv.add_argument("--json", action="store_true")
    pv.set_defaults(func=_cmd_validate)

    pa = sub.add_parser("add", help="entry 추가 (검증 통과 시에만 기록)")
    pa.add_argument("--id", required=True, help="<track>:<카테고리>/<이름> 형식")
    pa.add_argument("--track", required=True, choices=["art", "se", "bgm", "text"])
    pa.add_argument(
        "--status",
        default="placeholder",
        choices=["placeholder", "generated", "approved", "rejected"],
    )
    pa.add_argument("--spec", required=True, help="에셋 요구 명세 (자연어)")
    pa.add_argument(
        "--requested-by",
        action="append",
        metavar="KIND:PATH",
        help="이 에셋을 필요로 하는 지점. kind=scene_node|code_event|ui|doc. 반복 가능.",
    )
    pa.add_argument("--file", default=None, help="플레이스홀더/실제 파일 경로")
    pa.add_argument("--lore-ref", action="append", metavar="PATH", help="참조 lore/canon 경로. 반복 가능.")
    pa.set_defaults(func=_cmd_add)

    pu = sub.add_parser("update-status", help="entry status 갱신 + history 기록")
    pu.add_argument("--id", required=True)
    pu.add_argument(
        "--status",
        required=True,
        choices=["placeholder", "generated", "approved", "rejected"],
    )
    pu.add_argument("--feedback", default=None, help="반려/검수 피드백 (history 에 기록)")
    pu.add_argument("--file", default=None, help="반영 파일 경로 갱신")
    pu.set_defaults(func=_cmd_update_status)

    ps = sub.add_parser("set-style-guide", help="art lock 승인 결과(스타일 가이드 경로) 잠금")
    ps.add_argument("--path", default=None, help="스타일 가이드 문서 경로 (예: docs/style_guide.md)")
    ps.add_argument("--clear", action="store_true", help="스타일 잠금 해제(null)")
    ps.set_defaults(func=_cmd_set_style_guide)

    pl = sub.add_parser("list", help="entry 목록 출력")
    pl.add_argument("--track", choices=["art", "se", "bgm", "text"])
    pl.add_argument("--status", choices=["placeholder", "generated", "approved", "rejected"])
    pl.add_argument("--json", action="store_true")
    pl.set_defaults(func=_cmd_list)

    return p


def main(argv: list[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    try:
        return args.func(args)
    except (FileNotFoundError, NotADirectoryError, ValueError, json.JSONDecodeError) as exc:
        print(f"오류: {exc}", file=sys.stderr)
        return 2


if __name__ == "__main__":
    raise SystemExit(main())
