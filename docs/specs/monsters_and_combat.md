# spec: monsters_and_combat (Spec B)

- **status**: approved
- **생성 명령**: `play spec 몬스터 + 턴제 전투`
- **작성일**: 2026-07-25
- **승인**: 2026-07-25 사용자 승인 (범프 전투 + 스탯 기반 [최소~최대] 랜덤 데미지, 시드 RNG)
- **참조 lore**: `lore/canon/world.md`(시스템·서바이벌·지하 미궁), `glossary.md`(미궁 쥐/슬라임/시련/시스템)
- **선행 spec**: `dungeon_and_turns.md`(Spec A, approved·구현됨) — turn_manager의 적 페이즈 훅을 채운다.
- **데모 스코프**: 1층계(지하 미궁) 수직 슬라이스 2단계. 난이도 노멀 고정. 평면 top-down(iso 전환은 후속 Spec).

> `play spec` 산출물 초안. **아직 사람 승인 전(draft)**. 승인 시 status를 `approved`로 갱신한 뒤에만 `play build`.

## 목적 (goal)

지하 미궁에 몬스터(미궁 쥐·슬라임)를 배치하고, Spec A에서 남긴 **적 페이즈 훅**을 채워 턴제 전투를 구현한다. 승탑자와 몬스터가 HP를 갖고, 인접 상대에게 이동(범프)으로 공격한다. 몬스터는 승탑자를 추격한다. **처치 시 몬스터가 사라진다.** 경험치·상태창·사망 게임오버는 Spec C.

## 턴 흐름 (turn flow)

- Spec A의 `turn_manager`: 승탑자가 유효 행동으로 1턴을 소비하면 **적 페이즈**가 실행된다(기존 훅 채움).
- 적 페이즈: 살아 있는 모든 몬스터가 **행동 순서대로** 1회씩 행동(이동 또는 공격). 순서는 결정적(예: 스폰 인덱스).
- 승탑자와 몬스터의 행동은 명확히 분리된 페이즈다(동시성 없음). 서바이벌 톤에 맞게 한 수 한 수가 관찰 가능해야 한다.

## 전투 (bump combat)

- **범프 공격**: 이동하려는 칸에 적대 개체가 있으면, 이동 대신 그 개체를 공격한다(1턴 소비). 승탑자↔몬스터 양방향.
- **데미지 = 스탯 기반 랜덤 범위**: 각 개체는 `최소 공격력`·`최대 공격력` 스탯을 갖고, 데미지는 `[최소, 최대]` 범위의 정수 랜덤값이다. 방어·회피·크리티컬은 범위 밖(피격자 HP에서 데미지만 차감).
- **결정성(중요)**: 전투 랜덤은 **시드 기반 RNG 스트림**을 쓴다(던전 시드에서 파생하거나 전용 시드). 같은 시드·같은 행동 순서 → 같은 데미지 시퀀스. 재현성·테스트를 위해 전역 `randi()` 무시드 호출을 쓰지 않는다.
- HP가 0 이하가 된 **몬스터**는 즉시 제거(씬에서 사라지고 그 칸이 다시 walkable).
- **승탑자 HP가 0 이하**가 되면 `died` 신호를 방출한다. 게임오버 화면·영구사망 처리는 **Spec C**가 이 신호에 연결한다(이 spec은 신호 방출까지).

## 몬스터 AI (단순·결정적)

- **미궁 쥐**: 약함, 낮은 HP·공격. 승탑자가 일정 거리(aggro range, 데이터) 안이면 접근, 인접 시 공격. 무리 성향은 다수 스폰으로 표현(특수 로직 아님).
- **슬라임**: 느림, 높은 HP·낮은 공격. 매 턴이 아니라 **격턴 이동**(느림 표현, 데이터로 조절) 또는 낮은 이동력. 인접 시 공격.
- AI 이동은 그리드 상 승탑자 방향으로의 단순 한 칸 접근(벽·다른 개체 회피, 막히면 대기). 경로탐색(A*)은 범위 밖 — 데모엔 그리디 접근으로 충분.
- 몬스터 능력치(HP·공격·aggro·이동력)와 스폰 수는 **노멀 난이도 데이터**(딕셔너리/리소스). 장르·밸런스 상수 하드코딩 금지.

## 스폰

- 던전 생성 후 방(시작 방 제외) 바닥에 몬스터를 배치. 스폰 수·분포는 노멀 데이터 + 시드 결정적(같은 시드 → 같은 배치).

## 수용 기준 (acceptance criteria)

관찰 가능한 조건만.

1. 승탑자가 몬스터 인접 칸으로 이동 입력 → 이동하지 않고 그 몬스터의 HP가 `[공격자 최소~최대 공격력]` 범위 내 값만큼 감소, 1턴 소비.
2. 몬스터 HP가 0 이하 → 즉시 제거되고 그 칸이 walkable로 복귀.
3. 승탑자가 1턴 소비 → 적 페이즈에서 살아 있는 모든 몬스터가 1회 행동(결정적 순서).
4. aggro 범위 안 미궁 쥐는 승탑자에게 1칸 접근한다(벽/개체로 막히면 제자리).
5. 몬스터가 승탑자 인접에서 행동 → 승탑자 HP가 `[몬스터 최소~최대 공격력]` 범위 내 값만큼 감소.
6. 승탑자 HP가 0 이하 → `died` 신호 1회 방출(게임오버 처리는 하지 않음).
7. 같은 시드 → 몬스터 스폰 위치가 완전히 동일(결정성).
8. 데미지는 항상 `[최소, 최대]` 범위 안에 있고, 같은 시드·같은 행동 순서로 전투를 재현하면 데미지 시퀀스가 동일하다(시드 RNG).
9. 승탑자가 몬스터를 통과(겹침)하거나, 두 몬스터가 같은 칸에 겹치지 않는다.
10. 메인 씬이 렌더되어 던전·승탑자·몬스터가 화면에 보인다(스크린샷 스테이지 통과).

## 대상 파일 (target files)

정적 타이핑 준수. `src/core/`는 승인 spec 범위 내에서만.

| 경로 | 역할 |
|---|---|
| `src/core/stats.gd` | HP·최소/최대 공격력 등 전투 능력치 컴포넌트(승탑자·몬스터 공용). 데미지 적용·사망 판정 |
| `src/core/rng.gd` | 시드 기반 전투 RNG 스트림(range roll). 던전 시드에서 파생. 결정적 재현 |
| `src/core/actor.gd` | 그리드 위 개체 공통 기반(셀 좌표, stats, 진영). player/monster의 부모 또는 공용 인터페이스 |
| `src/core/monster.gd` | 몬스터 개체. stats + AI(접근·공격·대기). 종류별 데이터로 파라미터화 |
| `src/core/monster_ai.gd` | 그리디 접근 AI 로직(순수 함수 위주로 테스트 가능하게). 대상 방향 한 칸 이동 판정 |
| `src/core/combat.gd` | 범프 공격 해석: 공격자·피격자 → 데미지 적용. 승탑자↔몬스터 공용 |
| `src/core/turn_manager.gd` | 적 페이즈 훅 구현(몬스터 목록 순회 행동). 몬스터 등록/해제 |
| `src/core/player.gd` | 범프 판정 추가: 이동 대상 칸에 몬스터가 있으면 combat로 위임. stats·died 신호 |
| `src/core/dungeon.gd` | 스폰 배치(시드 결정적), 몬스터를 씬·grid·turn_manager에 등록 |
| `scenes/monster.tscn` | 루트 `Monster`(스크립트 monster.gd) + Sprite2D |
| `scenes/dungeon.tscn` | 몬스터 컨테이너 노드 추가(스폰 부모) |

## 필요 에셋 (assets)

### 플레이스홀더 (placeholder_gen 글리프)
| id | 글리프/색 | requested_by(후보) | 파일 |
|---|---|---|---|
| `art:enemy/dungeon_rat` | `r` / 갈색, 투명 | `scene_node:scenes/monster.tscn::Monster/Sprite2D` | `assets/art/sprites/enemy/PLACEHOLDER_dungeon_rat.png` |
| `art:enemy/slime` | `s` / 녹색, 투명 | `scene_node:scenes/monster.tscn::Monster/Sprite2D` | `assets/art/sprites/enemy/PLACEHOLDER_slime.png` |

### 효과음 (se gen — jsfxr, 무료·무제한)
| id | 이벤트 | requested_by(후보) | 백엔드 |
|---|---|---|---|
| `se:player_attack` | 승탑자 범프 공격 | `code_event:src/core/combat.gd::on_player_attack` | jsfxr |
| `se:enemy_hit` | 몬스터 피격 | `code_event:src/core/combat.gd::on_enemy_hit` | jsfxr |
| `se:enemy_death` | 몬스터 처치 | `code_event:src/core/monster.gd::on_death` | jsfxr |
| `se:player_hurt` | 승탑자 피격 | `code_event:src/core/player.gd::on_hurt` | jsfxr |

(효과음 연결은 `se attach`가 `se_emitter.gd` 브리지로 수행. 이 spec의 build는 code_event 지점을 코드에 마련하고 매니페스트에 등록까지. 실제 사운드 생성·연결은 별도 `se gen`/`se attach` 단계 — build 후 진행.)

## 범위 밖 (out of scope)

- 경험치·레벨·성장·스킬, 상태창 UI, 게임오버 화면·재시작, 계단 돌파 → Spec C
- 아이소메트릭 렌더 → 후속 iso 전환 Spec
- 경로탐색(A*), 특수 몬스터 능력, 아이템·인벤토리, 시야/안개
- 난이도 이지/하드/카오스

## 승인 후 진행

1. 사람 검토 후 status를 `approved`로 갱신.
2. `play build docs/specs/monsters_and_combat.md` — 대상 파일 구현 + placeholder 2종 + se code_event 4종 매니페스트 등록.
3. `se gen` + `se attach` — jsfxr로 효과음 4종 생성·정규화·연결.
4. `play test --screenshot` + 수용 기준 자동 테스트(전투·AI·사망 신호·결정성).
