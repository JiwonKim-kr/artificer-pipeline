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
- 플레이스홀더 이미지는 **`pipeline/scripts/placeholder_gen.py` 로만** 만든다. 즉석 스크립트로 단색 PNG 를 찍어내지 않는다.
- `src/core/` 는 승인된 spec 범위 안에서만 수정한다. GDScript 는 **정적 타이핑**(`var x: int`)을 쓴다.

## 1. 전제 확인

1. 대상 spec 파일을 읽고 `status: approved` 인지 확인한다. 아니면 여기서 멈추고 `play spec` 승인을 안내한다.
2. spec 의 대상 파일·수용 기준·필요 에셋 목록을 추출한다. 설정 참조가 있으면 `lore query` 로 canon 을 확인한다.

## 2. 생성 — 구현

1. spec 의 대상 파일에 따라 GDScript·씬을 구현한다:
   - 씬 파일명은 루트 노드의 snake_case, 노드 이름은 PascalCase (conventions).
   - 핵심 로직은 `src/core/`, 보조/툴은 `src/ui/`·`src/tools/`.
   - 정적 타이핑, 수용 기준을 만족하는 최소 구현.
2. 필요한 에셋 자리에는 **`PLACEHOLDER_` 접두사** 파일을 규칙 경로에 배치한다(`assets/art/...`, `assets/audio/...`). 이미지는 아래 3절의 생성기를 쓴다.
3. 첫 실행 가능한 씬을 만들면 `project.godot` 의 `application/run/main_scene` 설정을 함께 갱신한다(스모크 테스트의 로드 검증이 활성화된다).

## 3. 플레이스홀더 이미지 생성 (유일 창구: `placeholder_gen.py`)

플레이스홀더는 **임시방편이 아니라 정식 중간 산출물**이다. 아트가 없어도 화면만 보고
게임이 뭘 하는지 판정할 수 있어야 하므로, 단색 네모가 아니라 **글리프(문자)와 색으로
읽히는 그림**을 만든다. 예산이 생기면 `art reskin` 이 같은 경로·같은 구조의 실제
에셋으로 교체하므로(재작업 0), 이 단계에서 규약을 정확히 지킨다.

```
python3 pipeline/scripts/placeholder_gen.py \
  --glyph '<문자 1개>' --fg '<#RRGGBB>' [--bg '<#RRGGBB>'|transparent] [--border '<#RRGGBB>'] \
  [--size 16 | --width W --height H] \
  --output "assets/art/sprites/<카테고리>/PLACEHOLDER_<이름>.png" --preview
```
- 셸에서 `#RRGGBB` 는 **따옴표**로 감싼다(`#` 는 주석). `--fg ffd23f` 처럼 `#` 생략도 허용.
- `--preview` 로 나오는 텍스트 픽셀 맵을 **반드시 눈으로 확인**한다. 글리프가 뭉개졌거나
  경고(잘림/완전 투명/미지원 문자 폴백)가 뜨면 크기·글리프를 바꿔 다시 만든다.
- 지원 문자는 `--list-glyphs` 로 확인한다(영문 대소문자·숫자·주요 기호). 미지원 문자는
  `?` 로 폴백되므로 그대로 두지 않는다.
- 크기·프레임 규격은 spec 에서 온다. 확대·스프라이트시트 패킹이 필요하면
  `pipeline/scripts/art_post.py` (resize/pack/probe)를 쓴다 — 생성기는 만들기만 한다.
- 이 스크립트는 **매니페스트를 쓰지 않는다.** 등록은 아래 4절에서 `manifest.py` 로 한다.

**글리프·색 선택 규칙 (중요)**:
- 어떤 에셋에 어떤 글리프·색을 줄지는 **spec 의 에셋 설명과 `lore query` 결과(데이터)로
  판단한다.** 커맨드나 코드에 장르별 대응표를 만들지 않는다.
- **서로 다른 엔티티는 화면에서 즉시 구분돼야 한다.** 이번 build 에서 만드는 모든
  플레이스홀더의 (글리프, 색) 조합이 **서로 겹치지 않도록** 표로 정리한 뒤 생성한다.
  글리프가 같으면 색이 확연히 달라야 하고, 색이 비슷하면 글리프가 달라야 한다.
- 판단 근거: 에셋의 **역할**(조작 주체 / 적대 개체 / 획득물 / 지형·배경 / UI)과 spec 의
  이름·설명. 이름의 첫 글자를 쓰는 것도 유효한 선택이며, 정본(lore)에 상징이 정의돼
  있으면 그것을 우선한다.
- **배경 규칙**: 배경 위에 얹히는 것(캐릭터·아이템·UI 아이콘)은 `--bg transparent`,
  바닥·벽 같은 타일은 불투명 `--bg` + `--border` 로 격자 경계가 보이게 한다.
- 글리프가 무의미한 대상(순수 도형 표시)은 `--glyph` 를 생략해 단색+테두리로 만든다.

생성 후 요약표(에셋 / 글리프 / 색 / 크기 / 투명여부 / 매니페스트 ID)를 6절 보고에 포함한다.

## 4. 매니페스트 등록 (유일 창구)

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

## 5. 자동 검증

```
python3 pipeline/scripts/play_test.py
```
임포트·스모크·매니페스트 정합성이 모두 PASS 여야 한다. 실패하면 원인을 고치고 재실행한다.

## 6. 사람 검수 / 반영

- 변경 요약(생성 파일, 플레이스홀더 요약표, 등록한 매니페스트 entry, `play test` 결과)을 제시한다.
- 커밋은 사용자 승인 후에만 한다. **`src/core/` 변경 커밋 본문에는 승인된 spec 문서 경로를 명시**한다(예: 본문에 `spec: docs/specs/player_movement.md`). 커밋 제목은 `[play build] <요약>` 형식(conventions).

주의: 장르/스타일 의존 값은 spec/lore/manifest **데이터**에서 오고, 코드에는 하드코딩하지 않는다.
