---
description: art lock — 선택 컨셉으로 커스텀 스타일 모델 학습, 스타일 고정 (사람 승인 지점)
argument-hint: (인자 없음) [스타일 이름]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `art lock` 을 실행한다.
계약: `pipeline/commands/art.md` 의 `art lock` 절. 규칙: `CLAUDE.md`.

**목적**: 선택된 컨셉으로 **Scenario 커스텀 스타일 모델**을 학습시켜 스타일을 고정한다. 이후 모든 `art gen` 의 기준이 된다.
**절대 규칙**: 이것은 **생략 불가한 사람 승인 지점(아트 스타일 승인)**이다. 스타일 잠금(모델 ID 확정 + `manifest.style_guide` 기록 + 스타일 가이드 문서)은 **사람 승인 후에만** 한다. Claude 가 임의로 잠그지 않는다.

## 1. 사람 선택 (승인 대상)

- `assets/art/concepts/` 의 후보를 제시하고, 사람이 **5~15장**을 고르게 한다. 선정은 사람의 결정이다 — Claude 는 후보와 근거만 제시한다.
- 스타일 이름을 확인한다(예: "pixel-dungeon"). $ARGUMENTS 에 있으면 사용한다.

## 2. 생성 — 커스텀 모델 학습

```
python3 pipeline/scripts/scenario_client.py train \
  --name "<스타일 이름>" --type <flux.2-dev-lora | qwen-image-lora | zimage-lora 등> \
  --image <선택 이미지 1> --image <선택 이미지 2> ... [--seed N]
```
- 학습 시작 후 상태 확인: `python3 pipeline/scripts/scenario_client.py train --status --model-id <반환된 모델 ID>` → `trained` 대기.
- 키가 없으면 스크립트가 발급 안내 + 종료 코드 3 으로 멈춘다. `--dry-run` 으로 create→upload→start 요청 구성만 확인할 수 있다.

## 3. 자동 검증 (self-check)

- 학습 완료 후 잠긴 모델로 소량 테스트 생성(`generate --model-id <ID>`)을 돌려 스타일 반영을 확인한다.

## 4. 사람 검수 / 반영

- **스타일 가이드 문서 초안**(예: `docs/style_guide.md`: 스타일 규칙 요약 + 모델 ID + 대표 컨셉 경로 + 파라미터)과 테스트 샘플을 제시하고 **명시적 승인**을 요청한다.
- **승인 후에만**:
  1. 스타일 가이드 문서를 기록한다.
  2. `manifest.style_guide` 를 그 문서 경로로 설정한다(매니페스트 단일 창구 `manifest.py` 경유. 필드 갱신 지원이 없으면 추가 후 사용).
  3. 모델 ID 를 스타일 가이드 문서에 기록한다. **API 키·시크릿은 문서/매니페스트에 남기지 않는다**(모델 ID 는 비밀 아님, 키는 `.env` 전용).
- 승인 전에는 스타일을 잠그지 않으며 `art gen` 양산으로 진행하지 않는다.

주의: 픽셀 그리드 정합이 반복적으로 미흡하면 스타일 가이드에 그 사실을 남기고, Retro Diffusion 계열 병행 재검토를 제안한다(계약 §픽셀아트 정합 정책). 이 판단도 문서/데이터로만 표현한다.
