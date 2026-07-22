# se 명령군 정의 (정본 계약)

> 이 문서는 사운드 트랙 명령(`se gen` / `se attach`, 그리고 후순위 `bgm gen`)의 **입출력 계약과 처리 플로우**를 정의한다.
> 명령 범위의 최상위 정본은 `docs/command-catalog.md` 이며, 이 문서는 그중 사운드 트랙을 구현 수준으로 상세화한 것이다.
> 슬래시 커맨드(`.claude/commands/se*.md`)와 보조 스크립트(`pipeline/scripts/elevenlabs_client.py` · `se_jsfxr.py` · `se_post.py` · `se_attach.py` · `env_config.py`)는 이 계약을 따른다.

## 트랙 성격

- 사운드 트랙은 **후순위이며 SE(효과음) 중심**이다. BGM 은 최소 기능만 유지한다. (command-catalog §설계원칙 3)
- **쓰기 권한 경계**: `assets/audio/se/`·`assets/audio/bgm/` 는 se/bgm 명령만이 쓴다. OGG + 라우드니스 정규화 필수. (CLAUDE.md 디렉토리 규칙)
- 검증 대상 게임은 픽셀아트/로그라이크지만 **장르를 트랙에 하드코딩하지 않는다** — 어떤 이벤트가 어떤 소리를 갖는지는 매니페스트 entry(spec·params)와 lore 데이터로만 표현한다. (HANDOFF §6-3)
- 효과음 경로·매니페스트 ID·오디오 규격은 `docs/conventions.md` 를 따른다:
  `assets/audio/se/<이벤트>.ogg`, ID `se:<카테고리>/<이름>`, **OGG Vorbis · SE 모노 · -16 LUFS**.

## SE 생성 2백엔드 모델 (HANDOFF §2, §6-2 — 확정)

| 백엔드 | 성격 | 적합 대상 | 스크립트 |
|---|---|---|---|
| **elevenlabs** (기본) | 프롬프트 기반 SFX API (text → sound effect) | 자연음·질감 있는 소리 전반. `se gen` 의 텍스트 명세와 직결 | `elevenlabs_client.py` |
| **jsfxr** (병행) | 절차적 생성(sfxr 계열). **seed+파라미터 고정 → 동일 WAV 재현** | 레트로/칩튠 톤(검증 게임이 픽셀아트라 병행 활성) | `se_jsfxr.py` + `se_node/render_sfxr.js` |

- **이벤트별로 백엔드를 선택**한다. 선택은 명령 인자 또는 entry `params.backend`(`"elevenlabs"` \| `"jsfxr"`) **데이터**로 표현하고 스크립트에 하드코딩하지 않는다.
- jsfxr 프리셋: `pickupCoin` `laserShoot` `explosion` `powerUp` `hitHurt` `jump` `blipSelect` `synth` `tone` `click` `random`. 재현 파라미터(seed + resolved_params)는 entry `params.jsfxr` 에 기록해 재생성 근거로 남긴다.
- ElevenLabs 는 원시 오디오(mp3 등)를 반환하며 **정규화 전 산출물은 임시 경로에만** 둔다. 규칙 경로(`assets/audio/se/`)에는 정규화된 OGG 만 들어간다.

## 역할 분담 (HANDOFF §5)

| 계층 | 담당 | 내용 |
|---|---|---|
| **결정/판단** | 사람 | 사운드 디렉션(원하는 느낌), 최종 검수(review) |
| **설계/실행** | Claude (슬래시 커맨드 프롬프트) | 이벤트 명세 → 프롬프트/프리셋·파라미터 설계(lore 반영), 백엔드 선택 제안, 생성·정규화·attach 오케스트레이션, manifest 갱신 호출 |
| **기계적 처리** | 스크립트 (`pipeline/scripts/`) | API 호출(`elevenlabs_client.py`), 절차적 렌더(`se_jsfxr.py`), ffmpeg 정규화·측정(`se_post.py`), 씬 연결·상태 갱신(`se_attach.py`), 매니페스트 쓰기(`manifest.py`) |

핵심 원칙: **매니페스트에 대한 모든 쓰기는 `manifest.py` 를 통해서만** 이루어진다. **API 키는 코드·문서·매니페스트에 하드코딩하지 않고 `.env` 로만** 참조한다(`env_config.py`).

## 공통 규칙

1. 모든 실행 명령은 「**생성 → 자동 검증 → 사람 검수 → 반영**」 순서를 지킨다. (CLAUDE.md 명령 처리 원칙 2)
2. 트랙 간 연결은 반드시 `pipeline/manifest.json` 을 경유한다. 매니페스트를 갱신하지 않는 에셋 생성/교체는 금지. (CLAUDE.md 원칙 3)
3. 설정/세계관이 필요하면 실행 전 `lore query` 로 관련 canon 만 추출해 프롬프트 컨텍스트로 쓰고, 참조 경로를 entry `lore_refs` 에 남긴다. (CLAUDE.md 원칙 4)
4. **ElevenLabs API 키(`ELEVENLABS_API_KEY`)가 없으면** 생성 명령은 크래시 없이 한국어 안내 + 종료 코드 3 으로 멈춘다. 키 없이 요청 구성만 볼 때는 `--dry-run`. jsfxr 백엔드는 키 불필요(Node + `npm install` 만 필요, 미비 시 역시 안내 + 종료 코드 3).
5. 스크립트는 대상 경로를 인자로 받는다(`--project`, `--manifest`, `--schema`, `--env`, `--out`). 테스트는 임시 복제본을 지정해 실행하며 **실데이터(`assets/`, `scenes/`, `pipeline/manifest.json`)를 건드리지 않는다.**
6. **src/core/ 는 SE 를 모른다.** 효과음 연결은 코드 수정이 아니라 `se attach` 의 브리지 노드 삽입으로만 한다(아래 참조).

## 정규화 규격 (자동 검증 게이트)

모든 SE 산출물은 규칙 경로 반영 전에 `se_post.py` 를 통과해야 한다:

- **포맷**: OGG Vorbis (`.ogg`) — conventions.md.
- **SE**: 모노(1ch) · **-16 LUFS**(integrated) · true peak ≤ -1.5 dBTP · 44100 Hz.
- **방법**: ffmpeg **loudnorm 2-pass**(1차 측정 → 2차 linear 게인). 다운믹스는 측정 **앞**에 두어 모노 신호 기준으로 정규화한다. Vorbis 인코더는 자동 선택(libvorbis → wasm libvorbis(`se_node/encode_vorbis.js`) → 내장 vorbis(스테레오 전용)) — homebrew ffmpeg 8 슬림 빌드에 libvorbis 가 없는 환경 대응.
- **검증**: `se_post.py probe --expect-codec vorbis --expect-channels 1 --expect-i -16 --tolerance 1.0` 이 통과해야 한다(짧은 SE 는 BS.1770 게이팅 특성상 오차가 커질 수 있어 기본 허용오차 1.0 LU).

---

## `se gen <이벤트 목록>`

**목적**: 게임 이벤트 기반 효과음을 생성하고 규격(OGG 모노 -16 LUFS)으로 정규화한다.

**입력**: 대상 매니페스트 entry(보통 `placeholder` 상태의 se entry) 또는 자연어 이벤트 명세. 필요 시 lore 컨텍스트.

**출력**: `assets/audio/se/<이벤트>.ogg` (정규화 완료본, `PLACEHOLDER_` 접두사 없는 실제 경로). 재현 파라미터/프롬프트는 entry `params` 에 기록.

**처리 플로우**:
1. **백엔드 선택**: entry `params.backend` 또는 사람 지시. 기본 elevenlabs, 레트로 톤은 jsfxr. (선택 근거를 제시하고 확인받는다.)
2. **생성**:
   - elevenlabs: `python3 pipeline/scripts/elevenlabs_client.py generate --text "<이벤트 명세(+lore)>" [--duration N] --out <임시>.mp3` (키 부재 시 안내+3, `--dry-run` 가능)
   - jsfxr: `python3 pipeline/scripts/se_jsfxr.py render --spec <spec.json> --out <임시>.wav --save-params <재현 spec 저장>` (spec = `{"seed": N, "preset": "...", "params": {...}}` — seed 고정 → 동일 WAV)
3. **정규화**: `python3 pipeline/scripts/se_post.py normalize --input <임시> --output assets/audio/se/<이벤트>.ogg` (기본값이 SE 규격: 모노 -16 LUFS).
4. **자동 검증**: `se_post.py probe --input <출력> --expect-codec vorbis --expect-channels 1 --expect-i -16` 통과 확인. 실패 시 반영하지 않는다.
5. **사람 검수 / 반영**: 결과(파일·실측 LUFS·재현 파라미터)를 제시한다. 매니페스트 상태 갱신과 씬 연결은 **`se attach` 에서** 한다(이 명령은 규칙 경로에 정규화된 에셋을 만들어 두는 데까지). 재현 파라미터를 entry `params` 에 기록할 때도 `manifest.py` 를 경유한다.

## `se attach`

**목적**: 매니페스트를 기준으로 **코드 이벤트 지점에 효과음을 자동 연결**하고 상태를 갱신한다. (play 트랙 placeholder 의 실제화 — se 판 `art reskin`)

**연결 메커니즘 (src/core 무수정 원칙)**:
- 게임 로직은 시그널만 발산한다(예: `player.gd` 의 `step_completed`). SE 연결은 **범용 브리지 `src/tools/se_emitter.gd`**(AudioStreamPlayer 상속, 정적 타이핑)가 담당한다 — `_ready` 에서 export 로 주입된 `target_path`(기본 부모) 노드의 `signal_name` 시그널을 구독해 `stream` 을 재생한다. 시그널 인자 수는 `unbind` 로 흡수하므로 어떤 시그널이든 붙는다.
- `se_attach.py` 가 entry 의 `requested_by: code_event:<스크립트>::<메서드>` 에서 **씬과 시그널을 유도**한다: 스크립트가 붙은 씬(.tscn)을 scenes/ 에서 스캔하고, 메서드 본문이 emit 하는 선언 시그널을 소스에서 찾는다(모호하면 entry `params.signal` 또는 `--signal` 로 명시). 그 씬의 해당 노드 자식으로 `AudioStreamPlayer + 브리지 + stream` 노드를 삽입한다.
- 어떤 씬·시그널·스트림도 하드코딩하지 않는다 — 전부 매니페스트/스크립트 소스에서 유도된 **데이터**다.

**처리 플로우** (`se_attach.py`):
1. **생성(계획)**: `python3 pipeline/scripts/se_attach.py --dry-run [--id <entry>]` — 대상 entry 별 스크립트::메서드 → 시그널 → 씬/노드/스트림 계획을 출력한다(무변경). 실제 에셋이 없으면 SKIP(`se gen 먼저`) — 크래시 아님. `--allow-placeholder` 로 플레이스홀더 연결 가능(이때 매니페스트 상태는 유지).
2. **반영**: `python3 pipeline/scripts/se_attach.py [--id <entry>]` — 씬 삽입(멱등: 이미 연결된 씬은 skip, 플레이스홀더→실제 업그레이드는 경로 교체), **`manifest.py update-status`** 로 `placeholder → generated` + `file` 갱신(실제 에셋 연결 시), `godot --headless --import` 재임포트(`--skip-import` 로 생략).
3. **자동 검증**: `python3 pipeline/scripts/play_test.py` — 임포트·스모크·매니페스트 정합성 전체 PASS 확인.
4. **사람 검수 / 반영**: 변경 요약(삽입된 노드·시그널·스트림, 상태 갱신, play test 결과)을 제시한다. 최종 승인(`approved`)은 상위 `review`(사람) 몫이며 attach 가 임의로 approve 하지 않는다.

## `bgm gen` — 후순위 (계약만 정의, 구현은 이번 범위 밖)

- **최소 기능만 유지한다** (command-catalog §설계원칙 3, HANDOFF §2). 이번 Phase 4a 구현 범위에 포함되지 않으며, 아래 계약만 미리 고정한다:
  - 규격: OGG Vorbis · **스테레오 · -14 LUFS** · 루프 포인트 메타데이터 필수 (conventions.md). `se_post.py normalize --channels 2 --target-i -14` 로 정규화 규격은 이미 표현 가능하다(루프 메타데이터 기록은 미구현).
  - 매니페스트 ID `bgm:<카테고리>/<이름>`, 경로 `assets/audio/bgm/`.
  - 생성 백엔드·루프 메타 기록 방식은 구현 시점에 확정한다(별도 계약 갱신 필요).

---

## 환경 / API 키

- ElevenLabs 키는 저장소 루트 `.env`(`.gitignore` 등재, 커밋 금지)에 둔다. 형식:
  ```
  ELEVENLABS_API_KEY=발급받은_KEY
  ```
- 키 검증: `python3 pipeline/scripts/elevenlabs_client.py check-auth`. 키 부재 시 발급 안내 + 종료 코드 3.
- 인증 방식: **`xi-api-key` 헤더**. 엔드포인트(`POST /v1/sound-generation`, `GET /v1/user`)의 단일 정의는 `elevenlabs_client.py` 의 `Api` 블록에 격리돼 있으며 **라이브 검증 필요 TODO** 가 명시돼 있다(키 발급 후 실호출로 경로·바디·응답 포맷 재확인).
- jsfxr 백엔드: Node 18+ 와 `pipeline/scripts/se_node`(`npm install`, jsfxr@1.4.1 고정·퍼블릭 도메인). `node_modules/` 는 `.gitignore` 등재. 준비 확인: `python3 pipeline/scripts/se_jsfxr.py check`.
- 종료 코드 체계(스크립트 공통): 0 = 성공, 1 = 처리/HTTP 오류, 2 = 실행/인자 오류, 3 = 미설정(키/런타임 부재).

## 관련 파일

| 경로 | 역할 |
|---|---|
| `.claude/commands/se.md` | `/se <서브커맨드>` 디스패처 |
| `.claude/commands/se-gen.md` | `/se-gen` 진입점 |
| `.claude/commands/se-attach.md` | `/se-attach` 진입점 |
| `pipeline/scripts/env_config.py` | `.env` 로더 공용 헬퍼(stdlib) — art 트랙과 공유 |
| `pipeline/scripts/elevenlabs_client.py` | ElevenLabs SFX API 클라이언트(urllib). check-auth/generate. `--dry-run` |
| `pipeline/scripts/se_jsfxr.py` | jsfxr 절차적 백엔드 래퍼. check/presets/render (seed 재현) |
| `pipeline/scripts/se_node/` | Node 프로젝트(package.json): jsfxr 렌더(`render_sfxr.js`) + wasm Vorbis 인코더(`encode_vorbis.js`) |
| `pipeline/scripts/se_post.py` | ffmpeg 후처리: 2-pass loudnorm 정규화(normalize) · 라우드니스 검증(probe) · 인코더 탐지(encoders) |
| `pipeline/scripts/se_attach.py` | 매니페스트 code_event 기반 브리지 노드 삽입 + 상태 갱신 + 재임포트 |
| `src/tools/se_emitter.gd` | 범용 SE 브리지(AudioStreamPlayer). 시그널 구독→재생. 씬/게임 비참조 |
| `pipeline/scripts/manifest.py` | 매니페스트 읽기/쓰기 유일 창구 |
| `pipeline/tests/run_se_pipeline.py` | jsfxr 재현성 · se_post 정규화(-16 LUFS 실측) · elevenlabs dry-run · se_attach 왕복 + 회귀 |
