---
description: status — 프로젝트·태스크 현황 요약 (읽기 전용, 비밀값은 존재 여부만)
argument-hint: (인자 없음) [--json]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `status` 를 실행한다.
계약: `pipeline/commands/orchestration.md` 의 `status` 절. 규칙: `CLAUDE.md`.

**목적**: 파이프라인 전체 현황을 한눈에 모아 보고한다. 이 명령은 **읽기 전용**이다.

## 1. 생성 — 현황 수집

```
python3 pipeline/scripts/status.py
```
- 기계 처리용으로 요약이 필요하면 `--json`.
- 수집 항목: 매니페스트 entry(트랙별·status별 집계 + id), `style_guide`(art lock) 여부, `docs/specs/*` 의 spec status, `lore/canon` 정본 문서 수, `.env` 키(**존재 여부만** — 값 미노출), 도구 버전(godot/ffmpeg/node), 테스트 러너 목록.

## 2. 보고

- 요약을 제시한다. 특히 다음을 눈에 띄게 짚는다:
  - **승인 대기**: `generated` 에셋(→ `/review` 대상), `draft` spec(→ 승인 대기).
  - **선행 미완**: `style_guide` 미설정(art lock 미완), canon 미초기화(lore 미실행).
  - **키/도구 가용성**: 생성 계열 명령 실행 가능 여부(예: Scenario/ElevenLabs 키 부재 시 dry-run 만 가능).
- **비밀값은 절대 출력하지 않는다.** status.py 가 존재 여부만 마스킹해 주므로 그 결과를 그대로 전달한다.
- 다음 행동이 필요하면 관련 명령(`/plan`, `/review`, `/verify`, 개별 트랙 명령)을 제안한다.
