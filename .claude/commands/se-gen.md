---
description: se gen — 이벤트 기반 효과음 생성 + OGG 모노 -16 LUFS 정규화
argument-hint: <이벤트 목록 또는 매니페스트 ID> [--backend elevenlabs|jsfxr]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `se gen` 을 실행한다.
계약: `pipeline/commands/se.md` 의 `se gen` 절. 규칙: `CLAUDE.md`, 컨벤션: `docs/conventions.md`.

**대상**: `$ARGUMENTS` (예: `se:player_step`, 또는 자연어 이벤트 명세. 비우면 매니페스트의 `placeholder` se entry 전체를 후보로 제시)

## 1. 대상·백엔드 확정

1. `python3 pipeline/scripts/manifest.py list --track se --json` 으로 대상 entry 와 spec 을 파악한다.
2. **이벤트별 백엔드 선택** (HANDOFF §6-2): entry `params.backend` 가 있으면 그것을, 없으면 성격에 따라 제안한다 — 자연음/질감은 `elevenlabs`(기본), 레트로/칩튠 톤은 `jsfxr`. 선택 근거를 제시하고 확인받는다.
3. 설정 참조가 필요하면 `lore query` 로 canon 을 확인해 명세에 반영하고 경로를 `lore_refs` 후보로 남긴다.

## 2. 생성 (임시 경로에)

- **elevenlabs** (프롬프트 기반 기본):
  ```
  python3 pipeline/scripts/elevenlabs_client.py generate \
    --text "<이벤트 명세(+lore 반영)>" [--duration <초>] [--prompt-influence 0~1] \
    --out <임시 디렉토리>/<이벤트>.mp3
  ```
  키(`ELEVENLABS_API_KEY`)가 없으면 발급 안내 + 종료 코드 3. `--dry-run` 으로 요청 구성만 확인 가능.
- **jsfxr** (절차적·재현 가능):
  ```
  python3 pipeline/scripts/se_jsfxr.py render \
    --spec <spec.json> --out <임시 디렉토리>/<이벤트>.wav \
    --save-params <재현 spec 저장 경로>
  ```
  spec 예: `{"seed": 7, "preset": "pickupCoin", "params": {"p_env_decay": 0.5}}`. **seed 고정 → 동일 WAV**. 환경 미비 시 `se_jsfxr.py check` 안내 + 종료 코드 3.

## 3. 정규화 (규칙 경로로)

```
python3 pipeline/scripts/se_post.py normalize \
  --input <임시 산출물> --output assets/audio/se/<이벤트>.ogg
```
- 기본값이 SE 규격이다: **OGG Vorbis · 모노 · -16 LUFS** (loudnorm 2-pass). 파일명은 `PLACEHOLDER_` 접두사를 뗀 실제 경로(conventions).

## 4. 자동 검증 (self-check)

```
python3 pipeline/scripts/se_post.py probe --input assets/audio/se/<이벤트>.ogg \
  --expect-codec vorbis --expect-channels 1 --expect-i -16 --tolerance 1.0
```
- 불통과면 규칙 경로 산출물을 반영하지 않고 원인을 짚는다.

## 5. 사람 검수 / 반영

- 결과(파일 경로·실측 LUFS·재현 파라미터/프롬프트)를 제시한다. jsfxr 재현 spec 은 entry `params.jsfxr` 에, ElevenLabs 프롬프트는 `params.prompt` 에 기록하도록 `manifest.py` 경유로 제안한다.
- **씬 연결과 상태 갱신(`placeholder → generated`)은 `se attach` 에서** 한다(이 명령은 정규화된 에셋을 규칙 경로에 만들어 두는 데까지). `assets/audio/` 밖은 쓰지 않는다.

주의: 장르 상수(픽셀아트 등)를 프롬프트/프리셋 선택 로직에 하드코딩하지 않는다 — 성격 판단의 근거는 entry spec·lore **데이터**다.
