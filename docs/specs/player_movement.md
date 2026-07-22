# spec: player_movement

- **status**: approved
- **생성 명령**: `play spec 플레이어 이동`
- **작성일**: 2026-07-14
- **승인**: 2026-07-14 사용자 승인 (그리드 이동 방식 포함 원안대로)
- **참조 lore**: 없음 (canon 미초기화 — 이동 규칙은 세계관 의존 없음)

> 이 문서는 `play spec` 산출물 초안이다. **아직 사람 승인 전(draft)** 이므로
> `play build` 를 실행하지 않는다. 승인 시 status 를 `approved` 로 갱신한 뒤에만 build 로 진행한다.

## 목적 (goal)

플레이어 캐릭터가 격자(그리드) 위에서 4방향(상·하·좌·우)으로 **한 칸씩** 이동하는
기본 이동 컨트롤러를 제공한다. 이동 불가 지점(경계·차단 타일)으로는 이동하지 않는다.
이 기능은 play 트랙의 spec→build→test 왕복과 매니페스트 흐름을 검증하는 최소 기능이다.

## 이동 방식 결정: 그리드(타일) 이동 — 근거

- **검증 대상 게임이 로그라이크**(HANDOFF §2)이며, 로그라이크의 관례적 이동은 타일 단위 이산 이동이다. 자유(연속) 이동보다 장르 적합.
- **결정성·테스트 용이성**: 이동 결과가 "타일 좌표 +1" 처럼 이산적이라 수용 기준을 관찰 가능한 정수 상태로 표현할 수 있다(스모크/후속 자동 테스트에 유리).
- **픽셀아트 정합**(HANDOFF §2): 타일 그리드가 픽셀 그리드와 자연히 정렬된다.
- 단, **타일 크기·맵 데이터는 하드코딩하지 않고** 씬/Export 변수 등 데이터로 둔다(파이프라인 범용성 유지). 로그라이크라는 사실은 이 spec 문서의 판단 근거로만 쓰고 코드에 장르 상수를 박지 않는다.

## 수용 기준 (acceptance criteria)

관찰 가능한 조건만 기술한다. 이후 `play test` 스모크 및 후속 자동 테스트의 근거가 된다.

1. 방향 입력(상/하/좌/우) 1회에 플레이어의 그리드 좌표가 해당 방향으로 정확히 1칸 변한다.
2. 이동이 진행 중일 때 들어온 새 입력은 현재 이동을 반 칸에서 끊지 않는다(이동 완료 후 처리 또는 무시).
3. 맵 경계 바깥 또는 차단 타일로 향하는 입력은 **위치를 바꾸지 않는다**(좌표 불변).
4. 월드 좌표는 항상 `그리드 좌표 × 타일 크기` 에 정렬된다(반 칸 정지 없음).
5. 메인 씬이 `godot --headless` 로 로드·인스턴스화된다(스모크 테스트 2단계 통과).

## 대상 파일 (target files)

승인된 spec 범위 안에서만 생성/수정한다. 정적 타이핑 준수.

| 경로 | 역할 |
|---|---|
| `src/core/player.gd` | `Player` 컨트롤러. 입력 → 그리드 좌표 갱신 → 월드 좌표 보간. 이동 가능 판정 호출 |
| `src/core/grid.gd` | 그리드 좌표 ↔ 월드 좌표 변환, 경계/차단 판정(맵 데이터는 주입받음) |
| `scenes/player.tscn` | 루트 `Player`(스크립트 `src/core/player.gd`) + 자식 `Sprite2D` |
| `scenes/main.tscn` | 루트 `Main` + `TileMapLayer`(맵) + `Player` 인스턴스. `project.godot` 의 `application/run/main_scene` 로 설정 |

## 필요 에셋 (assets) — 매니페스트 placeholder 후보

build 단계에서 `manifest.py add` 로 등록한다. ID 는 `<track>:<카테고리>/<이름>` 형식.

| id | track | 요구 명세 | requested_by (후보) | placeholder 파일 |
|---|---|---|---|---|
| `art:player/player_idle` | art | 플레이어 대기 스프라이트. 정면 1프레임, 타일 크기에 맞는 정사각 | `scene_node:scenes/player.tscn::Player/Sprite2D` | `assets/art/sprites/player/PLACEHOLDER_player_idle.png` |
| `art:tiles/floor` | art | 바닥 타일 1종. 그리드 배경 | `scene_node:scenes/main.tscn::TileMapLayer` | `assets/art/sprites/tiles/PLACEHOLDER_floor.png` |
| `se:player_step` | se | 한 칸 이동 완료 시 발소리 효과음 | `code_event:src/core/player.gd::on_step_complete` | `assets/audio/se/PLACEHOLDER_player_step.ogg` |

## 승인 후 진행 (승인 전에는 실행하지 않음)

1. 사람이 이 spec 을 검토하고 status 를 `approved` 로 갱신.
2. `play build docs/specs/player_movement.md` — 위 대상 파일 구현 + placeholder 배치 + `manifest.py add` 등록 + `main_scene` 설정.
3. `play test` — 임포트 + 스모크(메인 씬 로드) + 매니페스트 정합성 통과 확인.
