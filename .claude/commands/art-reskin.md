---
description: art reskin — 매니페스트 기반 placeholder를 실제 에셋으로 씬에서 일괄 교체
argument-hint: [--id <매니페스트 ID> | 씬/범위] [--dry-run]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `art reskin` 을 실행한다.
계약: `pipeline/commands/art.md` 의 `art reskin` 절. 규칙: `CLAUDE.md`.

**대상**: `$ARGUMENTS` (예: `--id art:player/player_idle`, 또는 특정 씬/범위. 비우면 실제 에셋이 준비된 `placeholder` entry 전체)

**목적**: 매니페스트를 기준으로 씬(.tscn) 안의 **placeholder 텍스처 경로를 실제 에셋 경로로 일괄 교체**하고, 상태를 `placeholder → generated` 로 갱신한다. `art gen` 이 만들어 둔 실제 에셋을 게임에 연결하는 단계다.

**절대 규칙**: 매니페스트 쓰기는 **`manifest.py` 를 통해서만**(스크립트가 내부적으로 경유). 최종 승인(`approved`)은 상위 `review`(사람) 몫이며 reskin 이 임의로 approve 하지 않는다.

## 1. 생성 — 계획 확인 (먼저 dry-run 권장)

```
python3 pipeline/scripts/art_reskin.py [--id <매니페스트 ID>] --dry-run
```
- 각 대상 entry 의 placeholder→실제 경로 유도 결과와, 어떤 씬에서 몇 건 교체될지 계획을 출력한다(아무것도 쓰지 않음).
- 실제 에셋이 아직 없으면(`art gen` 미실행) 해당 entry 는 `SKIP` 으로 표시된다 — 크래시가 아니다. 먼저 `art gen` 을 안내한다.

## 2. 반영 — 교체 + 상태 갱신 + 재임포트

```
python3 pipeline/scripts/art_reskin.py [--id <매니페스트 ID>]
```
- 씬의 `res://<placeholder>` → `res://<실제 경로>` 치환, `manifest.py update-status` 로 `generated` + `file` 갱신, `godot --headless --import` 재임포트까지 수행한다.
- Godot 재임포트를 생략하려면 `--skip-import`. 대상 프로젝트가 다르면 `--project <경로>`(매니페스트/스키마는 프로젝트 하위에서 자동 유도).

## 3. 자동 검증

```
python3 pipeline/scripts/play_test.py
```
- 임포트·스모크·매니페스트 정합성이 모두 PASS 여야 한다(교체된 실제 에셋이 존재하고 씬이 정상 로드되는지). 실패 시 원인을 짚고 수정한다.

## 4. 사람 검수 / 반영

- 변경 요약(교체된 씬·건수, 갱신된 매니페스트 entry, `play test` 결과)을 제시한다.
- 커밋은 사용자 승인 후에만. 커밋 제목은 `[art reskin] <요약>` 형식(conventions).

주의: 이 명령은 **실데이터를 바꾼다**(씬·매니페스트). 테스트/실험은 저장소를 임시 디렉토리에 복제하고 `--project <복제본>` 으로 수행해 실데이터를 보호한다.
