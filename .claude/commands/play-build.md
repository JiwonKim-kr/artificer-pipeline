---
description: play build — 승인된 spec을 GDScript+씬으로 구현, placeholder를 매니페스트에 등록
argument-hint: <명세 경로 또는 기능명>
---

너는 게임 개발 파이프라인의 오케스트레이터다. `play build` 를 실행한다.
계약: `pipeline/commands/play.md` 의 `play build` 절. 규칙: `CLAUDE.md`, 컨벤션: `docs/conventions.md`.

**대상 spec**: `$ARGUMENTS` (예: `docs/specs/player_movement.md` 또는 기능명)

**절대 규칙**:
- 대상 spec 의 `status` 가 **`approved`** 여야 한다. `draft` 이거나 승인 근거가 없으면 **중단하고 승인을 요청한다.** (사람 승인 지점 생략 불가)
- 매니페스트 쓰기는 **`pipeline/scripts/manifest.py` 를 통해서만** 한다. 파일을 직접 편집하지 않는다.
- `src/core/` 는 승인된 spec 범위 안에서만 수정한다. GDScript 는 **정적 타이핑**(`var x: int`)을 쓴다.

## 1. 전제 확인

1. 대상 spec 파일을 읽고 `status: approved` 인지 확인한다. 아니면 여기서 멈추고 `play spec` 승인을 안내한다.
2. spec 의 대상 파일·수용 기준·필요 에셋 목록을 추출한다. 설정 참조가 있으면 `lore query` 로 canon 을 확인한다.

## 2. 생성 — 구현

1. spec 의 대상 파일에 따라 GDScript·씬을 구현한다:
   - 씬 파일명은 루트 노드의 snake_case, 노드 이름은 PascalCase (conventions).
   - 핵심 로직은 `src/core/`, 보조/툴은 `src/ui/`·`src/tools/`.
   - 정적 타이핑, 수용 기준을 만족하는 최소 구현.
2. 필요한 에셋 자리에는 **`PLACEHOLDER_` 접두사** 파일을 규칙 경로에 배치한다(`assets/art/...`, `assets/audio/...`).
3. 첫 실행 가능한 씬을 만들면 `project.godot` 의 `application/run/main_scene` 설정을 함께 갱신한다(스모크 테스트의 로드 검증이 활성화된다).

## 3. 매니페스트 등록 (유일 창구)

각 placeholder 를 아래처럼 등록한다. `requested_by` 에는 **씬 노드 경로**(또는 코드 이벤트 지점)를 남긴다:

```
python3 pipeline/scripts/manifest.py add \
  --id <track>:<카테고리>/<이름> \
  --track <art|se|bgm|text> \
  --status placeholder \
  --spec "<에셋 요구 명세(자연어)>" \
  --requested-by "scene_node:scenes/<씬>.tscn::<노드경로>" \
  --file "<PLACEHOLDER_ 파일 경로>"
```
- 참조한 canon 이 있으면 `--lore-ref <경로>` 를 추가한다.
- 검증 실패 시 매니페스트는 **쓰이지 않는다**. 출력된 오류(패턴/필수/enum/track 불일치/중복 ID)를 해소한 뒤 재시도한다.
- 등록 결과는 `python3 pipeline/scripts/manifest.py list` 로 확인한다.

## 4. 자동 검증

```
python3 pipeline/scripts/play_test.py
```
임포트·스모크·매니페스트 정합성이 모두 PASS 여야 한다. 실패하면 원인을 고치고 재실행한다.

## 5. 사람 검수 / 반영

- 변경 요약(생성 파일, 등록한 매니페스트 entry, `play test` 결과)을 제시한다.
- 커밋은 사용자 승인 후에만 한다. **`src/core/` 변경 커밋 본문에는 승인된 spec 문서 경로를 명시**한다(예: 본문에 `spec: docs/specs/player_movement.md`). 커밋 제목은 `[play build] <요약>` 형식(conventions).

주의: 장르/스타일 의존 값은 spec/lore/manifest **데이터**에서 오고, 코드에는 하드코딩하지 않는다.
