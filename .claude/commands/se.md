---
description: se 트랙 디스패처 — gen/attach 서브커맨드로 분기 (bgm gen 은 후순위 계약만)
argument-hint: <gen <이벤트 목록> | attach [--id <entry>]> [인자...]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `/se <서브커맨드>` 형태의 호출을 받았다.

전달된 인자: `$ARGUMENTS`

## 분기 규칙

`$ARGUMENTS` 의 **첫 토큰**을 서브커맨드로 해석해 아래로 분기한다. 나머지 토큰은 해당 서브커맨드의 인자다.

- 첫 토큰이 `gen` → `.claude/commands/se-gen.md` 의 지침을 읽고, 나머지 토큰을 이벤트 명세로 삼아 수행한다.
- 첫 토큰이 `attach` → `.claude/commands/se-attach.md` 의 지침을 읽고, 나머지 토큰을 대상 지정으로 삼아 수행한다.
- 인자가 비었거나 알 수 없는 토큰이면: 사용 가능한 서브커맨드(`gen <이벤트 목록>`, `attach [--id <entry>]`)와 각 목적을 한 줄씩 안내하고 멈춘다. 임의 동작을 하지 않는다.
- `bgm` 관련 요청이면: **bgm gen 은 후순위 최소 기능으로 계약만 정의된 상태**(`pipeline/commands/se.md` §bgm gen)임을 알리고, 구현 없이 계약 내용만 안내한다.

## 공통 준수 사항

- 계약 정본은 `pipeline/commands/se.md`, 명령 범위 정본은 `docs/command-catalog.md` 다. 카탈로그에 없는 동작은 수행하지 말고 제안만 한다.
- **SE 생성은 2백엔드 구성**이다: `elevenlabs` = 프롬프트 기반 기본, `jsfxr` = 절차적(레트로 톤, seed 재현 가능). 이벤트별 선택은 데이터(entry `params.backend` 또는 인자)로 표현한다.
- 산출물 규격: **OGG Vorbis · SE 모노 · -16 LUFS** (`docs/conventions.md`). 규칙 경로(`assets/audio/se/`)에는 `se_post.py` 정규화·probe 를 통과한 파일만 둔다.
- **src/core/ 는 수정하지 않는다.** 효과음 연결은 `se_attach.py` 의 브리지 노드(`src/tools/se_emitter.gd`) 삽입으로만 한다.
- 매니페스트 쓰기는 `pipeline/scripts/manifest.py` 를 통해서만 한다. **API 키는 `.env` 로만 참조**한다(하드코딩 금지). 키가 없으면 각 스크립트가 한국어 안내 + 종료 코드 3 으로 멈춘다. 키 없이 요청만 볼 때는 `--dry-run`.

먼저 첫 토큰을 확인하고 해당 서브커맨드 파일을 읽어 실행하라.
