# lore 명령군 정의 (정본 계약)

> 이 문서는 lore 트랙 명령(`init` / `query` / `check`)의 **입출력 계약과 처리 플로우**를 정의한다.
> 명령 범위의 최상위 정본은 `docs/command-catalog.md` 이며, 이 문서는 그중 lore 트랙을 구현 수준으로 상세화한 것이다.
> 슬래시 커맨드(`.claude/commands/lore*.md`)와 보조 스크립트(`pipeline/scripts/lore_*.py`)는 이 계약을 따른다.

## 트랙 성격

- 로어(설정/세계관)는 4번째 트랙이 아니라 **기반 계층**이다. 모든 트랙이 참조하는 단일 정본(canon) 역할을 한다. (command-catalog §설계원칙 4)
- **정본 경로**: `lore/canon/`. 쓰기는 `lore *` 명령을 통해서만 수행한다. (CLAUDE.md 디렉토리 규칙)
- 권장 구조: `canon/world.md`(세계), `canon/factions.md`(세력), `canon/characters/`(인물), `canon/glossary.md`(용어). (lore/README.md)

## 역할 분담 (HANDOFF §5)

| 계층 | 담당 | 내용 |
|---|---|---|
| **결정/판단** | Claude (슬래시 커맨드 프롬프트) | 문답 진행, canon 문서 작성, 자연어 답변 합성, **의미적 모순 판단** |
| **기계적 처리** | Python 스크립트 (`pipeline/scripts/`) | 마크다운 파싱/색인, 키워드 검색, 표기·중복·미등재·미사용 등 **기계적으로 결정 가능한 검사** |

핵심 원칙: 스크립트는 "표기가 다르다/중복이다/glossary에 없다" 같이 **규칙으로 판정 가능한 것만** 리포트한다.
"세력 A의 서술이 세계 규칙과 충돌하는가" 같이 **판단이 필요한 검사는 스크립트가 하지 않는다.** Claude가 수행한다.

## 공통 규칙

1. 모든 실행 명령은 「**생성 → 자동 검증 → 사람 검수 → 반영**」 순서를 지킨다. (CLAUDE.md 명령 처리 원칙 2)
2. `lore/canon/` 쓰기 전, 관련 기존 canon 항목만 추출해 컨텍스트로 사용하고 정본과 모순되는 산출물을 만들지 않는다. (CLAUDE.md 원칙 4)
3. 파일/디렉토리 네이밍은 `snake_case`. (docs/conventions.md)
4. 스크립트는 canon 경로를 `--canon` 인자로 받는다. 미지정 시 기본값은 `lore/canon`. 테스트는 fixture 경로를 지정해 실행한다.

---

## `lore init`

**목적**: 컨셉 문답을 통해 세계관 골격 문서를 생성한다. (빈 상태에서 canon 초기화)

**입력**: 사용자와의 대화형 문답 (장르, 톤, 무대, 핵심 갈등, 주요 세력/인물, 핵심 용어 등).

**출력 파일** (`lore/canon/` 하위):
- `world.md` — 세계 개요/역사/규칙
- `glossary.md` — 핵심 용어집 (표준 표기의 단일 출처)
- (선택) `factions.md`, `characters/` — 문답에서 확보된 경우

**glossary 표기 규약** (스크립트 파싱 대상): 용어는 아래 형식 중 하나로 기입한다.
```
- **용어** — 설명
- **용어**: 설명
### 용어            (레벨 3+ 헤딩도 용어로 인식)
```

**처리 플로우**:
1. **생성**: 기존 canon 이 있으면 `lore_index.py index` 로 현황을 먼저 파악한다. 질문 목록(슬래시 커맨드 참조)으로 문답을 진행하고, 확정된 답만으로 골격 문서를 작성한다. 추측으로 빈칸을 채우지 않는다.
2. **자동 검증**: 작성 직후 `lore_check.py --canon lore/canon` 를 실행해 표기/중복/미등재/미사용을 self-check 한다.
3. **사람 검수**: 생성될 문서 초안과 검사 결과를 사용자에게 제시하고 승인을 받는다.
4. **반영**: 승인 후에만 `lore/canon/` 에 파일을 기록한다.

## `lore query <질문>`

**목적**: canon 문서에서 관련 항목만 추출해 답변(사람용) 또는 컨텍스트(다른 명령 주입용)로 반환한다.

**입력**: 자연어 질문 또는 키워드.

**출력**: 관련 섹션/용어 발췌 + 근거 파일 경로(`파일:줄`). canon 에 없는 내용은 **지어내지 않고** "canon 에 없음"으로 답한다.

**처리 플로우**:
1. **생성(검색)**: `lore_index.py query --canon lore/canon "<질문>"` 로 관련 섹션/용어 후보를 기계적으로 회수한다.
2. **판단/합성**: 회수된 발췌만을 근거로 Claude 가 답변을 합성한다. 근거를 함께 표기한다.
3. (조회 명령이므로 canon 쓰기·사람 승인 없음. 순수 읽기.)

## `lore check`

**목적**: 정본의 모순·공백 후보를 리포트한다. 기계적 검사(스크립트) + 의미적 검사(Claude) 2계층.

**입력**: canon 경로(기본 `lore/canon`).

**출력**: 결함 후보 리포트. 각 항목은 `파일:줄`, 코드, 심각도(error/warning/info), 메시지를 갖는다.

**기계적 검사 항목** (`lore_check.py`):
| 코드 | 심각도 | 내용 |
|---|---|---|
| `duplicate_glossary_def` | error | 같은 용어가 glossary에 2회 이상 정의됨 |
| `notation_mismatch` | warning | glossary 용어가 본문에서 다른 표기로 사용됨 (대소문자/공백/하이픈 변형) |
| `undefined_term` | info | 본문에서 **강조**된 후보 용어가 glossary에 없음 (등재 후보) |
| `orphan_term` | info | glossary에 정의됐으나 어느 본문에서도 안 쓰임 (미사용/공백 후보) |

종료 코드: `0`=error/warning 없음, `1`=error 또는 warning 검출, `2`=실행 오류.

**의미적 검사(Claude 담당)**: 스크립트 리포트를 입력으로 받아, 규칙으로 판정 불가한 설정 충돌(세계 규칙 vs 세력/인물 서술의 모순, 연대기 불일치, 공백 등)을 canon 발췌 근거와 함께 판단한다.

**처리 플로우**:
1. **생성(기계 검사)**: `lore_check.py --canon lore/canon` 실행 → 기계적 리포트.
2. **판단(의미 검사)**: Claude 가 canon 을 읽고 의미적 모순/공백 후보를 추가 리포트.
3. **사람 검수/반영**: 통합 리포트를 제시. 수정은 별도 `lore edit`(미구현, Phase 1 범위 밖) 또는 사용자 지시로 진행하며, `lore check` 자체는 canon 을 쓰지 않는다.

---

## 관련 파일

| 경로 | 역할 |
|---|---|
| `.claude/commands/lore.md` | `/lore <서브커맨드>` 디스패처 |
| `.claude/commands/lore-init.md` | `/lore-init` 진입점 |
| `.claude/commands/lore-query.md` | `/lore-query` 진입점 |
| `.claude/commands/lore-check.md` | `/lore-check` 진입점 |
| `pipeline/scripts/lore_index.py` | canon 파싱/색인/검색 (index, query) |
| `pipeline/scripts/lore_check.py` | 기계적 정합성 검사 리포터 |
| `pipeline/tests/fixtures/` | 테스트용 canon (정본 아님). `sample_canon`(결함 포함), `clean_canon`(무결함) |
| `pipeline/tests/run_lore_roundtrip.py` | init(fixture)→query→check 왕복 자동 테스트 |
