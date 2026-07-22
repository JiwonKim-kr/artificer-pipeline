---
description: play test — Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성
argument-hint: (인자 없음) [--project <경로>] [--godot <경로>]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `play test` 를 실행한다.
계약: `pipeline/commands/play.md` 의 `play test` 절. 규칙: `CLAUDE.md`.

**목적**: Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성을 로컬 검증한다(verify 게이트의 play 부분). 이 명령은 **읽기 전용**이다 — 코드/매니페스트를 수정하지 않는다.

## 1. 생성 — 러너 실행

```
python3 pipeline/scripts/play_test.py
```
- 스테이지: (1) Godot headless 임포트 → (2) 스모크 테스트(`pipeline/tests/smoke_test.gd`) → (3) 매니페스트 정합성(스키마 + `file` 지정 entry 의 실제 파일 존재).
- 종료 코드: 0=전체 통과, 1=한 스테이지 이상 실패, 2=러너 오류(godot 실행 파일 없음 등).
- godot 실행 파일 경로가 기본값과 다르면 `--godot <경로>`, 프로젝트 경로가 다르면 `--project <경로>` 를 사용자 요청대로 넘긴다. godot 이 없는 환경에서 정합성만 보려면 `--skip-godot`.

## 2. 판단 / 보고

- 전체 PASS: 결과 요약을 보고한다.
- 실패 스테이지가 있으면 원인을 구분해 제시한다:
  - **임포트 실패**: 출력된 Godot 오류 로그(스크립트 파싱 오류, 리소스 문제)를 짚는다.
  - **스모크 실패**: 스모크 출력의 `[FAIL]`/`SMOKE_RESULT` 라인을 근거로 메인 씬 로드/인스턴스화 문제를 짚는다.
  - **정합성 실패**: 스키마 위반 또는 `missing_file`(매니페스트가 가리키는 파일 부재)을 짚고, `manifest.py` 로 수정하도록 안내한다.
- 수정이 필요하면 해당 작업(`play build` 재실행, placeholder 재배치 등)을 제안한다. 이 명령 자체는 고치지 않는다.

참고: 네이밍·디렉토리 규칙 검사와 lore 정본 모순 검사는 상위 `verify` 명령의 몫이며 이 러너 범위 밖이다. play test 는 임포트·스모크·매니페스트 정합성까지 책임진다.
