# 「태엽 인간」 인수인계 — 2026-08-02 (역할 분담: 개발=작성자 / 제출용 기술 문서=팀원)

> 기준 브랜치 `game/gireki-sim` (origin 반영 완료). 구조는 [gireki_dev_guide.md](gireki_dev_guide.md), 제출 체크리스트는 [playtest_checklist.md](playtest_checklist.md).
> **역할 분담 변경**: 남은 게임 개발(재설계 P4·P5, 플레이스홀더 치환 등)은 **작성자(나)가 이어서** 진행. **팀원은 제출용 「AI 활용 기술 문서」** 작성을 맡아주면 좋겠음(이 프로젝트의 승부처). 이 문서 = 그 기술 문서를 쓰는 데 필요한 자료·목차.

---

## 1. 지금까지 만들어진 것 (기술 문서 소스이자 프로젝트 현황)

**AI 오케스트레이션 파이프라인**으로 「태엽 인간」(석간지 기자가 진실한 문장을 취사·왜곡해 8턴 안에 여론을 돌리는 시뮬레이터)을 만들고 있음. 데모는 파이프라인의 **검증 대상**이고, 파이프라인 자체가 산출물.

이번까지 본체(`game/gireki-sim`)에 반영된 것:
- **아트**(디젤펑크): 컨셉→lock→gen→reskin (배경·창 프레임·게이지)
- **사운드**: 효과음 5종(jsfxr 절차생성) + SE/BGM 오디오 버스 + 소리 설정 UI
- **재설계 v0.4 P1~P3**: 정보 시간축(정보원 오늘/이월) · 기사 헤드라인+본문 카드 · 「받은 자료」 정보 선별
- **댓글 리얼리티**: 뱅크 51→87 + 작성자 랜덤 닉네임
- 검증: parity/turn/smoke 전부 PASS, 엔진(opinion_model) 불변

---

## 2. 팀원 담당 — 제출용 「AI 활용 기술 문서」

### 목적
해커톤 심사에서 **"AI를 어떻게·어디에·왜 그렇게 썼는가"**를 보여주는 문서. 단순 "AI 많이 씀"이 아니라 **판단력**(어디에 AI를 안 썼는지 포함)이 승부처.

### 제안 목차 + 핵심 메시지
1. **한 줄 요약 / 문제의식** — 게임 개발에서 사람만 해야 하는 일(디렉션·설계 결정·감각·검수)을 제외한 나머지를 **명령만으로** 처리하는 파이프라인.
2. **2계층 아키텍처 (핵심)** — ① 검증 계층 `sim/opinion-model/`(JS 원본 모델 + 몬테카를로 러너) = **정답 오라클**(웹빌드 제외) ② 런타임 계층 `src/core`·`src/ui`(GDScript) = 실제 게임. 모델 상수는 `opinion_config.json` **단일 출처**(sim·게임이 같이 읽음 → 드리프트 0). `opinion_parity_test`가 이식이 오라클과 **비트-정확** 일치함을 보장. → *메시지: "AI가 만든 걸 그냥 믿지 않고 검증된 오라클과 대조한다."*
3. **파이프라인 트랙 + 사람 승인 지점** — `lore`(정본) / `play`(spec→build→test) / `art`(concept→lock→gen→reskin) / `se`(gen→attach). `pipeline/manifest.json` = 트랙 간 유기적 연결의 단일 기록. **승인 지점(생략 불가): play spec 승인 · art lock · review** → *"결정권은 사람이 쥔다."*
4. **AI를 쓴 곳 vs 안 쓴 곳 (승부처)**
   - **썼다**: 컨셉 아트(FLUX), 스타일 학습·에셋 생성(Scenario 커스텀 모델), 코드 생성(Claude Code, spec→GDScript), 콘텐츠·댓글 초안.
   - **안 썼다(의도적)**: 여론 엔진 = 검증된 **결정론 모델**(런타임 AI 아님) · 효과음 = **jsfxr 절차생성**(무-API·라이선스 청정·재현 가능) · 밸런싱 = **몬테카를로 시뮬**(감이 아니라 수치, N=4000) · 최종 판단/검수 = 사람.
   - *메시지: "AI를 안 쓴 지점이 오히려 신뢰성·재현성을 만든다."*
5. **재현성·검증 장치** — seeded jsfxr(동일 바이트 재생성) · golden fixtures + parity 대조 · 결정론 RNG(mulberry32) · verify 게이트(import·스모크·매니페스트 정합).
6. **KPI** — 명령 1회당 **사람 개입 시간(분)·횟수** 하락(모든 개선의 방향).
7. **범용성** — 파이프라인은 장르/스타일을 하드코딩하지 않음(태엽인간은 첫 검증 대상일 뿐. 로그라이크 데모도 병존).

### 문서 쓸 때 참고할 자료 위치 (레포 내)
- `HANDOFF.md` — 파이프라인 확정 결정사항·KPI·트랙 구성
- `docs/build/gireki_dev_guide.md` — 2계층 아키텍처·데이터 흐름·핵심 파일 표
- `docs/conventions.md`, `docs/command-catalog.md` — 명령 규약(정본)
- `pipeline/manifest.json` + `pipeline/schemas/asset-manifest.schema.json` — 에셋 유기 기록
- `pipeline/tests/opinion_parity_test.gd`, `turn_flow_test.gd`, `dump_opinion_golden.mjs` — 검증·골든
- `sim/opinion-model/balance_montecarlo.mjs` + `docs/build/c6_balance.md` — 밸런싱 근거(수치)
- `pipeline/se_specs/*.json` — 효과음 재현 spec / `docs/web-export.md` — 웹 export 실측
- 스크린샷·시연: 게임 실행 화면(CRT OS), 파이프라인 명령 실행 로그

### 팀원이 사람으로서 확인·확보할 것 (심사 필수, 코드로 대체 불가)
- 아트 `review` 승인 여부 · **Pages 배포 URL**(Settings→Pages→GitHub Actions, public 필요) · 시연 영상 · 팀원 역할 기술서

---

## 3. 남은 게임 개발 — 작성자(나)가 진행 (팀원 참고용, 손 안 대도 됨)
- **플레이스홀더 치환**: 기존 댓글 11개 `{대상}`·`{수치}` 리터럴 노출 → 치환 로직
- **Phase 4 기사 본문 prose화**: fact×프레임 authored 본문(블럭 나열 → 문장) · 기사 포커스 제약
- **Phase 5 라이트 경제**: 의뢰→예산→정보원 구매(⚠️ `src/core` → spec 먼저)

> 개발 진행은 `game/gireki-sim`에서 새 브랜치로. src/core는 승인 spec 없이 수정 금지(CLAUDE.md). 매 단계 parity/turn/smoke 게이트 유지.
