# HANDOFF — Claude Code 작업 인수 문서

> 작성일: 2026-07-14 · 최종 갱신: 2026-07-30 (Phase 1~4 구현 완료 · 게임 제작 단계 진입)
> 이 저장소를 Claude Code로 열었을 때 가장 먼저 읽어야 할 문서.
> 규칙은 `CLAUDE.md`, 명령 범위는 `docs/command-catalog.md`(정본)를 따른다.
> 실시간 현황은 `/status`(읽기 전용)로 확인.

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

## 3. 현재 저장소 상태 (2026-07-30 갱신)

### 기반 (완료)
- [x] 디렉토리 골격 (`src/core` 보호 영역, 트랙별 에셋 경로)
- [x] `CLAUDE.md` 오케스트레이션 규칙
- [x] `docs/command-catalog.md` 명령 카탈로그 v1.0 (정본)
- [x] `docs/conventions.md` 네이밍·규격·커밋 규칙
- [x] `pipeline/schemas/asset-manifest.schema.json` + `manifest.json`
- [x] `project.godot` 생성 — **Godot 4.6.3.stable 초기화 완료**

### 파이프라인 구현 (완료 — 4트랙 + 오케스트레이션 전부 커밋됨)
- [x] **명령 20종** 슬래시 커맨드(`.claude/commands/*.md`) + 보조 스크립트 20종(`pipeline/scripts/*.py`, `se_node/*.js`)
- [x] **lore 트랙**: `init`/`query`/`check` (`lore_index.py`, `lore_check.py`)
- [x] **play 트랙**: `spec`/`build`/`test` — 플레이어 그리드 이동 예제 통과, `play test`에 스크린샷(시각) 검증 단계 포함, 로컬 플레이스홀더 생성기(`placeholder_gen.py`)
- [x] **art 트랙**: `concept`/`lock`/`gen`/`reskin` (`scenario_client.py`, `art_post.py`, `art_reskin.py`) — reskin 후 낡은 placeholder 정리(verify 게이트 #3 갭 수정)
- [x] **se 트랙**: `gen`/`attach` — ElevenLabs(`elevenlabs_client.py`) + jsfxr(`se_jsfxr.py`, `se_node/render_sfxr.js`) 병행, ffmpeg 정규화(`se_post.py`)
- [x] **오케스트레이션 공통**: `plan`/`verify`/`review`/`status` (`verify.py`, `review.py`, `status.py`)
- [x] **CI**: `.github/workflows/verify.yml` (Phase 4 GitHub Actions 도입 완료)
- [x] 로그라이크 데모 잔여물 제거 + 파이프라인 자체 테스트를 픽스처(`pipeline/tests/fixtures/`)로 분리

### 브랜치 구성
- `main` — 파이프라인 정본 (게임 콘텐츠 없음)
- `game/roguelike` — 최초 검증 대상 게임 (로그라이크/픽셀아트)
- **`game/gireki-sim` — 현재 작업 브랜치.** 파이프라인으로 「기레기 시뮬레이터」(디젤펑크 여론 시뮬) 제작 중

### 게임 제작 진행 (`game/gireki-sim`)
- [x] **[plan 0-b] 웹 export 실측 완료** → `docs/web-export.md`. NAN2026 제출 조건("링크 클릭 → 즉시 플레이, 심사자 입력 0")이 Godot 4 웹 빌드로 **성립함을 실측 확정**:
  - 렌더러 `gl_compatibility` 고정 / `thread_support=false`(GitHub Pages 등 헤더 없는 정적 호스팅 구동) / 전송 ≈ 9.03 MB(wasm이 99%, 콘텐츠 증가에 둔감)
  - **CRT 후처리 셰이더 WebGL2 정상 동작 확정** — 배럴왜곡·스캔라인·색수차·비네트. 노드 순서 `[화면] → BackBufferCopy(copy_mode=2) → [CRT ColorRect]`, `hint_screen_texture` 경로. 검증 프래그먼트는 web-export.md에 보존
- [ ] 게임 콘텐츠(spec/canon) 미착수 — `docs/specs`, `lore/canon`은 아직 비어 있음(.gitkeep)
- [ ] web-export.md가 spec 단계로 넘긴 미결: **디자인 해상도·stretch_mode 미설정** / `.gdshader` 경로 규칙 부재(conventions에 추가 필요) / 실화면 FPS 미측정

## 4. 구현 우선순위와 태스크 분해

> **상태(2026-07-30): Phase 1~4 전부 구현 완료.** 아래는 원래 계획으로, 각 Phase 완료 여부를 표시했다.
> 다음 초점은 파이프라인 확장이 아니라 **`game/gireki-sim`에서 게임 콘텐츠 제작**(lore init → play spec → build)이다.

### Phase 1 — `lore init` / `lore query` (기반 계층 먼저) ✅ 완료
1. `pipeline/commands/lore.md` 작성 — 명령을 Claude Code 스킬/슬래시 커맨드 형태로 정의
   - `lore init`: 사용자와 컨셉 문답 → `lore/canon/world.md`, `glossary.md` 등 골격 생성
   - `lore query <질문>`: canon 문서에서 관련 항목만 추출해 답변/컨텍스트 반환
2. `lore check` 최소 구현: canon 내 용어 불일치·모순 후보를 리포트
3. **완료 기준**: 샘플 게임 컨셉 하나로 init → query → check 왕복이 동작

### Phase 2 — `play spec` / `play build` / `play test` (매니페스트 흐름 검증) ✅ 완료
1. `project.godot` 생성 (Godot 4.x, 최소 설정)
2. `play spec`: 아이디어 입력 → `docs/specs/<기능>.md` 명세 생성 → 사람 승인 대기
3. `play build`: 승인된 spec 기반 GDScript + 씬 생성, `PLACEHOLDER_` 에셋 배치,
   **manifest.json에 entry 등록** (스키마 준수, `requested_by`에 씬 노드 경로 기록)
4. `play test`: `godot --headless --import` + 스모크 테스트 스크립트
5. **완료 기준**: 간단한 기능(예: 플레이어 이동) 하나가 spec→build→test 전 과정 통과,
   매니페스트에 placeholder entry가 스키마 검증을 통과한 상태로 기록됨

### Phase 3 — `art` 트랙 ✅ 완료
1. `art concept`: 범용 모델(FLUX.2 또는 GPT Image, Scenario 플랫폼 경유 호출 가능)로 컨셉 후보 복수 생성
2. `art lock`: 선택된 컨셉 이미지들(5~15장 권장)로 **Scenario 커스텀 스타일 모델 학습** → 모델 ID를 스타일 가이드 문서와 `manifest.style_guide`에 기록
3. `art gen`: **Scenario API**(커스텀 모델 지정) 생성 → 플랫폼 내장 후처리(배경 제거, 투명 PNG) 우선 활용, 부족분만 로컬 스크립트(리사이즈, 시트 패킹) → 규칙 경로 저장
   - 검증 게임이 픽셀아트이므로: 픽셀 그리드 정합이 미흡할 경우 픽셀아트 특화 모델(Retro Diffusion 계열) 병행을 재검토
3. `art reskin`: manifest의 placeholder entry를 읽어 씬 파일(.tscn) 내 텍스처 경로 일괄 교체,
   status를 `generated`로 갱신
4. **완료 기준**: Phase 2의 플레이스홀더가 실제 에셋으로 교체되고 verify 통과

### Phase 4 — `se` 트랙 / 오케스트레이션 잔여 ✅ 완료
- `se gen` + `se attach` (ffmpeg 정규화 포함), `plan` / `verify` / `review` / `status` 완성, GitHub Actions CI 도입

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

> 키·도구의 실시간 가용성은 `/status`(값 미노출, 존재 여부만)로 확인한다.

- [x] Godot 4.6.3.stable 설치 + **웹 export template 설치 확인**(`4.6.3.stable`, web-export.md 참고)
- [x] jsfxr 실행 환경 (`pipeline/scripts/se_node/`, Node 의존성 설치됨)
- [ ] Scenario 계정 + API 키 발급 (커스텀 모델 학습 가능 플랜 확인) — 키 부재 시 `art gen` dry-run만 가능
- [ ] ElevenLabs API 키 발급 (SFX 엔드포인트 접근 확인)
- [ ] ffmpeg 설치 (SE 포맷 정규화용)
- [ ] API 키는 `.env`로 관리하고 `.gitignore`에 추가 — 저장소에 커밋 금지
- [ ] CI 웹 빌드용 export template 설치 단계를 워크플로에 추가 (web-export.md §참고)
