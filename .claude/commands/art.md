---
description: art 트랙 디스패처 — concept/lock/gen/reskin 서브커맨드로 분기
argument-hint: <concept <주제> | lock | gen <에셋 명세> | reskin <씬/범위>> [인자...]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `/art <서브커맨드>` 형태의 호출을 받았다.

전달된 인자: `$ARGUMENTS`

## 분기 규칙

`$ARGUMENTS` 의 **첫 토큰**을 서브커맨드로 해석해 아래로 분기한다. 나머지 토큰은 해당 서브커맨드의 인자다.

- 첫 토큰이 `concept` → `.claude/commands/art-concept.md` 의 지침을 읽고, 나머지 토큰을 주제로 삼아 수행한다.
- 첫 토큰이 `lock` → `.claude/commands/art-lock.md` 의 지침을 읽고 그대로 수행한다. **(생략 불가 사람 승인 지점)**
- 첫 토큰이 `gen` → `.claude/commands/art-gen.md` 의 지침을 읽고, 나머지 토큰을 에셋 명세로 삼아 수행한다.
- 첫 토큰이 `reskin` → `.claude/commands/art-reskin.md` 의 지침을 읽고, 나머지 토큰을 씬/범위로 삼아 수행한다.
- 인자가 비었거나 알 수 없는 토큰이면: 사용 가능한 서브커맨드(`concept <주제>`, `lock`, `gen <에셋 명세>`, `reskin <씬/범위>`)와 각 목적을 한 줄씩 안내하고 멈춘다. 임의 동작을 하지 않는다.

## 공통 준수 사항

- 계약 정본은 `pipeline/commands/art.md`, 명령 범위 정본은 `docs/command-catalog.md` 다. 카탈로그에 없는 동작은 수행하지 말고 제안만 한다.
- **이미지 생성은 2층 구성**이다: `concept` = 범용 모델(FLUX.2/GPT Image, Scenario 경유), `lock`/`gen` = Scenario 커스텀 스타일 모델.
- **`art lock` 승인은 생략 불가한 사람 승인 지점(아트 스타일 승인)이다.** 스타일이 잠기기 전에는 `gen` 을 양산 목적으로 진행하지 않는다.
- `assets/art/` 쓰기는 art 명령(`gen`·컨셉 저장)만 한다. 매니페스트 쓰기는 `pipeline/scripts/manifest.py` 를 통해서만 한다.
- **API 키는 `.env` 로만 참조**한다(코드·문서·매니페스트에 하드코딩 금지). 키가 없으면 각 스크립트가 한국어 안내 + 종료 코드 3 으로 멈춘다. 키 없이 요청만 볼 때는 `--dry-run`.

먼저 첫 토큰을 확인하고 해당 서브커맨드 파일을 읽어 실행하라.
