---
description: art gen — 잠긴 커스텀 모델로 에셋 생성 + 후처리 + 규칙 경로 저장
argument-hint: <에셋 명세 또는 매니페스트 ID>
---

너는 게임 개발 파이프라인의 오케스트레이터다. `art gen` 을 실행한다.
계약: `pipeline/commands/art.md` 의 `art gen` 절. 규칙: `CLAUDE.md`, 컨벤션: `docs/conventions.md`.

**에셋 명세**: `$ARGUMENTS` (예: `art:enemy/slime_idle` 또는 자연어 명세)

**전제**: 스타일이 잠겨 있어야 한다(`manifest.style_guide` 설정 + 커스텀 모델 ID). 잠기지 않았으면 **중단하고 `art lock` 을 먼저 안내한다.**

## 1. 전제 확인

1. `python3 pipeline/scripts/manifest.py validate` 로 매니페스트를 확인하고, `style_guide` 가 설정됐는지(스타일 잠금 여부)와 대상 placeholder entry 를 파악한다.
2. 스타일 가이드 문서에서 커스텀 모델 ID 를 읽는다. 대상 에셋의 요구 명세(크기/프레임/투명)를 확정한다. 설정 참조가 필요하면 `lore query` 로 확인해 프롬프트에 반영하고 경로를 `lore_refs` 후보로 남긴다.

## 2. 생성 — 커스텀 모델

```
python3 pipeline/scripts/scenario_client.py generate \
  --model-id <잠긴 커스텀 모델 ID> \
  --prompt "<에셋 명세 + 스타일 가이드 반영>" [--num-samples N] \
  --out-dir <임시 또는 규칙 경로>
```
- 키가 없으면 발급 안내 + 종료 코드 3. `--dry-run` 으로 요청 구성만 확인 가능.

## 3. 후처리 (플랫폼 우선 → 로컬 보완)

- **플랫폼 내장 후처리(배경 제거·투명 PNG)를 우선** 활용한다. 필요 시 `scenario_client.py remove-bg`.
- 부족분만 로컬 ffmpeg 로 보완한다:
  - 픽셀아트 리사이즈(nearest): `python3 pipeline/scripts/art_post.py resize --input <..> --output <..> (--scale N | --width W --height H)`
  - 스프라이트시트 패킹(동일 크기 프레임): `python3 pipeline/scripts/art_post.py pack --output <시트> <frame0> <frame1> ... --json` (프레임 메타를 매니페스트 `params` 에 기록)
- 최종 파일은 규칙 경로에 둔다: 스프라이트 `assets/art/sprites/<카테고리>/<이름>...png`, UI `assets/art/ui/<화면>/<요소>.png`. **투명 PNG** 유지.

## 4. 자동 검증 (self-check)

- `python3 pipeline/scripts/art_post.py probe --input <경로>` 로 크기/투명(alpha)/프레임 규격을 확인한다.
- 픽셀 그리드 정합이 미흡하면 계약 §픽셀아트 정합 정책에 따라 대응(nearest 배수 강제 → 그래도 부족하면 Retro Diffusion 병행 재검토 제안).

## 5. 사람 검수 / 반영

- 생성 결과·규격을 제시한다. **씬 연결과 매니페스트 상태 갱신은 `art reskin` 에서** 한다(이 명령은 규칙 경로에 에셋을 만들어 두는 데까지).
- 매니페스트 쓰기가 필요하면 `manifest.py` 를 통해서만 한다. `assets/art/` 밖은 쓰지 않는다.

주의: 장르/스타일 값(프롬프트 톤 등)은 스타일 가이드·lore·명세 **데이터**에서 오고 코드/스크립트에 하드코딩하지 않는다.
