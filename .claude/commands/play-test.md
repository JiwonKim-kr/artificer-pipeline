---
description: play test — Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성 (+옵션: 스크린샷 시각 검증)
argument-hint: (인자 없음) [--project <경로>] [--godot <경로>] [--screenshot]
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

## 1b. (옵션) 시각 검증 — 스크린샷

기본 스테이지는 "씬이 로드/인스턴스화되는가"만 headless 로 빠르게 확인할 뿐, **화면에 무엇이 보이는지**는 알 수 없다. 실제 렌더 결과를 눈으로(그리고 픽셀 검사로) 판정하려면 `--screenshot` 을 붙인다:

```
python3 pipeline/scripts/play_test.py --screenshot
```
- 메인 씬(또는 `--shot-scene res://scenes/xxx.tscn`)을 **실제로 렌더**해 PNG 로 저장하고, 저장된 이미지가 비어있지 않은지(존재·크기·**비-단색**) 검증한다. 저장 경로 기본값은 `pipeline/artifacts/screenshot.png`(`.gitignore` 처리됨), `--shot-output <경로>` 로 바꿀 수 있다.
- **왜 headless 가 아닌가**: 순수 `--headless` 는 더미 렌더 드라이버라 뷰포트 캡처가 불가하고 프로세스가 무한 대기한다. 그래서 이 스테이지는 headless 를 쓰지 않는다.
  - **macOS/GUI 데스크톱**: `--rendering-driver opengl3` 로 실제 렌더. **창이 잠깐 뜬다**(정상). 렌더가 끝나면 프로세스는 자동 종료된다.
  - **Linux(CI/서버, GUI 없음)**: `xvfb-run` 가상 디스플레이가 있어야 렌더된다. `xvfb-run` 이 없으면 스테이지가 명확한 안내와 함께 실패한다.
- **옵트인 이유**: 실제 렌더는 무겁고 창이 뜨므로 기본 `play test`(빠른 headless)에는 포함하지 않는다. 시각 확인이 필요할 때만 명시적으로 붙인다. 타임아웃(`--shot-timeout`, 기본 120s)으로 무한 대기를 막고, 실패/완료 시 렌더 프로세스를 확실히 정리한다.
- 튜닝: `--shot-frames N`(캡처 전 대기 프레임, 기본 12), `--shot-scene`, `--shot-output`, `--shot-timeout`.
- 통과 시 저장된 PNG 절대경로가 리포트에 찍힌다. **그 경로를 사람에게 제시**해 눈으로 게임 화면을 판정하게 한다(빈 렌더/까만 화면이면 스테이지가 FAIL 로 먼저 잡는다).

## 2. 판단 / 보고

- 전체 PASS: 결과 요약을 보고한다.
- 실패 스테이지가 있으면 원인을 구분해 제시한다:
  - **임포트 실패**: 출력된 Godot 오류 로그(스크립트 파싱 오류, 리소스 문제)를 짚는다.
  - **스모크 실패**: 스모크 출력의 `[FAIL]`/`SMOKE_RESULT` 라인을 근거로 메인 씬 로드/인스턴스화 문제를 짚는다.
  - **정합성 실패**: 스키마 위반 또는 `missing_file`(매니페스트가 가리키는 파일 부재)을 짚고, `manifest.py` 로 수정하도록 안내한다.
  - **스크린샷 실패**(`--screenshot` 시): 원인을 구분한다 — 타임아웃(창 미표시/GL 컨텍스트 실패, Linux 라면 `xvfb-run` 부재), `SHOT_ERROR`(씬 로드/저장 실패), 또는 **빈/단색 렌더 감지**(까만 화면). 빈 렌더면 씬에 보이는 노드가 있는지·카메라/뷰포트를 점검하도록 안내한다.
- 수정이 필요하면 해당 작업(`play build` 재실행, placeholder 재배치 등)을 제안한다. 이 명령 자체는 고치지 않는다.

참고: 네이밍·디렉토리 규칙 검사와 lore 정본 모순 검사는 상위 `verify` 명령의 몫이며 이 러너 범위 밖이다. play test 는 임포트·스모크·매니페스트 정합성(+옵션 스크린샷 시각 검증)까지 책임진다.
