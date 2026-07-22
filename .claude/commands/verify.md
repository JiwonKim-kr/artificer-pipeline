---
description: verify — CLAUDE.md 검증 게이트 5항목 통합 검사 + 통합 판정 (읽기 전용)
argument-hint: (인자 없음) [--full] [--skip-godot]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `verify` 를 실행한다.
계약: `pipeline/commands/orchestration.md` 의 `verify` 절. 규칙: `CLAUDE.md` 「검증 게이트」.

**목적**: CLAUDE.md 검증 게이트 5항목을 통합 실행하고 **통합 판정**을 보고한다. 반영 가능 여부의 자동 게이트다. 이 명령은 **읽기 전용**이다 — 검사·판정만 하고 고치지 않는다.

## 1. 생성 — 게이트 러너 실행

```
python3 pipeline/scripts/verify.py
```
- 게이트: (1) Godot headless 임포트 → (2) 스모크 테스트 → (3) 네이밍/디렉토리 규칙 → (4) 매니페스트 정합성 → (5) lore 기계 검사.
- 전 러너까지 돌리려면 `--full` (`pipeline/tests/run_*.py` 자동 발견·실행. 재귀는 환경변수 가드로 방지됨). godot 없는 환경은 `--skip-godot` 로 게이트 1·2 생략.
- 종료 코드: 0=전체 통과(SKIP 포함), 1=게이트/러너 위반, 2=실행 오류.

## 2. 게이트 5 — lore 의미 검사 (Claude 몫)

- `verify.py` 의 게이트 5 는 **기계 검사**(`lore_check.py`: 표기/중복/미등재/미사용)만 한다. canon 이 비어 있으면 SKIP 으로 나온다.
- canon 에 문서가 있으면, 기계 리포트에 더해 **너(Claude)가 canon 을 읽고 의미적 모순**(세계 규칙 vs 세력/인물 서술의 충돌, 연대기 불일치, 공백)을 `/lore-check` 패턴으로 판단해 통합 판정에 포함한다. (`lore query` 로 관련 항목만 추출해 근거로 삼는다.)

## 3. 판단 / 통합 보고

- 게이트별 PASS/FAIL/SKIP 을 종합해 **반영 가능 여부**를 한 줄로 판정한다.
- 실패 게이트는 원인을 구분해 짚는다:
  - **#1 임포트 실패**: Godot 오류 로그(스크립트 파싱/리소스).
  - **#2 스모크 실패**: `SMOKE_RESULT`/`[FAIL]` 라인 → 메인 씬 로드/인스턴스화 문제.
  - **#3 네이밍/디렉토리 위반**: 출력된 `파일:항목` 목록을 그대로 제시하고, 어떤 규칙 위반인지(snake_case/씬 루트 불일치/미등록 PLACEHOLDER/오디오 확장자/스프라이트·UI 경로/매니페스트 id) 설명한다.
  - **#4 정합성 실패**: 스키마 위반 또는 `missing_file` → `manifest.py`/해당 트랙 명령으로 수정 안내.
  - **#5 lore 결함**: 기계 결함 + 의미 모순 후보를 함께 제시.
- 각 위반은 **어떤 트랙 명령으로 고칠지**(예: `play build` 재실행, `art reskin`, `manifest.py add`)를 제안한다. verify 자체는 수정하지 않는다.
