# spec: dungeon_and_turns (Spec A)

- **status**: approved
- **생성 명령**: `play spec 던전 생성 + 턴제 이동`
- **작성일**: 2026-07-25
- **승인**: 2026-07-25 사용자 승인 (방-복도형·턴제 전환·글리프 타일 원안대로)
- **참조 lore**: `lore/canon/world.md`(층·층계·지하 미궁·서바이벌·느린 등반), `glossary.md`(층/시련/돌파/지하 미궁)
- **데모 스코프**: 1층계(지하 미궁) 수직 슬라이스의 1단계. 난이도 노멀 고정.

> `play spec` 산출물 초안. **아직 사람 승인 전(draft)**. 승인 시 status를 `approved`로 갱신한 뒤에만 `play build`로 진행한다.

## 목적 (goal)

지하 미궁 한 개 층을 **절차적으로 생성**하고, 승탑자가 그 위를 **턴제(turn-based)**로 한 칸씩 이동·탐색하는 기반을 만든다. 로그라이크의 근본 골격(맵 + 턴 + 시야 없는 전면 렌더)을 세우는 단계이며, 전투·성장은 Spec B/C에서 얹는다.

## 핵심 결정: 턴제 모델 (기존 이동과의 차이)

- 현재 `src/core/player.gd`는 **실시간 입력 + 보간 이동**이다(로그라이크에 부적합). 이 spec에서 **턴제로 전환**한다.
- 한 번의 플레이어 행동(이동 1칸 또는 제자리 대기)이 **1턴**을 소비한다. 이 spec에는 적이 없으므로 턴은 "플레이어 행동 카운터"로만 존재하지만, Spec B의 적 행동이 끼어들 **턴 경계(turn boundary)**를 지금 구조로 만들어 둔다.
- 이동은 즉시(discrete) 반영을 기본으로 하되, 시각적 부드러움을 위한 짧은 보간은 허용(턴 로직과 분리). 턴 판정은 보간 완료를 기다리지 않는다.

## 던전 생성 (procedural)

- **방-복도형**: 여러 개의 직사각형 방을 배치하고 복도로 연결. 모든 바닥이 상호 도달 가능해야 한다(고립 방 금지).
- 생성은 **시드 기반 결정적**: 같은 시드 → 같은 던전(테스트·재현성). 시드는 데이터로 주입(하드코딩 금지).
- 타일 종류(이 spec): **바닥(walkable)**, **벽(blocked)**, **계단(내려온 곳=시작, 올라가는 곳=출구)**. 출구 계단은 배치만 하고 "돌파" 동작은 Spec C.
- 맵 크기·방 개수·최소/최대 방 크기는 **노멀 난이도 파라미터**로 데이터화(예: 리소스/딕셔너리). 장르·밸런스 상수를 코드에 박지 않는다.

## 수용 기준 (acceptance criteria)

관찰 가능한 조건만. `play test`(스모크+스크린샷) 및 후속 자동 테스트의 근거.

1. 던전 생성 결과의 모든 바닥 타일은 시작 지점에서 도달 가능하다(BFS/flood-fill로 검증 가능).
2. 같은 시드로 두 번 생성하면 타일 배치가 완전히 동일하다(결정성).
3. 방향 입력 1회에 승탑자의 그리드 좌표가 해당 방향으로 정확히 1칸 이동하고, **턴 카운터가 정확히 1 증가**한다.
4. 벽 타일 또는 맵 경계로 향하는 입력은 좌표를 바꾸지 않으며 **턴을 소비하지 않는다**.
5. 제자리 대기 입력은 좌표를 바꾸지 않고 턴 카운터만 1 증가시킨다.
6. 승탑자의 월드 좌표는 정지 시 항상 `그리드 좌표 × 타일 크기`에 정렬된다.
7. 메인 씬이 `godot`로 로드·렌더되어 던전과 승탑자가 화면에 보인다(스크린샷 스테이지 통과). 카메라가 승탑자를 화면 안에 둔다.

## 대상 파일 (target files)

정적 타이핑 준수. `src/core/`는 승인된 spec 범위 내에서만 수정.

| 경로 | 역할 |
|---|---|
| `src/core/dungeon_generator.gd` | 시드 기반 방-복도 던전 생성. 타일 격자(enum: floor/wall/stairs) + 시작/출구 좌표 반환. 도달성 보장 |
| `src/core/turn_manager.gd` | 턴 경계 관리. 플레이어 행동 → 턴 소비 → (후속 적 페이즈 훅). 턴 카운터 |
| `src/core/player.gd` | **턴제로 개편**. 입력 → turn_manager에 행동 제출 → grid 판정. 실시간 폴링 이동 제거 |
| `src/core/grid.gd` | 기존 유지·확장. 던전 타일 데이터를 walkable 판정에 사용 |
| `src/core/dungeon.gd` | 던전 런타임: 생성 결과를 타일맵/스프라이트로 렌더, 승탑자·계단 배치, 카메라 |
| `scenes/dungeon.tscn` | 루트 `Dungeon` + TileMapLayer(또는 타일 스프라이트 컨테이너) + `Player` + `Camera2D`. 새 메인 씬 |
| `scenes/player.tscn` | 기존 유지(스프라이트 텍스처는 placeholder 교체) |

- `project.godot`의 `main_scene`을 `scenes/dungeon.tscn`으로 변경.
- 기존 `scenes/main.tscn`(9×9 테스트 맵)은 제거하거나 대체.

## 필요 에셋 (assets) — placeholder_gen 글리프

`play build`에서 `placeholder_gen.py`로 생성 후 `manifest.py add` 등록. ID는 `<track>:<카테고리>/<이름>`.

| id | 글리프/색 | requested_by(후보) | 파일 |
|---|---|---|---|
| `art:player/climber_idle` | `@` / 밝은 노랑, 투명 | `scene_node:scenes/player.tscn::Player/Sprite2D` | `assets/art/sprites/player/PLACEHOLDER_climber_idle.png` |
| `art:tiles/dungeon_floor` | `.` / 어두운 회색, 불투명 | `scene_node:scenes/dungeon.tscn::TileMapLayer` | `assets/art/sprites/tiles/PLACEHOLDER_dungeon_floor.png` |
| `art:tiles/dungeon_wall` | `#` / 회청색, 불투명 | `scene_node:scenes/dungeon.tscn::TileMapLayer` | `assets/art/sprites/tiles/PLACEHOLDER_dungeon_wall.png` |
| `art:tiles/stairs_up` | `<` / 밝은 청록, 불투명 | `scene_node:scenes/dungeon.tscn::TileMapLayer` | `assets/art/sprites/tiles/PLACEHOLDER_stairs_up.png` |

(효과음은 Spec B/C에서 이벤트가 생길 때 `se gen`으로. 이 spec은 이동 발소리 정도만 선택적으로 후속 연결.)

## 범위 밖 (out of scope)

- 몬스터·전투·HP → Spec B
- 상태창 UI·경험치·성장·사망·계단 돌파 동작 → Spec C
- 시야/안개(FoW) → 데모 후 검토. 이 spec은 전면 렌더.
- 난이도 이지/하드/카오스 → 노멀만.

## 승인 후 진행

1. 사람이 검토 후 status를 `approved`로 갱신.
2. `play build docs/specs/dungeon_and_turns.md` — 위 대상 파일 구현 + placeholder 4종 생성·등록 + main_scene 변경.
3. `play test --screenshot` — 임포트 + 스모크(dungeon.tscn 로드) + 시각 렌더 + 매니페스트 정합성. 도달성·결정성·턴 카운터 수용 기준 자동 테스트.
