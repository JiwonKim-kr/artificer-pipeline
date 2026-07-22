---
description: art concept — 범용 모델로 컨셉 후보 복수 생성 (design-first 진입점)
argument-hint: <주제>
---

너는 게임 개발 파이프라인의 오케스트레이터다. `art concept` 을 실행한다.
계약: `pipeline/commands/art.md` 의 `art concept` 절. 규칙: `CLAUDE.md`, 컨벤션: `docs/conventions.md`.

**주제**: `$ARGUMENTS`

**목적**: 스타일 확정 전, 범용 프런티어 모델(FLUX.2/GPT Image, Scenario 플랫폼 경유)로 컨셉 후보를 폭넓게 생성한다. 이 산출물은 **탐색용**이며 다음 `art lock` 의 학습 입력이 된다.

$ARGUMENTS 가 비어 있으면 무엇의 컨셉을 만들지 되묻고 멈춘다.

## 1. 생성 — 컨셉 후보

1. 설정/세계관이 관련되면 먼저 `python3 pipeline/scripts/lore_index.py --canon lore/canon query "<핵심어>"` 로 canon 을 확인하고 프롬프트에 반영한다(있으면).
2. 주제를 반영한 프롬프트를 구성해 후보를 생성한다:
   ```
   python3 pipeline/scripts/scenario_client.py generate \
     --base-model --model-id <FLUX.2/GPT Image 등 범용 모델 ID> \
     --prompt "<주제 + 방향 묘사>" --num-samples <N> \
     --out-dir assets/art/concepts
   ```
   - 키가 없으면 스크립트가 발급 안내 + 종료 코드 3 으로 멈춘다. 이때는 `--dry-run` 으로 요청 구성만 확인하고, 사용자에게 키 발급을 안내한다.

## 2. 자동 검증 (self-check)

- 저장된 파일을 `python3 pipeline/scripts/art_post.py probe --input <경로>` 로 크기/투명 규격을 확인한다.

## 3. 사람 검수

- 후보 이미지와 각 프롬프트/시드를 제시한다. **여기서의 선택(5~15장)은 `art lock` 의 학습 입력**임을 알린다.

## 4. 반영

- 컨셉 이미지는 `assets/art/concepts/` 에만 저장한다(탐색 산출물). **매니페스트 placeholder 실제화나 씬 변경은 하지 않는다** — 그것은 `art gen`/`art reskin` 의 몫이다.

주의: 이 단계는 스타일을 잠그지 않는다. 스타일 고정은 승인 지점인 `art lock` 에서만 한다.
