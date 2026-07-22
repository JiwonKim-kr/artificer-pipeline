# art 명령군 정의 (정본 계약)

> 이 문서는 art 트랙 명령(`concept` / `lock` / `gen` / `reskin`)의 **입출력 계약과 처리 플로우**를 정의한다.
> 명령 범위의 최상위 정본은 `docs/command-catalog.md` 이며, 이 문서는 그중 art(디자인) 트랙을 구현 수준으로 상세화한 것이다.
> 슬래시 커맨드(`.claude/commands/art*.md`)와 보조 스크립트(`pipeline/scripts/scenario_client.py` · `art_post.py` · `art_reskin.py` · `env_config.py`)는 이 계약을 따른다.

## 트랙 성격

- art(디자인) 트랙은 그래픽 에셋(컨셉·스프라이트·UI)을 만든다. **design-first 진입점**(`art concept`)이자 play 트랙 placeholder 의 실제화 담당이다. (command-catalog §설계원칙 2)
- **쓰기 권한 경계**: `assets/art/` 하위(concepts/sprites/ui)는 **`art gen`(및 컨셉 저장)** 만이 쓴다. (CLAUDE.md 디렉토리 규칙)
- 검증 대상 게임은 픽셀아트지만 **장르/스타일을 트랙에 하드코딩하지 않는다** — 스타일은 `art lock` 이 만든 **스타일 가이드 문서 + 커스텀 모델 ID + manifest 데이터**로만 표현한다. (HANDOFF §6-3)
- 씬/파일/디렉토리 네이밍과 이미지 규격은 `docs/conventions.md` 를 따른다.

## 이미지 생성 2층 모델 (HANDOFF §2, §6-1 — 확정)

| 층 | 명령 | 모델 | 목적 |
|---|---|---|---|
| **1층: 탐색** | `art concept` | 범용 프런티어 모델(FLUX.2 / GPT Image)을 **Scenario 플랫폼 경유** 호출 | 스타일 확정 전 컨셉 후보를 폭넓게 생성 |
| **2층: 양산** | `art lock` · `art gen` | **Scenario 커스텀 스타일 모델**(잠긴 스타일 LoRA) | 확정 스타일로 일관된 게임 에셋 양산 |

- 로컬 ComfyUI 는 편의성 기준 미달로 배제. 단 **픽셀아트 그리드 정합이 미흡하면** 픽셀아트 특화 모델(Retro Diffusion 계열) 병행을 **재검토**한다(아래 "픽셀아트 정합 정책").
- 플랫폼 내장 후처리(배경 제거·투명 PNG)를 **우선** 쓰고, 부족분만 로컬 `art_post.py`(nearest 리사이즈·시트 패킹)로 보완한다.

## 역할 분담 (HANDOFF §5)

| 계층 | 담당 | 내용 |
|---|---|---|
| **결정/판단** | 사람 | 아트 디렉션, **`art lock`(아트 스타일 승인)**, 최종 검수(review) |
| **설계/실행** | Claude (슬래시 커맨드 프롬프트) | 컨셉/에셋 프롬프트 작성(lore 반영), 컨셉 선별 제안, 생성·후처리·reskin 오케스트레이션, manifest 등록 호출 |
| **기계적 처리** | Python 스크립트 (`pipeline/scripts/`) | Scenario API 호출(`scenario_client.py`), ffmpeg 후처리(`art_post.py`), 씬 교체·상태 갱신(`art_reskin.py`), 매니페스트 쓰기(`manifest.py`) |

핵심 원칙: **매니페스트에 대한 모든 쓰기는 `manifest.py` 를 통해서만** 이루어진다. **API 키는 코드·문서·매니페스트에 하드코딩하지 않고 `.env` 로만** 참조한다(`env_config.py`).

## 공통 규칙

1. 모든 실행 명령은 「**생성 → 자동 검증 → 사람 검수 → 반영**」 순서를 지킨다. (CLAUDE.md 명령 처리 원칙 2)
2. **`art lock` 승인은 생략할 수 없는 사람 승인 지점이다.** 스타일이 잠기기(`manifest.style_guide` 설정) 전에는 `art gen` 을 양산 목적으로 진행하지 않는다. (CLAUDE.md 역할 경계, HANDOFF §2)
3. 트랙 간 연결은 반드시 `pipeline/manifest.json` 을 경유한다. 매니페스트를 갱신하지 않는 에셋 생성/교체는 금지. (CLAUDE.md 원칙 3)
4. 설정/세계관이 필요하면 실행 전 `lore query` 로 관련 canon 만 추출해 프롬프트 컨텍스트로 쓰고, 참조 경로를 manifest entry 의 `lore_refs` 에 남긴다. (CLAUDE.md 원칙 4)
5. **Scenario API 키(`SCENARIO_API_KEY`/`SECRET`)가 없으면** 생성 계열 명령은 크래시 없이 한국어 안내 + 종료 코드 3 으로 멈춘다. 키 없이 요청 구성만 볼 때는 `--dry-run` 을 쓴다. (`env_config.py`, `scenario_client.py`)
6. 스크립트는 대상 경로를 인자로 받는다(`--project`, `--manifest`, `--schema`, `--env`, `--out-dir`). 테스트는 임시 복제본을 지정해 실행하며 **실데이터(`assets/`, `scenes/`, `pipeline/manifest.json`)를 건드리지 않는다.**

---

## `art concept <주제>`

**목적**: 스타일 확정 전, 범용 모델로 컨셉 후보를 복수 생성한다. (design-first 진입점)

**입력**: 자연어 주제(예: "지하 던전 슬라임 몬스터"), 필요 시 `lore query` 로 확인한 설정.

**출력**: `assets/art/concepts/` 하위 컨셉 이미지 후보 여러 장(+ 프롬프트/시드 메모). 이 단계 산출물은 **탐색용**이며 매니페스트 placeholder 를 실제화하지 않는다.

**처리 플로우**:
1. **생성**: 관련 lore 를 반영해 프롬프트를 구성하고, `scenario_client.py generate --base-model --model-id <FLUX.2/GPT Image 등> --prompt "<...>" --num-samples <N> --out-dir assets/art/concepts` 로 후보를 만든다. (키 부재 시 `--dry-run` 으로 요청만 확인.)
2. **자동 검증**: 저장된 파일을 `art_post.py probe` 로 규격(크기/투명) 확인.
3. **사람 검수**: 후보를 제시한다. 여기서의 선택은 다음 `art lock` 의 학습 입력이 된다.
4. (컨셉 저장 외 매니페스트/씬 변경 없음.)

## `art lock`  — 생략 불가 **사람 승인 지점**

**목적**: 선택된 컨셉으로 **Scenario 커스텀 스타일 모델을 학습**시켜 스타일을 고정한다. 이후 모든 `art gen` 의 기준이 된다.

**입력**: `art concept` 결과 중 사람이 고른 컨셉 이미지 **5~15장**(권장), 스타일 이름.

**출력**:
- 학습된 **커스텀 모델 ID**.
- **스타일 가이드 문서**(예: `docs/style_guide.md`): 스타일 규칙 요약 + 모델 ID + 대표 컨셉 경로 + 파라미터.
- `manifest.style_guide` = 스타일 가이드 문서 경로. (스키마: 잠기기 전 `null`)

**처리 플로우**:
1. **사람 선택/승인**: 컨셉 5~15장 선정은 **사람의 결정**이다. Claude 는 후보와 근거만 제시한다.
2. **생성(학습)**: `scenario_client.py train --name "<스타일>" --type <flux.2-dev-lora 등> --image <선택 이미지들> [--seed N]` 로 학습을 시작하고, `train --status --model-id <ID>` 로 `trained` 를 확인한다.
3. **자동 검증**: 학습 완료 후 소량 테스트 생성으로 스타일 반영을 확인한다.
4. **사람 검수/반영**: 스타일 가이드 문서 초안과 샘플을 제시해 **명시적 승인**을 받는다. 승인 후에만 `manifest.py`(추후 `style_guide` 필드 갱신 지원) 및 스타일 가이드 문서에 모델 ID 를 기록한다. **승인 없이 스타일을 잠그지 않는다.**

## `art gen <에셋 명세>`

**목적**: 잠긴 커스텀 모델로 게임 에셋을 생성하고, 후처리·규칙 경로 저장까지 일괄한다.

**전제**: 스타일이 잠겨 있어야 한다(`manifest.style_guide` 설정, 모델 ID 확보). 잠기지 않았으면 `art lock` 을 먼저 안내한다.

**입력**: 대상 에셋(보통 매니페스트의 `placeholder` entry 또는 spec 의 필요 에셋), 요구 명세, 프레임 수 등.

**출력**:
- `assets/art/sprites/<카테고리>/<이름>...png`(스프라이트) 또는 `assets/art/ui/<화면>/<요소>.png`(UI) — **투명 PNG**. (conventions 이미지 규격)
- 필요 시 스프라이트시트(프레임 정보는 매니페스트 `params` 에 기록).

**처리 플로우**:
1. **생성**: `scenario_client.py generate --model-id <잠긴 모델 ID> --prompt "<명세+스타일 반영>" [--num-samples N] --out-dir <임시/규칙 경로>`.
2. **후처리**: 플랫폼 배경 제거·투명 PNG 를 **우선** 활용하고, 부족분만 로컬로: `art_post.py resize`(픽셀아트 nearest), `art_post.py pack`(동일 크기 프레임 → 시트). `art_post.py probe` 로 투명·규격을 확인한다.
3. **자동 검증**: 규격(크기/투명/프레임)을 self-check. 픽셀 그리드 정합이 미흡하면 아래 정책에 따라 대응한다.
4. **사람 검수/반영**: 결과와 규격을 제시한다. 반영은 다음 `art reskin` 단계에서 씬에 연결하며 매니페스트 상태를 갱신한다.

## `art reskin <씬/범위>`

**목적**: 매니페스트를 기준으로 씬(.tscn) 안의 **placeholder 텍스처 경로를 실제 에셋 경로로 일괄 교체**하고 상태를 갱신한다. (play 트랙 placeholder 의 실제화)

**입력**: 대상 매니페스트 entry(기본: 실제 에셋이 준비된 `placeholder` entry, 또는 `--id` 지정).

**처리 플로우** (`art_reskin.py`):
1. **생성(계획)**: 매니페스트에서 대상 entry 를 읽어, 각 entry 의 placeholder 경로 ↔ 실제 에셋 경로(`PLACEHOLDER_` 접두사 규약)를 유도하고 `requested_by` 의 씬을 찾는다. `--dry-run` 으로 계획만 확인할 수 있다.
2. **교체/갱신**: 씬 파일의 `res://<placeholder>` → `res://<실제 경로>` 로 치환하고, **`manifest.py update-status`** 로 상태를 `placeholder → generated` 로 갱신(+ `file` 실제 경로 반영)한다. (매니페스트 단일 창구)
3. **자동 검증**: `godot --headless --import` 재임포트 후 `play test` 로 임포트·스모크·정합성을 확인한다.
4. **사람 검수/반영**: 변경 요약을 제시한다. 최종 승인(`approved`)은 상위 `review`(사람 검수) 몫이며 reskin 이 임의로 approve 하지 않는다.

---

## 픽셀아트 정합 정책 (HANDOFF §6-1)

- 기본은 Scenario 커스텀 스타일 모델 + 로컬 nearest 후처리로 픽셀 그리드를 맞춘다.
- **그리드 정합이 반복적으로 미흡**하면(픽셀이 뭉개지거나 격자에 안 맞으면): (a) `art_post.py resize` 를 목표 타일 배수로 강제, (b) 그래도 부족하면 **Retro Diffusion 계열 픽셀아트 특화 모델 병행**을 재검토한다. 이 정책은 **문서/정책으로만** 표현하고 명령·스크립트에 픽셀아트 상수를 하드코딩하지 않는다. (HANDOFF §6-3)

## 환경 / API 키

- 키는 저장소 루트 `.env`(`.gitignore` 등재, 커밋 금지)에 둔다. 형식:
  ```
  SCENARIO_API_KEY=발급받은_KEY
  SCENARIO_API_SECRET=발급받은_SECRET
  # (선택) SCENARIO_PROJECT_ID=프로젝트_ID
  ```
- 키 검증: `python3 pipeline/scripts/scenario_client.py check-auth`. 키 부재 시 발급 안내 + 종료 코드 3.
- 인증 방식: Scenario **Basic 인증**(`base64(KEY:SECRET)`). 엔드포인트/응답 스키마의 단일 정의는 `scenario_client.py` 의 `Api` 블록에 격리돼 있으며 **라이브 검증 필요 TODO** 가 명시돼 있다.

## 관련 파일

| 경로 | 역할 |
|---|---|
| `.claude/commands/art.md` | `/art <서브커맨드>` 디스패처 |
| `.claude/commands/art-concept.md` | `/art-concept` 진입점 |
| `.claude/commands/art-lock.md` | `/art-lock` 진입점 (사람 승인 지점) |
| `.claude/commands/art-gen.md` | `/art-gen` 진입점 |
| `.claude/commands/art-reskin.md` | `/art-reskin` 진입점 |
| `pipeline/scripts/env_config.py` | `.env` 로더 공용 헬퍼(stdlib). se 트랙도 재사용 |
| `pipeline/scripts/scenario_client.py` | Scenario API 클라이언트(urllib). check-auth/generate/train/remove-bg. `--dry-run` |
| `pipeline/scripts/art_post.py` | 로컬 후처리(ffmpeg): nearest 리사이즈 · tile 시트 패킹 · 투명 probe |
| `pipeline/scripts/art_reskin.py` | 매니페스트 기반 placeholder→실제 에셋 씬 교체 + 상태 갱신 + 재임포트 |
| `pipeline/scripts/manifest.py` | 매니페스트 읽기/쓰기 유일 창구 (스타일 잠금 시 `style_guide` 기록) |
| `pipeline/tests/run_art_pipeline.py` | env_config·scenario_client·art_post·art_reskin 자동 테스트 + 회귀 |
| `docs/style_guide.md` | `art lock` 산출물(스타일 규칙 + 커스텀 모델 ID). 잠금 전 미생성 |
