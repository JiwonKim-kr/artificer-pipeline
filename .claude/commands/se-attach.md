---
description: se attach — 매니페스트 code_event 기반으로 효과음을 씬에 자동 연결
argument-hint: [--id <매니페스트 ID>] [--dry-run] [--allow-placeholder]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `se attach` 를 실행한다.
계약: `pipeline/commands/se.md` 의 `se attach` 절. 규칙: `CLAUDE.md`.

**대상**: `$ARGUMENTS` (예: `--id se:player_step`. 비우면 실제 에셋이 준비된 `placeholder` se entry 전체)

**목적**: 매니페스트의 `requested_by: code_event:<스크립트>::<메서드>` 를 읽어, 그 스크립트가 붙은 씬에 **AudioStreamPlayer + 범용 브리지(`src/tools/se_emitter.gd`)** 노드를 삽입하고 상태를 `placeholder → generated` 로 갱신한다. `se gen` 이 만들어 둔 정규화 에셋을 게임에 연결하는 단계다.

**절대 규칙**:
- **src/core/ 는 수정하지 않는다.** 연결은 씬(.tscn)에 브리지 노드를 삽입하는 방식으로만 한다(게임 로직은 시그널만 발산, 브리지가 `_ready` 에서 구독).
- 매니페스트 쓰기는 **`manifest.py` 를 통해서만**(스크립트가 내부적으로 경유). 최종 승인(`approved`)은 상위 `review`(사람) 몫이며 attach 가 임의로 approve 하지 않는다.

## 1. 생성 — 계획 확인 (먼저 dry-run 권장)

```
python3 pipeline/scripts/se_attach.py [--id <매니페스트 ID>] --dry-run
```
- entry 별로 「스크립트::메서드 → 유도된 시그널 → 대상 씬/노드 → 연결할 스트림」 계획을 출력한다(무변경).
- 실제 에셋이 아직 없으면(`se gen` 미실행) `SKIP` 으로 표시된다 — 크래시가 아니다. 먼저 `se gen` 을 안내한다. (`--allow-placeholder` 로 플레이스홀더 연결도 가능 — 이때 매니페스트 상태는 placeholder 유지.)
- 시그널 유도가 모호하면(복수 emit 등) entry `params.signal` 또는 `--signal`(단일 `--id` 시)로 명시한다.

## 2. 반영 — 삽입 + 상태 갱신 + 재임포트

```
python3 pipeline/scripts/se_attach.py [--id <매니페스트 ID>]
```
- 씬에 브리지 노드 삽입(멱등: 이미 연결된 씬은 skip, 플레이스홀더→실제 업그레이드는 경로 교체), `manifest.py update-status` 로 `generated` + `file` 갱신, `godot --headless --import` 재임포트까지 수행한다.
- 재임포트 생략은 `--skip-import`. 대상 프로젝트가 다르면 `--project <경로>`(매니페스트/스키마는 프로젝트 하위에서 자동 유도).

## 3. 자동 검증

```
python3 pipeline/scripts/play_test.py
```
- 임포트·스모크·매니페스트 정합성이 모두 PASS 여야 한다(브리지가 붙은 씬이 정상 로드되는지). 실패 시 원인을 짚고 수정한다.

## 4. 사람 검수 / 반영

- 변경 요약(삽입 노드·시그널·스트림 경로, 갱신된 entry, `play test` 결과)을 제시한다.
- 커밋은 사용자 승인 후에만. 커밋 제목은 `[se attach] <요약>` 형식(conventions).

주의: 이 명령은 **실데이터를 바꾼다**(씬·매니페스트). 테스트/실험은 저장소를 임시 디렉토리에 복제하고 `--project <복제본>` 으로 수행해 실데이터를 보호한다.
