# play 명령군 정의 (정본 계약)

> 이 문서는 play 트랙 명령(`spec` / `build` / `test`)의 **입출력 계약과 처리 플로우**를 정의한다.
> 명령 범위의 최상위 정본은 `docs/command-catalog.md` 이며, 이 문서는 그중 play 트랙을 구현 수준으로 상세화한 것이다.
> 슬래시 커맨드(`.claude/commands/play*.md`)와 보조 스크립트(`pipeline/scripts/manifest.py`, `pipeline/scripts/play_test.py`)는 이 계약을 따른다.

## 트랙 성격

- play(플레이) 트랙은 게임 로직·씬을 만든다. 로그라이크 등 **장르/스타일은 이 트랙에 하드코딩하지 않는다** — spec 문서와 lore/manifest 데이터로만 표현한다. (HANDOFF §6-3)
- **핵심 로직 경로**: `src/core/`. 이곳은 **사람이 승인한 spec 없이 수정 금지**다. (CLAUDE.md 디렉토리 규칙)
- 보조 코드·에디터 툴은 `src/ui/`, `src/tools/` — AI 자유 작업 영역.
- 씬/스크립트/노드 네이밍은 `docs/conventions.md` 를 따른다.

## 역할 분담 (HANDOFF §5)

| 계층 | 담당 | 내용 |
|---|---|---|
| **결정/판단** | 사람 | 아이디어·디렉션, **spec 승인**, 재미/감각 판단, 최종 검수 |
| **설계/구현** | Claude (슬래시 커맨드 프롬프트) | spec 초안 작성, GDScript(정적 타이핑) + 씬 구성, placeholder 배치, manifest 등록 호출 |
| **기계적 처리** | Python 스크립트 (`pipeline/scripts/`) | 매니페스트 스키마 검증·쓰기(`manifest.py`), headless 임포트·스모크·정합성(`play_test.py`) |

핵심 원칙: **매니페스트에 대한 모든 쓰기는 `manifest.py` 를 통해서만** 이루어진다. 스키마 검증을 통과하지 못한 entry 는 기록되지 않는다. (CLAUDE.md 원칙 3, HANDOFF §5)

## 공통 규칙

1. 모든 실행 명령은 「**생성 → 자동 검증 → 사람 검수 → 반영**」 순서를 지킨다. (CLAUDE.md 명령 처리 원칙 2)
2. **`play spec` 승인은 생략할 수 없는 사람 승인 지점이다.** 승인(spec status: `approved`) 전에는 `play build` 를 진행하지 않는다. (CLAUDE.md 역할 경계, command-catalog play 표)
3. 트랙 간 연결은 반드시 `pipeline/manifest.json` 을 경유한다. 매니페스트를 갱신하지 않는 에셋 배치는 금지. (CLAUDE.md 원칙 3)
4. 플레이스홀더 에셋은 `PLACEHOLDER_` 접두사 + 매니페스트 등록 필수. (CLAUDE.md 코딩 규칙)
5. 설정/세계관이 필요하면 실행 전 `lore query` 로 관련 canon 만 추출해 컨텍스트로 쓰고, 참조 경로를 manifest entry 의 `lore_refs` 에 남긴다. (CLAUDE.md 원칙 4)
6. 스크립트는 대상 경로를 인자로 받는다(`--manifest`, `--schema`, `--project`). 테스트는 fixture/임시 사본을 지정해 실행하며 실데이터를 건드리지 않는다.

---

## `play spec <기능>`

**목적**: 아이디어를 구현 가능한 명세로 변환한다. **이 명령의 산출물(spec)은 사람 승인 지점이다.**

**입력**: 자연어 기능 설명(+ 필요 시 사용자와의 짧은 문답).

**출력 파일**: `docs/specs/<기능>.md` (snake_case). 명세는 아래 필드를 포함한다:
- **status**: `draft` → (사람 승인) → `approved`. 초안은 항상 `draft` 로 생성한다.
- **목적(goal)**: 이 기능이 해결하는 것.
- **수용 기준(acceptance criteria)**: 검증 가능한 조건 목록. `play test` 스모크가 확인할 항목의 근거가 된다.
- **대상 파일(target files)**: 생성/수정할 `src/core/` 경로(+ 씬 경로).
- **필요 에셋(assets)**: 매니페스트 placeholder 후보 목록. 각 항목은 `id`(`<track>:<카테고리>/<이름>`), 요구 명세, 사용 지점(requested_by 후보)을 명시.
- (선택) **참조 lore**: `lore query` 로 확인한 canon 경로.

**처리 플로우**:
1. **생성**: 필요하면 `lore query` 로 관련 설정을 확인하고, 확정된 내용만으로 spec **초안(status: draft)** 을 작성한다. 추측으로 빈칸을 채우지 않는다.
2. **자동 검증**: 대상 파일 경로가 규칙(`src/core/` 보호 영역, snake_case)에 맞는지, 에셋 `id` 가 `<track>:<카테고리>/<이름>` 형식인지 self-check.
3. **사람 검수**: 초안 전문을 제시하고 **명시적 승인**을 요청한다. **승인 없이는 build 로 진행하지 않는다.**
4. **반영**: 승인 시 spec 의 `status` 를 `approved` 로 갱신한다. (승인 자체는 사람의 결정이며, Claude 가 임의로 approved 로 바꾸지 않는다.)

## `play build <명세>`

**목적**: 승인된 spec 을 GDScript + 씬으로 구현하고, 필요한 placeholder 에셋을 매니페스트에 등록한다.

**전제**: 대상 spec 의 `status` 가 `approved` 여야 한다. **draft 상태면 중단하고 승인을 요청한다.**

**출력**:
- `src/core/<기능>.gd` (+ 필요 시 `src/ui/`, `src/tools/`), 씬 `<루트노드>.tscn` — **정적 타이핑**(`var x: int`) 준수.
- placeholder 에셋 파일: `PLACEHOLDER_<이름>` 접두사, 규칙 경로(`assets/art/...`, `assets/audio/...`).
- 매니페스트 entry: **`manifest.py add` 로만** 등록. `requested_by` 에 **씬 노드 경로**(`kind=scene_node`, `path=scenes/<씬>.tscn::<노드경로>`) 또는 코드 이벤트 지점을 기록한다.

**처리 플로우**:
1. **생성**: spec 의 대상 파일/수용 기준에 따라 GDScript·씬을 구현하고, 필요한 에셋 자리에 placeholder 를 배치한다.
2. **매니페스트 등록**: 각 placeholder 를 `python3 pipeline/scripts/manifest.py add --id <track>:<카테고리>/<이름> --track <...> --status placeholder --spec "<요구 명세>" --requested-by "scene_node:scenes/<씬>.tscn::<노드>" --file "<placeholder 경로>"` 로 등록한다. 검증 실패 시 매니페스트는 쓰이지 않으므로 오류를 해소한 뒤 재시도한다.
3. **자동 검증**: `play test` 를 실행해 임포트·스모크·매니페스트 정합성을 확인한다.
4. **사람 검수/반영**: 변경 요약과 `play test` 결과를 제시한다. `src/core/` 변경 커밋 본문에는 **승인된 spec 문서 경로를 명시**한다. (docs/conventions.md 커밋 규칙 — 커밋은 사용자 승인 후.)

## `play test`

**목적**: Godot headless 임포트 + 스모크 테스트 + 매니페스트 정합성을 로컬 검증한다. (verify 게이트의 play 부분)

**입력**: 프로젝트 디렉토리(기본 저장소 루트), 매니페스트/스키마 경로.

**출력**: 스테이지별 PASS/FAIL 리포트. 종료 코드 0=통과, 1=실패, 2=러너 오류.

**검사 스테이지** (`pipeline/scripts/play_test.py`):
| 스테이지 | 내용 | verify 게이트 |
|---|---|---|
| Godot headless 임포트 | `godot --headless --path <repo> --import` 성공 | #1 |
| 스모크 테스트 | `pipeline/tests/smoke_test.gd`(SceneTree) 로 부트/메인 씬 로드 무결성 | #2 |
| 매니페스트 정합성 | 스키마 유효 + `file` 지정 entry 의 실제 파일 존재 | #4 |

**단계적 설계**: 아직 씬이 없어도 각 스테이지가 의미 있게 동작한다. 스모크는 `application/run/main_scene` 미설정 시 부트/임포트만 확인하고 통과하며, `play build` 가 메인 씬을 설정하면 재실행만으로 로드/인스턴스화 검증이 활성화된다.

**처리 플로우**:
1. **생성(실행)**: `python3 pipeline/scripts/play_test.py` 실행.
2. **판단/보고**: 실패 스테이지가 있으면 원인(임포트 로그/스모크 출력/정합성 문제)을 제시하고 수정 후 재실행한다. (네이밍·디렉토리 규칙 검사와 lore 모순 검사는 상위 `verify` 명령 범위이며 이 러너 밖이다.)

---

## 관련 파일

| 경로 | 역할 |
|---|---|
| `project.godot` | Godot 4.6 프로젝트 파일 (저장소 루트, 최소 설정) |
| `.claude/commands/play.md` | `/play <서브커맨드>` 디스패처 |
| `.claude/commands/play-spec.md` | `/play-spec` 진입점 |
| `.claude/commands/play-build.md` | `/play-build` 진입점 |
| `.claude/commands/play-test.md` | `/play-test` 진입점 |
| `pipeline/scripts/manifest.py` | 매니페스트 읽기/쓰기 유일 창구 (스키마 검증 후 쓰기). CLI: validate/add/update-status/list |
| `pipeline/scripts/play_test.py` | 임포트 + 스모크 + 매니페스트 정합성 러너 |
| `pipeline/tests/smoke_test.gd` | 스모크 테스트 (SceneTree 스크립트) |
| `pipeline/tests/fixtures/manifest/` | 매니페스트 검증 fixture (정본 아님). valid + 유형별 invalid |
| `pipeline/tests/run_play_pipeline.py` | manifest 검증·쓰기 + play_test 러너 자동 테스트 |
| `docs/specs/<기능>.md` | play spec 산출물. `status: draft → approved` |
