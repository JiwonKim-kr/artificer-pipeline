# HANDOFF — Claude Code 작업 인수 문서

> 작성일: 2026-07-14 · 최종 갱신: 2026-07-14 (미결정 항목 전부 확정)
> 이 저장소를 Claude Code로 열었을 때 가장 먼저 읽어야 할 문서.
> 규칙은 `CLAUDE.md`, 명령 범위는 `docs/command-catalog.md`(정본)를 따른다.

## 1. 프로젝트 한 줄 요약

Godot 게임 개발에서 개발자가 직접 해야만 하는 작업(디렉션, 설계 결정, 감각 판단, 검수)을 제외한
대부분의 작업을 **명령만으로** 처리하는 AI 파이프라인을 구축한다.

## 2. 확정된 결정 사항

| 항목 | 결정 | 근거 |
|---|---|---|
| 엔진 | **Godot 4.x** | 텍스트 기반 씬/리소스로 AI 조작 용이, headless CLI 자동화 |
| 트랙 구성 | 플레이 / 디자인 / 사운드 + **로어(기반 계층)** | 로어는 병렬 트랙이 아닌 전 트랙 참조 정본 |
| 워크플로 | play-first, design-first **양방향 지원** | 단일 진입점 비고집, 유기성은 필수 |
| 사운드 | 후순위, **SE 중심** (BGM 최소 기능) | 사용자 지시 |
| 유기성 장치 | `pipeline/manifest.json` 에셋 매니페스트 | 트랙 간 연결의 단일 기록 |
| 승인 지점 | play spec 승인 / art lock / review — **생략 불가** | 사람 개입 최소화하되 결정권은 유지 |
| KPI | 명령 1회당 사람 개입 시간(분)·횟수 | 모든 개선은 이 수치 하락 방향 |
| 이미지 생성 | `art concept`=범용 모델(FLUX.2/GPT Image), `art lock`/`art gen`=**Scenario API + 커스텀 스타일 모델** | 편의성·퀄리티 제어 우선(비용 후순위). 게임 특화 기능(투명 PNG, 스프라이트시트, 배경 제거)과 API 통합 |
| SE 생성 | **ElevenLabs SFX API 기본 + jsfxr 병행**(검증 게임이 픽셀아트이므로 병행 활성) | 프롬프트 기반 API가 `se gen` 구조와 직결. 레트로 톤은 절차적 생성이 적합 |
| Godot 버전 | **4.6.x 고정** (업그레이드는 verify 전체 통과 조건부) | 4.7은 출시 직후로 검증 부족. AI 생성 코드 재현성 확보 |
| CI | Phase 2 로컬 verify → **Phase 4에서 GitHub Actions** | 초기 CI 세팅은 KPI 기여 대비 비용 과다 |
| 검증 대상 게임 | **로그라이크 / 픽셀아트** | 파이프라인은 범용 설계 유지. 이는 첫 검증 대상일 뿐 시스템에 하드코딩하지 않는다 |

## 3. 현재 저장소 상태

- [x] 디렉토리 골격 (`src/core` 보호 영역, 트랙별 에셋 경로)
- [x] `CLAUDE.md` 오케스트레이션 규칙
- [x] `docs/command-catalog.md` 명령 카탈로그 v1.0 (정본)
- [x] `docs/conventions.md` 네이밍·규격·커밋 규칙
- [x] `pipeline/schemas/asset-manifest.schema.json` + 빈 `manifest.json`
- [ ] 명령 구현 전무 — **다음 작업은 여기서 시작**
- [ ] Godot 프로젝트 파일(`project.godot`) 미생성 — 첫 구현 시 함께 생성

## 4. 구현 우선순위와 태스크 분해

### Phase 1 — `lore init` / `lore query` (기반 계층 먼저)
1. `pipeline/commands/lore.md` 작성 — 명령을 Claude Code 스킬/슬래시 커맨드 형태로 정의
   - `lore init`: 사용자와 컨셉 문답 → `lore/canon/world.md`, `glossary.md` 등 골격 생성
   - `lore query <질문>`: canon 문서에서 관련 항목만 추출해 답변/컨텍스트 반환
2. `lore check` 최소 구현: canon 내 용어 불일치·모순 후보를 리포트
3. **완료 기준**: 샘플 게임 컨셉 하나로 init → query → check 왕복이 동작

### Phase 2 — `play spec` / `play build` / `play test` (매니페스트 흐름 검증)
1. `project.godot` 생성 (Godot 4.x, 최소 설정)
2. `play spec`: 아이디어 입력 → `docs/specs/<기능>.md` 명세 생성 → 사람 승인 대기
3. `play build`: 승인된 spec 기반 GDScript + 씬 생성, `PLACEHOLDER_` 에셋 배치,
   **manifest.json에 entry 등록** (스키마 준수, `requested_by`에 씬 노드 경로 기록)
4. `play test`: `godot --headless --import` + 스모크 테스트 스크립트
5. **완료 기준**: 간단한 기능(예: 플레이어 이동) 하나가 spec→build→test 전 과정 통과,
   매니페스트에 placeholder entry가 스키마 검증을 통과한 상태로 기록됨

### Phase 3 — `art` 트랙
1. `art concept`: 범용 모델(FLUX.2 또는 GPT Image, Scenario 플랫폼 경유 호출 가능)로 컨셉 후보 복수 생성
2. `art lock`: 선택된 컨셉 이미지들(5~15장 권장)로 **Scenario 커스텀 스타일 모델 학습** → 모델 ID를 스타일 가이드 문서와 `manifest.style_guide`에 기록
3. `art gen`: **Scenario API**(커스텀 모델 지정) 생성 → 플랫폼 내장 후처리(배경 제거, 투명 PNG) 우선 활용, 부족분만 로컬 스크립트(리사이즈, 시트 패킹) → 규칙 경로 저장
   - 검증 게임이 픽셀아트이므로: 픽셀 그리드 정합이 미흡할 경우 픽셀아트 특화 모델(Retro Diffusion 계열) 병행을 재검토
3. `art reskin`: manifest의 placeholder entry를 읽어 씬 파일(.tscn) 내 텍스처 경로 일괄 교체,
   status를 `generated`로 갱신
4. **완료 기준**: Phase 2의 플레이스홀더가 실제 에셋으로 교체되고 verify 통과

### Phase 4 — `se` 트랙 / 오케스트레이션 잔여
- `se gen` + `se attach` (ffmpeg 정규화 포함), `plan` / `verify` / `review` / `status` 완성

## 5. 구현 형태 가이드

- 각 명령은 **Claude Code 슬래시 커맨드(.claude/commands/) 또는 스킬** + 필요 시 보조 스크립트(`pipeline/scripts/`, Python 권장)로 구현
- 결정 로직(문답, 명세 작성, 코드 생성)은 Claude가, 기계적 처리(이미지 후처리, ffmpeg, JSON 검증)는 스크립트가 담당
- manifest 읽기/쓰기는 반드시 스키마 검증을 거치는 단일 헬퍼 스크립트로 통일 (`pipeline/scripts/manifest.py` 권장)

## 6. 확정된 결정 (구 미결정 항목 — 전부 해소됨, 2026-07-14)

1. **이미지 생성**: 2층 구성. `art concept`=범용 프런티어 모델(FLUX.2/GPT Image), `art lock`+`art gen`=Scenario API + 커스텀 스타일 모델. 로컬 ComfyUI는 편의성 기준 미달로 배제하되, 픽셀아트 그리드 정합 문제 발생 시 Retro Diffusion 계열 병행만 예외 재검토.
2. **SE 생성**: ElevenLabs SFX API 기본. 검증 게임이 픽셀아트로 확정되어 jsfxr(절차적 생성) 병행 활성. `se gen`은 이벤트별로 두 백엔드 중 선택 가능하게 구현.
3. **검증 대상 게임**: 로그라이크 장르, 픽셀아트 스타일. **단, 파이프라인은 범용으로 설계한다** — 장르/스타일 의존 로직을 명령·스크립트에 하드코딩하지 말고 lore/스타일 가이드/manifest의 데이터로만 표현할 것.
4. **Godot**: 4.6.x 최신 유지보수 버전으로 고정. 업그레이드는 `verify` 전체 통과를 조건으로만 허용.
5. **CI**: Phase 2는 로컬 `verify` 스크립트로 운용, GitHub Actions 도입은 Phase 4.

## 7. 작업 환경 준비 체크리스트 (code 환경에서 최초 1회)

- [ ] Godot 4.6.x 설치 및 `godot --headless --version` 동작 확인
- [ ] Scenario 계정 + API 키 발급 (커스텀 모델 학습 가능 플랜 확인)
- [ ] ElevenLabs API 키 발급 (SFX 엔드포인트 접근 확인)
- [ ] jsfxr 실행 환경 (Node 또는 Python 포팅 중 택1)
- [ ] ffmpeg 설치 (SE 포맷 정규화용)
- [ ] API 키는 `.env`로 관리하고 `.gitignore`에 추가 — 저장소에 커밋 금지
