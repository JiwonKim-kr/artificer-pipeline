---
description: play spec — 아이디어를 승인 대상 구현 명세로 변환 (사람 승인 지점)
argument-hint: <기능 설명>
---

너는 게임 개발 파이프라인의 오케스트레이터다. `play spec` 을 실행한다.
계약: `pipeline/commands/play.md` 의 `play spec` 절. 규칙: `CLAUDE.md`, 컨벤션: `docs/conventions.md`.

**기능**: `$ARGUMENTS`

**목적**: 아이디어를 `docs/specs/<기능>.md` 구현 명세로 변환한다. **이 산출물은 생략 불가한 사람 승인 지점이다** — 승인 전에는 `play build` 로 진행하지 않는다.
**절대 규칙**: 초안은 항상 `status: draft` 로 만든다. Claude 는 스스로 `approved` 로 바꾸지 않는다(승인은 사람의 결정).

$ARGUMENTS 가 비어 있으면 무엇을 명세할지 되묻고 멈춘다.

## 1. 생성 — 명세 초안 작성

1. 설정/세계관이 관련되면 먼저 `python3 pipeline/scripts/lore_index.py --canon lore/canon query "<핵심어>"` 로 canon 을 확인한다(있으면). 참조한 경로는 spec 의 "참조 lore" 에 남긴다.
2. 필요하면 사용자와 2~4개씩 짧게 문답한다(대상 범위, 입력/조작, 성공 조건). 답이 모호하면 되묻는다.
3. 확정된 내용만으로 `docs/specs/<기능>.md`(snake_case) **초안**을 작성한다. 아래 필드를 포함한다:
   - **status**: `draft`
   - **목적(goal)**
   - **수용 기준(acceptance criteria)**: 검증 가능한 조건 목록. 이후 `play test` 스모크가 확인할 항목의 근거.
   - **대상 파일(target files)**: 생성/수정할 `src/core/` 경로(+ 씬 경로). 네이밍은 conventions 준수.
   - **필요 에셋(assets)**: 매니페스트 placeholder 후보. 각 항목에 `id`(`<track>:<카테고리>/<이름>`), 요구 명세, 사용 지점(requested_by 후보: `scene_node:...` 또는 `code_event:...`) 명시.
   - (선택) **참조 lore**: canon 경로.
   - 장르/스타일(예: 로그라이크)은 **spec 문서 데이터로만** 표현하고 코드/스크립트에 하드코딩하지 않는다.

## 2. 자동 검증 (self-check)

파일로 쓰기 전 스스로 점검한 결과를 함께 제시한다:
- 대상 파일이 `src/core/` 보호 영역·snake_case 규칙에 맞는가.
- 각 에셋 `id` 가 `<track>:<카테고리>/<이름>` 형식이고 track prefix 가 일치하는가.
- 수용 기준이 검증 가능한(관찰 가능한) 형태인가.

## 3. 사람 검수

spec 초안 전문과 self-check 요약을 제시하고 **명시적 승인**을 요청한다. **승인 없이는 다음 단계(build)로 가지 않는다.**

## 4. 반영

- 승인 전: `docs/specs/<기능>.md` 를 `status: draft` 로 기록(또는 제시)한다.
- 승인 후: 사용자 지시에 따라 spec 의 `status` 를 `approved` 로 갱신한다. 이 갱신 자체가 build 진입 조건이다.

주의: 이 명령은 `src/core/` 코드를 만들지 않는다. 코드 생성은 승인된 spec 을 받은 `play build` 의 몫이다.
