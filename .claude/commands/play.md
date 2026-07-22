---
description: play 트랙 디스패처 — spec/build/test 서브커맨드로 분기
argument-hint: <spec <기능> | build <명세> | test> [인자...]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `/play <서브커맨드>` 형태의 호출을 받았다.

전달된 인자: `$ARGUMENTS`

## 분기 규칙

`$ARGUMENTS` 의 **첫 토큰**을 서브커맨드로 해석해 아래로 분기한다. 나머지 토큰은 해당 서브커맨드의 인자다.

- 첫 토큰이 `spec` → `.claude/commands/play-spec.md` 의 지침을 읽고, 나머지 토큰을 기능 설명으로 삼아 수행한다.
- 첫 토큰이 `build` → `.claude/commands/play-build.md` 의 지침을 읽고, 나머지 토큰을 대상 spec 으로 삼아 수행한다.
- 첫 토큰이 `test` → `.claude/commands/play-test.md` 의 지침을 읽고 그대로 수행한다.
- 인자가 비었거나 알 수 없는 토큰이면: 사용 가능한 서브커맨드(`spec <기능>`, `build <명세>`, `test`)와 각 목적을 한 줄씩 안내하고 멈춘다. 임의 동작을 하지 않는다.

## 공통 준수 사항

- 계약 정본은 `pipeline/commands/play.md`, 명령 범위 정본은 `docs/command-catalog.md` 다. 카탈로그에 없는 동작은 수행하지 말고 제안만 한다.
- **`play spec` 승인은 생략 불가한 사람 승인 지점이다.** spec 이 `approved` 가 아니면 `play build` 를 진행하지 않는다.
- `src/core/` 는 승인된 spec 없이 수정하지 않는다. 매니페스트 쓰기는 `pipeline/scripts/manifest.py` 를 통해서만 한다.
- 결정/설계는 네가, 기계적 처리(스키마 검증·쓰기, 임포트·스모크)는 `pipeline/scripts/manifest.py` · `play_test.py` 가 담당한다.

먼저 첫 토큰을 확인하고 해당 서브커맨드 파일을 읽어 실행하라.
