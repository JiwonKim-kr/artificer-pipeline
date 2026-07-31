---
status: approved
track: play
name: turn_loop_vertical_slice
title: 「태엽 인간」 Phase B — 1턴 수직 슬라이스 (정면 모니터 · 레트로 OS UI · 여론엔진 이식)
references:
  - lore/canon/world.md
  - lore/canon/factions.md
  - docs/design/스토리_태엽인간_v0.3.md
  - docs/design/태엽인간_기사조각_헤드라인_초안_v0.1.md
  - docs/design/댓글뱅크_설계_v0.1.md
  - sim/opinion-model/ (설계·검증 오라클 + 이식 대조 기준)
---

# 목적 (goal)
정면 고정 시점 책상 화면에서 **모니터 클릭 → 전체화면 전환 + CRT 셰이더 → 레트로 OS 창 UI**로
**1턴을 end-to-end** 완결한다: 정보원 사실 확인 → 원고 작성(조각 취사 + 프레임·톤·채널 + 왜곡)
→ 발행 → 세그먼트별 댓글 반응 + 아날로그 여론 게이지 갱신 → 턴 결과. 여론 로직은
`sim/opinion-model`을 GDScript로 **비트-정확 이식**하고 sim과 대조해 정확성을 증명한다.

# 확정 결정 (근거: 검토 라운드)
1. **모델 config = 단일 출처.** `config.json`을 `src/core/data/opinion_config.json`으로 이전,
   sim 러너와 게임이 같은 파일을 읽는다(드리프트 0). export는 src/ 포함이라 자동 패킹.
2. **RNG = 32비트 비트-정확 이식**(`RngMulberry32`). 발각 경로까지 sim과 uint32 완전 일치.
3. **셰이더 컨벤션** `src/ui/shaders/<이름>.gdshader`(snake_case). **런타임 데이터 디렉토리**
   `src/core/data/`(모델 config·콘텐츠·튜닝 JSON).

# 아키텍처
- **데스크뷰 = 정적 배경 아트**(모니터 화면 아트상 꺼짐, 라이브 렌더 없음).
- **모니터 클릭 → 전체화면 "스크린 상태" 전환**(Tween). 이 상태에서만 **CRT 전체화면 후처리 1패스**
  (web-export.md 검증 구성 `화면 → BackBufferCopy(copy_mode=2) → CRT ColorRect` 재사용).
- **입력 = 마우스/클릭 전용**(자유 텍스트 없음, 기사는 조각·레버 선택으로 구성).
- **2계층**: 모델 상수=`opinion_config.json`(공용 단일 출처), 게임 계층 튜닝=`lever_tuning.json`.

# UI 모델 (레트로 OS 창)
- **정보원 창**: 이번 턴 사실(F1·F2)의 전체 조각(유·불리·중립 전부) = "정보 전부 진실".
- **원고 작성 창**: 조각 포함/제외(누락), 순서(재배치), 프레임(찬성/중립/반대각)·톤(자극/중립/차분)
  ·채널(올드/SNS), 헤드라인(과장 여부) → **발행**.
- **댓글 창**: 발행 후 세그먼트별 미시 반응(댓글 뱅크).
- **여론 게이지**: 거시 지지율을 부정확 아날로그 바늘로 느리게 갱신(수치 비표시).
- **계기 비표시**: 발각·평판·압박은 게이지 없이 암시 문구로만.

# 왜곡 → δ 매핑 (게임 계층 · `src/core/data/lever_tuning.json`)
> 엔진은 왜곡을 단일 스칼라 δ∈[0,1]로만 받는다(종류 구분 없음). 프레임은 δ와 **독립 명시 레버**.
```
δ = 0 (정직 균형)
+ 불리 조각 1개 제외(누락)   += w_omit
+ 유리를 리드로 재배치        += w_reorder
+ 과장 헤드라인 선택          += w_exagg
δ = clamp01(δ);  article = { frame, tone, channel, distortion: δ }
```

# 대상 파일 (target files)
> `src/core/`·`src/ui/`·`scenes/` 하 snake_case. 씬=scenes/, 스크립트=src/.

**코어 로직**
- `src/core/opinion_model.gd` — `opinion-model.mjs` 이식(updateSegment·macroOpinion·contestedness·
  initState·step·isWon 등). 순수 로직, 씬 의존 없음.
- `src/core/rng_mulberry32.gd` — makeRng 비트-정확 이식(아래 §RNG 구현).
- `src/core/turn_manager.gd` — 1턴 오케스트레이션 + 상태.
- `src/core/data/opinion_config.json` — 모델 config **단일 출처**(sim에서 이전).
- `src/core/data/lever_tuning.json` — δ 가중치 등 게임 계층 튜닝값.
- `src/core/data/content_slice.json` — 슬라이스 콘텐츠(F1·F2 조각/헤드라인 + 세그먼트 댓글).
  Phase C "LLM 베이킹" 콘텐츠 뱅크의 씨앗.

**씬 / UI**
- `scenes/main.tscn`(Main) — 데스크 배경 + 모니터 클릭 영역 + 스크린 컨테이너 + CRT ColorRect(전체화면).
- `src/ui/desk_view.gd` — 데스크↔스크린 줌 트랜지션.
- `scenes/screen_os.tscn`(ScreenOS) + `src/ui/screen_os.gd` — 창 매니저.
- `scenes/informant_window.tscn` / `editor_window.tscn` / `comments_window.tscn` /
  `opinion_gauge.tscn` + 각 `src/ui/*.gd`.
- `src/ui/shaders/crt_screen.gdshader` — CRT 후처리(gl_compatibility, web-export.md 프래그먼트 기반).

# RNG 구현 (§비트-정확)
정직(δ=0)은 RNG 미호출→결정론. 왜곡은 발각 굴림에 RNG 사용(δ=1, 1턴 ≈17% 발동)→비트-정확 필요.
```gdscript
class_name RngMulberry32
extends RefCounted
var _a: int  # 32비트 unsigned (0..2^32-1)
func _init(seed: int = 1) -> void:
    _a = seed & 0xFFFFFFFF
static func _imul(x: int, y: int) -> int:  # JS Math.imul, int64 오버플로 회피(16비트 분할)
    x &= 0xFFFFFFFF; y &= 0xFFFFFFFF
    var xl := x & 0xFFFF; var xh := (x >> 16) & 0xFFFF
    var yl := y & 0xFFFF; var yh := (y >> 16) & 0xFFFF
    var low := xl * yl
    var mid := (xh * yl + xl * yh) & 0xFFFF
    return (low + (mid << 16)) & 0xFFFFFFFF
func next_uint32() -> int:  # 테스트 대조용(부동소수 배제)
    _a = (_a + 0x6D2B79F5) & 0xFFFFFFFF
    var t := _imul(_a ^ (_a >> 15), 1 | _a) & 0xFFFFFFFF
    t = ((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
    t &= 0xFFFFFFFF
    return (t ^ (t >> 14)) & 0xFFFFFFFF
func next() -> float:
    return float(next_uint32()) / 4294967296.0
```

# 필요 에셋 (매니페스트 placeholder)
| id | 명세 | requested_by |
|---|---|---|
| `art:ui/main/desk_bg` | 정면 책상 배경. 외부(Gemini) 생성본 수동 등록 → 16:9 최종+review 전까지 placeholder | `scene_node:Main/Background` |
| `art:ui/window/frame` | 레트로 OS 창 크롬 | `scene_node:ScreenOS` |
| `art:ui/gauge/opinion_needle` | 부정확 아날로그 게이지 판+바늘 | `scene_node:OpinionGauge` |
- `PLACEHOLDER_` 접두사 + 매니페스트 등록. SE는 Phase D(비범위).

# 수용 기준 (acceptance criteria)
1. Godot 헤드리스 임포트 + 스모크 통과.
2. **이식(정직)**: 시나리오①(찬성각·자극·SNS·δ0) 1턴 후 세그먼트 x가 sim 골든 픽스처와 **부동소수 동일**
   (부동층 0.50→약 0.52 근방).
3. **이식(RNG/발각)**: `RngMulberry32.next_uint32()` 시퀀스가 sim `makeRng` 골든 uint32 배열과 **정수 완전 일치**.
   동일 시드·δ에서 발각 발동·피해가 sim과 일치.
4. 모델 config 단일 출처: 게임이 `res://src/core/data/opinion_config.json`을 읽고 sim 러너도 동일 파일 참조.
5. 모니터 클릭 → 전체화면 전환 + CRT 렌더(스캔라인/곡률/색수차, 컴파일 에러 0).
6. 정보원 창에 F1·F2 **전체 조각(유·불리)** 표시.
7. 원고 작성에서 프레임/톤/채널 선택 + 누락/재배치/과장 시 **δ 증가**, 발행 시 δ가 engine에 전달(로그 관찰).
8. 발행 후 댓글 창 세그먼트별 반응 ≥2종(부동층·반대층) + 여론 게이지 **느린** 갱신(미시≠거시 시차).
9. 정직 찬성각·자극·SNS 1턴에 부동층 x **상승 방향**.
10. **웹 export 정합**: 런타임 데이터(`src/core/data/**`) pck 포함, `.mjs`·content/ 제외. 네이밍/매니페스트 정합(verify 3·4).

# 선행 작업 (build 전 반영 — 팀원 파일 포함, 조율 필요)
> junho 소유(#A) / JiwonKim 소유(#B). 조율 후 반영.

**A. config 단일 출처 이전**
```bash
git mv sim/opinion-model/config.json src/core/data/opinion_config.json
```
```diff
# sim/opinion-model/simulate.mjs (4행), montecarlo.mjs (3행)
- new URL("./config.json", import.meta.url)
+ new URL("../../src/core/data/opinion_config.json", import.meta.url)
```
export_presets 수정 불필요(src/ 포함). 이전 후 재-export로 pck 포함 재확인.

**B. 컨벤션·디렉토리 문서화**
- `docs/conventions.md` "파일/디렉토리 네이밍"에 셰이더 규칙 추가:
  `- 셰이더: src/ui/shaders/<이름>.gdshader (snake_case). ShaderMaterial는 <이름>_material.tres.`
- `CLAUDE.md` 디렉토리 표에 행 추가:
  `| src/core/data/ | 런타임 데이터(모델 config·콘텐츠·튜닝 JSON) | 승인된 spec 기반. 웹빌드 포함 |`
- `.gdshader`는 verify gate#3이 이미 snake_case 강제(코드 변경 없음).

**C. 대조 픽스처**
- `sim/opinion-model/`에 골든 덤퍼 추가 → `makeRng(1)` 첫 16개 uint32 + 시나리오① 1턴 결과를
  `pipeline/tests/fixtures/opinion_golden.json`으로 커밋. Godot 헤드리스 테스트가 대조.

# 자동 검증 (self-check)
- 파일 전부 보호영역·snake_case, 씬명=루트노드 snake_case. ✔
- 에셋 id 3종 `art:<카테고리>/<이름>` 형식. ✔ · 수용기준 관찰 가능. ✔
- 선행 A/B/C 완료가 build 진입 조건.

# 범위 밖 / 후속
- 8턴·분기(F15/F16)·압박 컷신·엔딩 4종·maxTurns(A2)·FPS 재측정 = Phase C~.
- 발각·평판·압박 3축은 이식하되 슬라이스에서 미소진 → Phase C 검증.
- topic 정본 불일치(`요나스반전`/`임금`) 정리 = Phase C.
- (옵션) 데모 임팩트용 2~3턴 확장.
