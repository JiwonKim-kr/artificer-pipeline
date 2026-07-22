---
description: plan — 목표를 트랙별 태스크로 분해, 실행 순서·승인 지점 제시 (읽기 전용)
argument-hint: <목표> (예: 슬라임 적 추가, 이동에 발소리 붙이기)
---

너는 게임 개발 파이프라인의 오케스트레이터다. `plan` 을 실행한다.
계약: `pipeline/commands/orchestration.md` 의 `plan` 절. 규칙: `CLAUDE.md`, 명령 범위 정본: `docs/command-catalog.md`.

**목표**: `$ARGUMENTS` (자연어. 비었으면 목표를 물어보고 멈춘다.)

이 명령은 **읽기 전용**이다 — 계획만 세우고 어떤 파일도 쓰거나 명령을 실행하지 않는다.

## 1. 현황 파악

```
python3 pipeline/scripts/status.py --json
```
- 매니페스트 entry(트랙·status), spec 상태, lore 초기화 여부, `style_guide`(art lock) 여부, `.env` 키/도구 가용성을 확인한다. 이게 분해의 근거다.

## 2. 목표를 트랙별 태스크로 분해 (판단)

- 목표를 `docs/command-catalog.md` 의 명령들로 매핑해 **트랙별(lore/play/art/se) 태스크**로 나눈다.
- 실행 순서는 카탈로그 §대표 워크플로(play-first / design-first)를 기준으로 잡는다. 현황상 선행이 안 된 것을 순서에 반영한다:
  - `style_guide` 미설정인데 실제 에셋이 필요하면 → `art lock` 을 `art gen` 앞에 둔다.
  - 세계관 참조가 필요한데 canon 미초기화면 → 필요 시 `lore init` 을 앞에 둔다.
  - play 산출물(placeholder)이 없으면 → `play spec`→`play build` 를 art/se 앞에 둔다.
- **생략 불가 승인 지점**을 태스크 순서에 명확히 표시한다: **play spec 승인 · art lock · review**.
- **카탈로그에 없는 동작은 태스크로 넣지 않는다.** 필요하면 "제안"으로만 따로 남긴다. (CLAUDE.md 원칙 1)
- 장르/스타일(로그라이크·픽셀아트)을 계획 로직에 하드코딩하지 않는다 — 그 성격은 lore/spec/style_guide **데이터**로만 반영한다.

## 3. 계획 제시

- 트랙별 태스크 목록 + 실행 순서(번호) + 각 태스크의 근거 명령(예: `play build`) + 승인 지점 표시 + 선행 의존성을 한 화면으로 제시한다.
- 마지막에 "이 계획대로 진행할까요?"로 사용자 확인을 받는다. **승인 전에는 개별 명령을 실행하지 않는다.** 승인하면 각 명령(`/play spec` 등)으로 하나씩 진행한다.
