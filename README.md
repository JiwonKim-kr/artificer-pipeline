# artificer-pipeline

Godot 게임 개발에서 **사람만 할 수 있는 일(디렉션·설계 결정·감각 판단·검수)을 제외한 나머지를 명령만으로 처리하는** AI 오케스트레이션 파이프라인.

이 저장소의 산출물은 파이프라인 자체이고, 게임은 그 **검증 대상**이다.

---

## 제출작 — 「가이드라인 (GUIDELINE)」

> 진실만으로도, 여론은 조작된다.

석간지 기자가 정보원에게 받은 **진실한 문장만을 취사·배치**해 8턴 안에 여론을 돌리는 디젤펑크 시뮬레이터. 거짓말은 한 줄도 쓸 수 없다. 쓸 수 있는 건 무엇을 싣고 무엇을 뺄지뿐이다.

| | |
|---|---|
| ▶ **플레이 (웹)** | <https://jiwonkim-kr.github.io/artificer-pipeline/> |
| **소스 브랜치** | [`game/gireki-sim`](../../tree/game/gireki-sim) — 게임 설명은 [그 브랜치의 README](../../blob/game/gireki-sim/README.md) |
| **제출 문서** | [`docs/submission/`](../../tree/game/gireki-sim/docs/submission) |

설치 없이 링크 접속 → 브라우저에서 즉시 플레이. 마우스 전용.

## 브랜치 구성

| 브랜치 | 내용 |
|---|---|
| `main` | **파이프라인 정본** — 게임 콘텐츠 없음 |
| `game/gireki-sim` | 파이프라인으로 제작한 「가이드라인」 ← **제출작** |
| `game/roguelike` | 최초 검증 대상 (로그라이크/픽셀아트) |

파이프라인(도구)과 게임(산출물)을 브랜치로 분리해 운용한다. 게임 브랜치는 파이프라인 전체를 포함하므로 단독으로 완결된다.

게임 제작 중 파이프라인에 추가·수정한 도구는 게임 콘텐츠를 제외하고 `main`으로 되돌린다. 게임 전용 테스트(여론 모델 비트-정확 대조, 턴 흐름 등)는 그 게임의 씬·데이터에 의존하므로 게임 브랜치에 남는다.

## 파이프라인 구조

**4트랙 + 로어 기반 계층.** 각 트랙은 슬래시 커맨드(`.claude/commands/`)와 보조 스크립트(`pipeline/scripts/`)로 구현된다.

| 트랙 | 명령 |
|---|---|
| `lore` | `init` · `query` · `check` · `export` — 세계관 정본(전 트랙 참조) |
| `play` | `spec` → `build` → `test` |
| `art` | `concept` → `lock` → `gen` → `reskin` |
| `se` / `bgm` | `se gen` → `se attach` · `bgm gen`(앰비언트 합성) · `bgm prep`(외부 음원 루프화) |
| 공통 | `plan` · `verify` · `review` · `status` |

트랙 간 연결은 **반드시 `pipeline/manifest.json`을 경유**한다. 매니페스트를 갱신하지 않는 에셋 생성·교체는 금지된다.

### 사람 승인 지점 (생략 불가)

**`play spec` 승인 · `art lock` · `review`.** 사람의 개입 *시간*은 줄이되 **결정권은 넘기지 않는다.** 자세한 역할 경계는 [`CLAUDE.md`](CLAUDE.md).

### 검증 게이트

`verify`가 5항목을 통과해야 반영된다 — Godot headless 임포트 / 스모크 테스트 / 네이밍·디렉토리 규칙 / 매니페스트↔실제 파일 정합성 / lore 정본 모순.

`--full`은 여기에 `pipeline/tests/run_*.py` 러너를 자동 탐색해 함께 돌린다(러너 파일을 추가하면 별도 등록 없이 편입된다). push·PR마다 CI에서 재검증한다([`verify.yml`](.github/workflows/verify.yml), Godot 4.6.3).

배포는 `workflow_dispatch` 수동 트리거다 — 공개 행위이므로 push마다 자동으로 나가지 않는다([`deploy-web.yml`](.github/workflows/deploy-web.yml)).

## 문서

| 문서 | 내용 |
|---|---|
| [`CLAUDE.md`](CLAUDE.md) | 오케스트레이션 규칙 (역할 경계·디렉토리·검증 게이트) |
| [`docs/command-catalog.md`](docs/command-catalog.md) | 명령 카탈로그 (정본) |
| [`docs/conventions.md`](docs/conventions.md) | 네이밍·규격·커밋 규칙 |
| [`HANDOFF.md`](HANDOFF.md) | 확정 결정사항·KPI·진행 현황 |
| [`docs/web-export.md`](docs/web-export.md) | 웹 export 실측 근거 |

## KPI

명령 1회당 **사람의 개입 시간(분)과 개입 횟수.** 모든 개선은 이 수치를 낮추는 방향으로만 이뤄진다.
