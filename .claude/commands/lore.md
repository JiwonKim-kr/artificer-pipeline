---
description: lore 트랙 디스패처 — init/query/check 서브커맨드로 분기
argument-hint: <init | query <질문> | check> [인자...]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `/lore <서브커맨드>` 형태의 호출을 받았다.

전달된 인자: `$ARGUMENTS`

## 분기 규칙

`$ARGUMENTS` 의 **첫 토큰**을 서브커맨드로 해석해 아래로 분기한다. 나머지 토큰은 해당 서브커맨드의 인자다.

- 첫 토큰이 `init` → `.claude/commands/lore-init.md` 의 지침을 읽고 그대로 수행한다.
- 첫 토큰이 `query` → `.claude/commands/lore-query.md` 의 지침을 읽고, 나머지 토큰을 질문으로 삼아 수행한다.
- 첫 토큰이 `check` → `.claude/commands/lore-check.md` 의 지침을 읽고 그대로 수행한다.
- 인자가 비었거나 알 수 없는 토큰이면: 사용 가능한 서브커맨드(`init`, `query <질문>`, `check`)와 각 목적을 한 줄씩 안내하고 멈춘다. 임의 동작을 하지 않는다.

## 공통 준수 사항

- 계약 정본은 `pipeline/commands/lore.md`, 명령 범위 정본은 `docs/command-catalog.md` 다. 카탈로그에 없는 동작은 수행하지 말고 제안만 한다.
- `lore/canon/` 쓰기는 사용자 승인 이후에만 한다. `query`/`check` 는 읽기 전용이다.
- 결정/판단은 네가, 기계적 처리(파싱·검색·표기 검사)는 `pipeline/scripts/lore_*.py` 가 담당한다.

먼저 첫 토큰을 확인하고 해당 서브커맨드 파일을 읽어 실행하라.
