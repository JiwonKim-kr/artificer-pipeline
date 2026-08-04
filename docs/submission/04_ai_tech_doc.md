# AI 활용 기술 문서 — 구조 (승부처)

> 목적: "AI를 **어디에·어떻게·왜** 썼는가"로 판단력을 입증. **핵심 = AI를 안 쓴 곳.**
> 사용: 각 섹션의 `> [채움]`을 `> [출처]`의 리포 파일을 읽어 채운다. 코드 인용/파일 경로로 근거를 보이면 설득력↑.
> 고정 메시지 3개(전체를 관통): ① 2계층으로 AI 산출을 오라클과 대조 ② 승인 지점으로 결정권은 사람 ③ **AI를 안 쓴 지점이 신뢰성·재현성을 만든다.**

---

## 1. 개요 / 문제의식
> [채움] 게임 개발에서 **사람만 해야 하는 판단**(디렉션·설계 결정·감각·검수)을 제외한 나머지를 **명령(prompt)만으로** 처리하는 AI 오케스트레이션 파이프라인 → 그것으로 이 게임 제작. "AI 많이 씀"이 아니라 **판단력**이 주제임을 선언.
> [출처] `HANDOFF.md` §1(한 줄 요약)·§2(확정 결정)

## 2. 2계층 아키텍처 (신뢰의 핵심)
> [채움] ① **검증 계층** `sim/opinion-model/`(여론 모델 JS 원본 + 몬테카를로 러너) = 정답 오라클, 웹빌드 제외 ② **런타임 계층** `src/core`·`src/ui`(GDScript 게임) ③ 모델 상수 `opinion_config.json` **단일 출처**(드리프트 0) ④ `opinion_parity_test`가 이식이 오라클과 **비트-정확** 일치함을 매번 검증.
> [출처] `docs/build/gireki_dev_guide.md` §2, `sim/opinion-model/`, `src/core/opinion_model.gd`, `pipeline/tests/opinion_parity_test.gd`, `pipeline/tests/dump_opinion_golden.mjs`
> [팁] "AI/사람이 옮긴 코드를 그냥 믿지 않고 검증된 오라클과 대조한다"를 한 문장으로.

## 3. AI 파이프라인 트랙 + 사람 승인 지점
> [채움] 트랙: **lore**(정본)·**play**(spec→build→test)·**art**(concept→lock→gen→reskin)·**se**(gen→attach)·**lore export**(게임 텍스트 생성·검증·반영). `manifest.json`=트랙 간 유기적 연결의 단일 기록(verify가 정합성 검사). **생략 불가 승인 지점**: `play spec` 승인·`art lock`·`review`.
> [출처] `.claude/commands/*.md`(명령 정의), `pipeline/scripts/*.py`, `pipeline/manifest.json`, `pipeline/schemas/asset-manifest.schema.json`, `HANDOFF.md` §4, `docs/command-catalog.md`
> [팁] 승인 지점 = "결정권은 사람이 쥔다"의 근거.

## 4. AI 쓴 곳 vs 의도적으로 안 쓴 곳 ★ (가장 중요)
> [채움 — 표로]
> **썼다(생산성):**
> - 컨셉 아트 = 범용 모델(FLUX 등) / 스타일 학습·에셋 생성 = Scenario 커스텀 스타일 모델(디젤펑크 고정) → [출처] `.claude/commands/art-*.md`, `pipeline/scripts/scenario_client.py`·`art_post.py`·`art_reskin.py`, `manifest.style_guide`
> - 코드·씬 생성 = Claude Code로 spec→GDScript(여론 엔진 비트-정확 이식 포함)
> - 게임 내 텍스트 = `lore export`로 세계관 정합 댓글 대량 생성(87→132, 커버리지 균형) → [출처] `pipeline/scripts/lore_export.py`, `pipeline/tests/run_lore_export.py`, `src/core/data/content_slice.json`
>
> **안 썼다(의도적 — 신뢰성·재현성):**
> - **여론 엔진 = 검증된 결정론 모델**(런타임 LLM이 여론을 지어내지 않음) → [출처] `src/core/opinion_model.gd`, `sim/opinion-model/`
> - **효과음 = jsfxr 절차생성**(무-API·라이선스 청정·seed 고정 시 동일 바이트 재생성) → [출처] `pipeline/scripts/se_jsfxr.py`, `se_node/render_sfxr.js`, `pipeline/se_specs/*.json`
> - **밸런싱 = 몬테카를로 시뮬(N=4000)**(감이 아니라 수치) → [출처] `sim/opinion-model/balance_montecarlo.mjs`, `docs/build/c6_balance.md`
> - **최종 판단·검수 = 사람**(승인 지점)
> [팁] 이 섹션이 승부처 — "안 쓴 지점이 오히려 이 게임의 신뢰성/재현성을 만든다"로 마무리.

## 5. 재현성 · 검증 장치
> [채움] seeded jsfxr(동일 바이트) · golden fixtures + parity 대조 · 결정론 RNG(mulberry32) · `verify`/`play test` 게이트(임포트·스모크·매니페스트 정합) · GitHub Actions CI.
> [출처] `pipeline/se_specs/`, `pipeline/tests/`(parity·turn·golden), `src/core/rng_mulberry32.gd`, `pipeline/scripts/verify.py`·`play_test.py`, `.github/workflows/verify.yml`

## 6. KPI · 결론
> [채움] 파이프라인 지향 = **명령 1회당 사람 개입(시간·횟수) 최소화**. 결론: AI로 빠르게 만들되 **검증 가능한 축(여론 엔진·재현 효과음·수치 밸런싱)은 결정론으로 못 박은** 제작 방식.
> [출처] `HANDOFF.md`(KPI)

## (선택) 부록
> [채움] 파이프라인 명령 실행 로그·스크린샷, 2계층 다이어그램, parity PASS 캡처 등 근거 자료.
