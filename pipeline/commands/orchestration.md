# 오케스트레이션 공통 명령군 정의 (정본 계약)

> 이 문서는 오케스트레이션 공통 명령(`plan` / `verify` / `review` / `status`)의
> **입출력 계약과 처리 플로우**를 정의한다.
> 명령 범위의 최상위 정본은 `docs/command-catalog.md` 이며, 이 문서는 그중
> 오케스트레이션 공통 4명령을 구현 수준으로 상세화한 것이다.
> 슬래시 커맨드(`.claude/commands/{plan,verify,review,status}.md`)와 보조 스크립트
> (`pipeline/scripts/{verify,status,review}.py`)는 이 계약을 따른다.

## 트랙 성격

- 오케스트레이션 공통 명령은 특정 트랙(lore/play/art/se)에 속하지 않고 **전 트랙을
  가로지르는 지휘·검증·검수·현황** 계층이다. 개별 트랙 명령이 만든 산출물을 모아
  「생성 → 자동 검증 → 사람 검수 → 반영」 흐름의 **검증(verify)·검수(review)·현황
  (status)·계획(plan)** 을 담당한다. (command-catalog §오케스트레이션)
- 어떤 트랙에도 장르/스타일을 하드코딩하지 않는다 — 목표 분해·검사·큐 구성은 전부
  매니페스트·spec·lore·컨벤션 **데이터**에서 유도한다. (HANDOFF §6-3)

## 역할 분담 (HANDOFF §5, CLAUDE.md 역할 경계)

| 계층 | 담당 | 내용 |
|---|---|---|
| **기계 검사** | Python 스크립트 (`verify.py`·`status.py`·`review.py`) | 규칙으로 판정 가능한 것: 임포트/스모크 성공, 네이밍·디렉토리 규칙, 매니페스트 정합성, lore 기계 검사, 현황 집계, 상태 전이 반영 |
| **판단** | Claude (슬래시 커맨드 프롬프트) | 목표를 트랙별 태스크로 분해(`plan`), 검사 결과 해석·통합 판정(`verify`), lore **의미** 검사(게이트 5), 검수 큐 제시·요약(`review`) |
| **결정(승인)** | 사람 | play spec 승인 · art lock(스타일 승인) · review 최종 승인/반려. **생략 불가.** |

핵심 원칙:
- **승인 여부는 사람이 결정한다.** `review` 스크립트는 사람이 내린 결정을 반영만 하며
  스스로 승인하지 않는다. Claude 는 큐를 제시하고 사람의 지시를 받아 반영을 호출한다.
- **매니페스트 쓰기는 `manifest.py` 를 통해서만.** `review` 의 에셋 승인/반려도
  `manifest.py update-status` 를 경유한다. (CLAUDE.md 원칙 3)
- 스크립트는 대상 경로를 인자로 받는다(`--project`, `--manifest`, `--schema`, `--env`,
  `--specs-dir`). 테스트는 임시 복제본을 지정해 실행하며 **실데이터를 건드리지 않는다.**

## 공통 규칙

1. 모든 실행 명령은 「**생성 → 자동 검증 → 사람 검수 → 반영**」 순서를 지킨다.
2. 명령의 정의·범위는 `docs/command-catalog.md` 를 따른다. 카탈로그에 없는 동작은
   임의로 수행하지 않고 **제안만** 한다. (CLAUDE.md 명령 처리 원칙 1)
3. `plan`·`status` 는 **읽기 전용**이다. `verify` 도 읽기 전용(검사만). `review` 만이
   사람 결정에 따라 상태를 쓴다(그마저 `manifest.py`/문서 status 필드 경유).

---

## `plan <목표>`

**목적**: 자연어 목표를 **트랙별 태스크로 분해**하고 실행 순서·승인 지점을 제시한다.
(읽기 전용 — 계획만 세우고 실행하지 않는다.)

**입력**: 자연어 목표(예: "슬라임 적 추가", "플레이어 이동에 발소리 붙이기").

**출력**: 트랙별 태스크 목록 + 실행 순서(대표 워크플로 기반) + **승인 지점 표시**
(play spec 승인 / art lock / review) + 각 태스크가 근거로 삼는 카탈로그 명령.

**처리 플로우**:
1. **현황 파악**: `python3 pipeline/scripts/status.py --json` 으로 매니페스트 entry·
   spec 상태·lore 초기화 여부·style_guide(art lock) 여부·키/도구 가용성을 확인한다.
2. **분해(판단)**: 목표를 `docs/command-catalog.md` 의 명령들로 매핑해 트랙별 태스크로
   나눈다. play-first / design-first 대표 워크플로(카탈로그)를 기준으로 순서를 잡고,
   **생략 불가 승인 지점**(spec 승인·art lock·review)을 명시한다. 카탈로그에 없는
   동작은 태스크에 넣지 않고 **제안**으로만 남긴다.
3. **의존성 반영**: 현황상 선행이 안 된 것(예: style_guide 미설정이면 art gen 앞에
   art lock, lore 미초기화면 필요 시 lore init)을 순서에 반영한다.
4. (계획 제시로 끝. 실행·쓰기 없음. 사용자가 승인하면 개별 명령으로 진행.)

## `verify`

**목적**: CLAUDE.md 「검증 게이트」 5항목을 통합 실행하고 **통합 판정**을 보고한다.
반영(merge/commit) 가능 여부의 자동 게이트다.

**입력**: 프로젝트 디렉토리(기본 저장소 루트), 매니페스트/스키마 경로(기본 유도).

**검증 게이트** (`verify.py`):
| 게이트 | 내용 | 담당 |
|---|---|---|
| #1 | Godot headless 임포트 성공 | 스크립트 (play_test 재사용) |
| #2 | 스모크 테스트 통과 | 스크립트 (play_test 재사용) |
| #3 | **네이밍/디렉토리 규칙 준수** | 스크립트 (verify.py 신규) |
| #4 | 매니페스트 ↔ 실제 파일 정합성 | 스크립트 (play_test 재사용) |
| #5 | lore 정본과의 모순 없음 | **기계 검사**=lore_check.py, **의미 검사**=Claude |

**게이트 #3 검사 규칙** (docs/conventions.md 근거, `파일:항목` 으로 위반 리포트):
- `snake_case` 파일명 (`src/`·`scenes/`·`assets/`; `PLACEHOLDER_` 접두사 허용)
- 씬 파일명 = 루트 노드 PascalCase 의 snake_case 일치
- `PLACEHOLDER_` 파일은 반드시 매니페스트에 등록
- `assets/audio/se`·`bgm` 는 `.ogg` 만
- `assets/art/sprites` 는 `<카테고리>/<파일>`, `assets/art/ui` 는 `<화면>/<요소>` 경로
- 매니페스트 entry `id` 형식(스키마 패턴 재사용)
- (`.uid`·`.import`·`.gitkeep` 등 Godot·VCS 부산물, `__pycache__`·`.godot` 제외)

**게이트 #5 2계층**: `lore_check.py` 가 표기/중복/미등재/미사용 등 **기계** 결함을
검출한다. canon 이 비어 있으면(lore init 미실행) **SKIP** 하고 출력에 그 사실과
"의미 검사는 Claude 몫"임을 안내한다. 세계 규칙 vs 세력/인물 서술의 **의미적 모순**은
스크립트가 아닌 Claude 가 canon 을 읽고 판단한다.

**옵션**: `--skip-godot`(게이트 1·2 생략), `--full`(게이트에 더해
`pipeline/tests/run_*.py` 러너 전부 자동 발견·실행), `--json`.
**재귀 방지**: `--full` 은 자식 러너 실행 시 `ARTIFICER_IN_VERIFY_FULL=1` 을 심고,
이미 그 안에서 다시 `--full` 이 호출되면 러너 실행을 생략(게이트만)한다.

종료 코드: `0`=전체 통과(SKIP 포함), `1`=게이트/러너 위반, `2`=실행 오류.

**처리 플로우**:
1. **생성(실행)**: `python3 pipeline/scripts/verify.py [--full]`.
2. **판단/통합**: 게이트별 PASS/FAIL/SKIP 을 해석한다. 게이트 5 가 기계 검사만
   수행했다면 Claude 가 canon 의미 모순을 추가 판단해 **통합 판정**을 낸다.
3. **보고**: 실패 게이트의 원인(임포트 로그/스모크/네이밍 위반 `파일:항목`/정합성/
   lore 결함)을 짚고 수정 방향(어떤 트랙 명령으로 고칠지)을 제시한다. verify 는
   **고치지 않는다** — 검사·판정만 한다.

## `review`

**목적**: 승인 지점(**에셋 approved · spec 승인 · art lock**)의 **단일 창구**.
검수 대기 항목을 사람에게 제시하고, **사람이 내린 승인/반려 결정을 반영**한다.

**입력**: 없음(큐 조회) 또는 승인/반려 대상 `--id` + 사유.

**검수 큐** (`review.py list`):
- (a) `status=generated` 매니페스트 entry → **approved 후보** (id = entry id)
- (b) `status=draft` spec 문서 → **spec 승인 대기** (id = `spec:<이름>`)
- (c) `manifest.style_guide` 미설정 → **art lock 미완 표시** (정보 항목, 승인 대상 아님)

**상태 전이 규칙**:
- 에셋: `approve`/`reject` 는 현재 status 가 **generated** 일 때만 허용(생성→검수→반영).
  `approve`→`approved`, `reject`→`rejected`(+ history 에 한 줄 피드백). 이미
  approved/rejected 면 멱등 안내.
- spec: `approve`→ 문서 `status` 필드 `approved`. `reject`→ status 는 `draft` 유지
  (승인 안 됨)하고 문서에 반려 사유 노트 추가.
- art lock: 스타일 승인은 **커스텀 모델 학습 + 사람 승인**이 필요한 별도 절차이므로
  review 큐에서는 **정보로만** 표시하고, 승인은 `/art lock` 으로 안내한다.

**처리 플로우**:
1. **생성(큐)**: `python3 pipeline/scripts/review.py list` — 대기 항목을 제시한다.
2. **사람 검수**: Claude 는 각 항목(에셋 파일·spec 초안)을 사람에게 보여주고
   **항목별 승인/반려 + 한 줄 피드백**을 수집한다. **사람 결정 없이 임의 승인 금지.**
3. **반영**: 사람의 결정을 스크립트 경유로 반영한다 —
   `review.py approve --id <id>` / `review.py reject --id <id> --reason "<피드백>"`.
   (에셋은 `manifest.py update-status`, spec 은 문서 status 필드로.)
4. **자동 검증**: 반영 후 매니페스트가 유효한지(단일 창구 통과) 확인하고, 필요 시
   `verify` 로 정합성을 재확인한다.

종료 코드: `0`=성공, `1`=반영 오류(매니페스트 쓰기 실패 등), `2`=인자/상태 오류.

## `status`

**목적**: 프로젝트·태스크 현황을 한눈에 모아 보고한다. (읽기 전용)

**출력** (`status.py`, `--json` 지원):
- 매니페스트 entry: 트랙별·status별 집계 + id 목록, `style_guide`(art lock) 여부
- `docs/specs/*`: spec 문서별 status(draft/approved 등)
- `lore/canon`: 정본 문서 수(0 이면 미초기화)
- `.env` 키: `SCENARIO_API_KEY`/`SCENARIO_API_SECRET`/`ELEVENLABS_API_KEY` 의
  **존재 여부만** (값은 절대 출력하지 않음 — 비밀 보호)
- 도구 버전: godot / ffmpeg / node
- 테스트 러너: `pipeline/tests/run_*.py` 목록

**처리 플로우**:
1. **생성(실행)**: `python3 pipeline/scripts/status.py [--json]`.
2. **보고**: 요약을 제시한다. `plan` 은 이 현황을 근거로 목표를 분해하고, `review` 는
   이 현황의 대기 항목을 검수 큐로 삼는다.

---

## 대표 흐름에서의 위치 (command-catalog §대표 워크플로)

```
lore init → play spec → [승인] → play build → play test
→ art lock → art reskin → se gen → se attach → verify → review
                                                  ↑         ↑
                                          통합 검증 게이트   승인 지점 단일 창구
```

- `plan` 은 이 흐름 자체를 목표에 맞춰 세우는 지휘 명령이고, `status` 는 어느 단계에
  있는지 보여주는 현황 명령이다. `verify` 는 반영 전 자동 게이트, `review` 는 반영의
  사람 승인 창구다.

## CI (GitHub Actions)

- `.github/workflows/verify.yml` 가 push/PR 에서 `verify.py --full` 을 실행한다
  (ubuntu-latest: Python 3.12+, Node 20, ffmpeg(apt), Godot 4.6.3 headless).
- 로컬 `verify` 와 동일한 게이트 + 러너 전부를 CI 에서 재검증한다. (HANDOFF §2:
  CI 는 Phase 4 에서 GitHub Actions 로 도입 — Phase 2 로컬 verify 의 자동화판)

## 관련 파일

| 경로 | 역할 |
|---|---|
| `.claude/commands/plan.md` | `/plan <목표>` 진입점 (목표 분해) |
| `.claude/commands/verify.md` | `/verify` 진입점 (통합 검증 게이트) |
| `.claude/commands/review.md` | `/review` 진입점 (사람 검수 큐 단일 창구) |
| `.claude/commands/status.md` | `/status` 진입점 (현황 보고) |
| `pipeline/scripts/verify.py` | 검증 게이트 5항목 통합 러너 (게이트 3 신규 구현) |
| `pipeline/scripts/status.py` | 현황 집계 리포터 (JSON + 텍스트, 비밀값 마스킹) |
| `pipeline/scripts/review.py` | 검수 큐 + approve/reject 반영 (manifest.py/문서 경유) |
| `pipeline/scripts/play_test.py` | 게이트 1·2·4 스테이지 (verify 가 재사용) |
| `pipeline/scripts/lore_check.py` | 게이트 5 기계 검사 (verify 가 재사용) |
| `.github/workflows/verify.yml` | CI — push/PR 에서 `verify.py --full` |
| `pipeline/tests/run_orchestration_pipeline.py` | verify·status·review 자동 테스트 + 회귀 |
