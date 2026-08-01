# 「태엽 인간」 스타일 가이드 — taeyeop-dieselpunk v1.0

> art lock 산출물(사람 승인 지점). 이후 모든 `art gen`/후처리·추가 에셋은 이 문서를 기준으로 한다.
> 승인일: 2026-08-01 (사람 승인) · 브랜치 `gireki-art` · 근거 컨셉: `assets/art/concepts/` 13장 (커밋 7d4ed5d)

## 1. 잠금 수단 — 프롬프트 규약 (편차 명시)

**정식 계약(커스텀 LoRA 학습)은 Scenario 플랜 제한으로 보류됐다**
(`PlanLimitReachedError: parallel-training actionLimit 0` — 현 플랜은 학습 미지원, 2026-08-01 실측).
따라서 이번 데모의 스타일 잠금은 **베이스 모델 + 앵커 프롬프트 규약**으로 한다:

- **모델**: FLUX 2 (Flex) = `model_bfl-flux-2-flex` (Scenario custom 엔드포인트 경유, `--base-model` 금지)
- **앵커 프롬프트(모든 생성에 포함)**:
  `diesel-punk, early 20th century, brass and bakelite, aged patina, rivets, amber phosphor glow, muted sepia palette, dim tungsten light, painterly, game asset, no text`
- **금지 요소**: 디지털/LED 표시, 현대적 UI 아이콘, 선명한 원색, 사람(배경), 실존 브랜드·문자
- 근거: 동일 앵커로 생성한 13장이 스타일 일관성을 입증(아래 §4). LoRA 학습은 정식판에서
  플랜 업그레이드 후 이 컨셉 10선으로 재개한다(§5 모델 셸 참조).

## 2. 스타일 규칙 요약

| 축 | 규칙 |
|---|---|
| 팔레트 | 세피아·앰버 단색조 기조. 하이라이트 = 앰버 인광(#f0a030 계열), 섀도 = 갈색·흑갈 |
| 재질 | 황동(브라스) 프레임·리벳, 바켈라이트 노브, 낡은 상아색 다이얼 페이스, 녹·마모 패티나 |
| 조명 | 텅스텐 저조도 + 진공관/네온 앰버 글로우. 화면 발광은 인광(초록/앰버)만 |
| 형태 | 20세기 초 기계 — 태엽·다이얼·타자기·브라운관. 곡면 유리, 두꺼운 금속 테 |
| 시대 규율 | 디지털 표시(7-seg LED 등) 금지. 계기는 바늘·눈금만. 문자는 게임 런타임 폰트(Neo둥근모)가 담당 — 아트에 텍스트 굽지 않기 |

## 3. 에셋별 생성·후처리 규약

| 에셋 (manifest id) | 소스 | 후처리 |
|---|---|---|
| `art:ui/main/desk_bg` | `concept_desk_00.png` (16:9, 1344×752) | 1152×648 리사이즈. CRT 모니터가 중앙(클릭 영역 정합) |
| `art:ui/window/frame` | `concept_window_00.png` (텍스트 無, 균일 테두리) | 9-slice 마진 산출 후 등록. 타이틀바 텍스트는 런타임 폰트 |
| `art:ui/gauge/opinion_needle` | `concept_gauge_00.png` 또는 `_c` | 판/바늘 분리 필요 시 바늘 별도 생성 or 코드 회전으로 대체. 숫자 제거(인페인트/크롭) — canon "숫자 없는 부정확 계기" |

- 추가 에셋이 필요하면 **§1 앵커 프롬프트 + 위 재질·조명 규칙**으로 생성한다. 단가 실측 9크레딧/장.
- 컨셉이 곧 소스인 이유: 필요 에셋 3종뿐인 데모 스코프에서 양산 모델은 과투자(사람 결정 2026-08-01).

## 4. 대표 컨셉 (스타일 정본 이미지)

학습 10선(= 스타일 기준): desk `00/b/c` · window `00/b` · gauge `00/2/c/d/e`
제외 3장과 사유: `desk_d`(LED 디지털 — 시대 규율 위반), `window_c/d`(대형 가짜 텍스트 — 문자 오염)
→ 이 제외 사유가 곧 §2 의 금지 요소 규칙이다.

## 5. 파라미터·계정 기록

- 생성: `scenario_client.py generate --model-id model_bfl-flux-2-flex --prompt "..." [--aspect-ratio 16:9]`
  (numSamples 미지원 — 다장은 개별 호출), 이미지당 9크레딧(실측: 13장=117).
- **모델 셸**: `model_5S7Qfb2bK215uGPHzNvQThqK` (name=taeyeop-dieselpunk, flux.2-dev-lora, status=new)
  — 학습 이미지 10장 업로드까지 완료된 상태로 Scenario 계정에 존재. 플랜 업그레이드 시
  이 모델에서 학습 재개 가능. API 키·시크릿은 `.env` 전용(이 문서·매니페스트에 기록 금지).
