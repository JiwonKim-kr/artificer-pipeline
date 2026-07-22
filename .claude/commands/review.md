---
description: review — 사람 검수 큐 제시 + 사람 결정(승인/반려) 반영 (승인 지점 단일 창구)
argument-hint: (인자 없음 = 큐 제시) 이후 항목별 승인/반려를 사람에게서 수집
---

너는 게임 개발 파이프라인의 오케스트레이터다. `review` 를 실행한다.
계약: `pipeline/commands/orchestration.md` 의 `review` 절. 규칙: `CLAUDE.md` 역할 경계.

**핵심 원칙: 승인 여부는 사람이 결정한다.** 이 명령은 승인 지점(에셋 approved · spec 승인 · art lock)의 **단일 창구**다. 너는 검수 큐를 제시하고 사람의 결정을 받아 반영만 한다. **사람 결정 없이 임의로 승인/반려하지 않는다.**

## 1. 생성 — 검수 큐 제시

```
python3 pipeline/scripts/review.py list
```
- (a) `status=generated` 에셋 → approve/reject 대상 (id = entry id)
- (b) `status=draft` spec → approve/reject 대상 (id = `spec:<이름>`)
- (c) `style_guide` 미설정 → art lock 미완 (정보. 승인 대상 아님 → `/art lock` 안내)

## 2. 사람 검수 — 항목별 결정 수집

- 각 대기 항목을 사람이 판단할 수 있게 제시한다:
  - 에셋: 파일 경로·spec·실측 규격(예: 스프라이트 크기/투명, SE 실측 LUFS)을 보여준다.
  - spec: 초안 전문(목적·수용 기준·대상 파일·필요 에셋)을 보여준다.
- 항목마다 **승인 / 반려 + 한 줄 피드백**을 사람에게서 받는다. 답이 없으면 반영하지 않고 기다린다. **추측으로 승인하지 않는다.**

## 3. 반영 — 사람 결정을 스크립트 경유로

승인:
```
python3 pipeline/scripts/review.py approve --id <entry-id 또는 spec:이름>
```
반려(사유 필수):
```
python3 pipeline/scripts/review.py reject --id <...> --reason "<한 줄 피드백>"
```
- 에셋 승인/반려는 `manifest.py update-status` 를 경유한다(단일 쓰기 창구). approve→`approved`, reject→`rejected`(+ history 에 피드백). **generated 상태에서만** 반영된다(생성→검수→반영).
- spec 승인은 문서 `status` 필드를 `approved` 로, 반려는 `draft` 유지 + 사유 노트 추가.
- art lock(스타일 승인)은 여기서 토글하지 않는다 — 커스텀 모델 학습 + 사람 승인이 필요하므로 `/art lock` 으로 안내한다.

## 4. 자동 검증 / 후속

- 반영 후 `python3 pipeline/scripts/manifest.py validate` 로 매니페스트 유효성을 확인한다. 필요하면 `/verify` 로 정합성을 재확인한다.
- 반려된 항목은 재생성 경로(예: `art gen` 재실행, spec 수정 후 재승인)를 제안한다.
