# AI 활용 기술 문서 — 구조 (승부처 · 유의사항 준수 필수)

> 목적: "AI를 **어디에·어떻게·왜** 썼는가"로 판단력 입증. **핵심 = AI를 안 쓴 곳.**
> ⚠️ **유의사항(위배 시 선발 취소)**: ① **사용 AI 도구 + 활용 내역**을 반드시 기재(§4·§5) ② **외부 에셋/오픈소스 출처·라이선스**를 이 문서에 반드시 명시(§7).
> 고정 메시지 3개: ① 2계층으로 AI 산출을 오라클과 대조 ② 승인 지점으로 결정권은 사람 ③ AI를 안 쓴 지점이 신뢰성·재현성을 만든다.

---

## 1. 개요 / 문제의식
> [채움] 사람만 할 판단(디렉션·설계·감각·검수) 빼고 나머지를 **명령(prompt)만으로** 처리하는 AI 오케스트레이션 파이프라인 + 그것으로 게임 제작. [출처] `HANDOFF.md` §1·§2

## 2. 2계층 아키텍처 (신뢰의 핵심)
> [채움] 검증 계층 `sim/opinion-model/`(오라클, 웹빌드 제외) ↔ 런타임 `src/core`·`src/ui`, config 단일 출처, `opinion_parity_test` 비트-정확 대조. [출처] `docs/build/gireki_dev_guide.md` §2, `sim/opinion-model/`, `pipeline/tests/opinion_parity_test.gd`

## 3. 파이프라인 트랙 + 사람 승인 지점
> [채움] lore/play/art/se/lore-export + `manifest.json`(유기 기록) + **승인 지점**(play spec·art lock·review). [출처] `.claude/commands/*.md`, `pipeline/scripts/*.py`, `pipeline/manifest.json`, `HANDOFF.md` §4

## 4. 사용 AI 도구 + 활용 내역 (유의사항 필수)
> [채움 — 표로: 도구 · 용도 · 산출물]
> - **Claude / Claude Code (Anthropic)** — 코드·씬 생성(spec→GDScript, 여론 엔진 비트-정확 이식), 게임 텍스트·문서. [출처] `.claude/commands/`, git 이력
> - **FLUX 등 범용 이미지 모델** — 아트 컨셉 후보 생성(`art concept`). [출처] `.claude/commands/art-concept.md`
> - **Scenario (커스텀 스타일 모델)** — 스타일 학습(`art lock`) + 에셋 생성(`art gen`), 디젤펑크 고정. [출처] `pipeline/scripts/scenario_client.py`, `manifest.style_guide`, `docs/style_guide.md`
> - **lore export** — 세계관 정합 게임 텍스트(댓글) 대량 생성·검증. [출처] `pipeline/scripts/lore_export.py`
> [팁] 각 도구가 **무엇을 얼마나** 만들었는지 활용 내역을 구체 수치로(예: 댓글 87→132, 아트 3종).

## 5. AI 대상 주요 프롬프트 · 지시 사항 (공식 요구)
> [채움] 대표 명령/프롬프트 3~5개를 목적과 함께. 예: play spec(아이디어→명세), art lock(컨셉→스타일 고정), lore export(세계관 정합 댓글), 여론 엔진 이식 지시(비트-정확+parity 대조).
> [출처] `.claude/commands/*.md`(각 명령의 지시 구조), `docs/command-catalog.md`, `CLAUDE.md`(오케스트레이션 규칙)
> [팁] "어떤 제약을 걸었는가"(예: src/core는 승인 spec 없이 수정 금지, config 단일 출처)를 함께 — 프롬프트 설계의 판단력.

## 6. AI 쓴 곳 vs 의도적으로 안 쓴 곳 ★
> [채움] **썼다**: 아트(FLUX/Scenario)·코드(Claude Code)·텍스트(lore export). **안 썼다(의도적)**: 여론 엔진(검증된 결정론 모델)·효과음(jsfxr 절차생성)·밸런싱(몬테카를로 N=4000)·최종 검수(사람).
> [출처] `src/core/opinion_model.gd`, `se_jsfxr.py`/`se_node`, `sim/opinion-model/balance_montecarlo.mjs`+`docs/build/c6_balance.md`
> [팁] "안 쓴 지점이 신뢰성·재현성을 만든다"로 마무리 — 승부처.

## 7. 외부 에셋 / 오픈소스 출처 · 라이선스 (유의사항 필수)
> [채움 — 표로: 항목 · 출처 · 라이선스 · 용도] · 확실치 않은 라이선스는 반드시 원본 확인.
> - **Godot Engine 4.x** — godotengine.org — MIT — 게임 엔진
> - **jsfxr** (효과음 절차생성) — 퍼블릭 도메인(코드 주석 근거 `se_jsfxr.py`) — SE 생성
> - **neodgm 한글 폰트** — `[출처·라이선스 확인]` (`assets/fonts/neodgm.ttf`) — 웹 한글 렌더
> - **아트 에셋(desk_bg·window frame·gauge 등)** — **자체 생성**(Scenario 커스텀 스타일 모델, FLUX 컨셉) — 저작권 자체 보유, 생성 도구 명시
> - **효과음(.ogg)** — **자체 생성**(jsfxr 절차생성, 재현 spec `pipeline/se_specs/`) — 외부 에셋 아님
> - **파이프라인 의존성** — `wasm-media-encoders`, `certifi` 등 `[각 라이선스 확인]` (`pipeline/scripts/se_node/package.json`, `requirements` 류)
> [팁] "AI 생성 에셋 = 어떤 도구로 생성했는지 명시" + "외부 라이브러리 = 라이선스 명시". 하나라도 누락 시 유의사항 위배.

## 8. 재현성 · 검증
> [채움] seeded jsfxr(동일 바이트)·golden+parity·결정론 RNG(mulberry32)·verify/CI 게이트. [출처] `pipeline/se_specs/`, `pipeline/tests/`, `.github/workflows/verify.yml`

## 9. KPI · 결론
> [채움] 명령당 사람 개입 최소화 + "검증 가능한 축은 결정론으로 못 박음". [출처] `HANDOFF.md`(KPI)
