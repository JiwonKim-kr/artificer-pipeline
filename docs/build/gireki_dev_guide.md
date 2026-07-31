# 「태엽 인간」 개발 가이드 — 이어서 작업하기

> 대상: 이 게임 코드를 이어받아 개발할 팀원. 브랜치 `gireki-phase-c` 기준.
> 이 문서만 읽으면 구조 파악 + 실행 + 확장(사실·댓글·엔딩 추가·밸런싱)까지 시작할 수 있다.
> 상위 설계: `docs/specs/turn_loop_vertical_slice.md`, `docs/build/phase_c_plan.md`, `docs/design/*`.

---

## 1. 한눈에
석간지 기자가 **정보원이 준 진실한 문장들을 취사(넣을지 말지)**해 기사를 쓰고, 8턴 안에
**SNS 부동층을 찬성 65%로** 돌리는 여론조작 게임. 무엇을 넣고 빼느냐로 기사의 **논조가 도출**되고,
불리한 사실을 빼면 찬성에 유리하지만 **발각 리스크**가 오른다.

- **엔진**: 검증된 여론 확산 모델(bounded-confidence + 확증편향 + 역풍 + 톤×감정 + 발각/평판)을
  GDScript로 **비트-정확 이식**. 결과가 규칙표가 아니라 창발한다.
- **UI**: 정면 데스크 → 모니터 클릭 → 전체화면 **CRT OS 창**(정보원·원고작성·댓글·여론게이지).

## 2. 2계층 아키텍처 (중요)
- **개발/검증 계층** `sim/opinion-model/` — JS 원본 모델 + 검증 러너(simulate/montecarlo). **웹빌드 제외**.
  이식의 **정답(오라클)**. 게임 로직을 바꾸면 여기와 대조한다.
- **런타임 계층** `src/core/`, `src/ui/` — 실제 게임(GDScript). 웹빌드에 포함.
- **모델 config는 단일 출처**: `src/core/data/opinion_config.json` 하나를 **sim과 게임이 같이 읽는다**
  (sim 러너가 `../../src/core/data/opinion_config.json` 참조). 드리프트 0.

## 3. 핵심 파일 & 데이터 흐름
```
[원고작성 창] 문장 블록 체크 → TurnManager.publish(included_ids)
   └ 유리노출·불리은폐 → 논조(frameValue) & 왜곡(δ) 도출 (lever_tuning.json)
   └ OpinionModel.step(article) → 세그먼트 여론 갱신 + 발각 굴림
   └ 압박(반대각 누적)·분기(F7→F16, 책상→F15)·엔딩 판정
   → [댓글 창] 세그먼트 반응 · [게이지] 거시 여론 바늘 · [엔딩 오버레이]
```
| 파일 | 역할 |
|---|---|
| `src/core/opinion_model.gd` | 여론 엔진 이식(순수 로직). frameValue 직접 수용. |
| `src/core/rng_mulberry32.gd` | mulberry32 비트-정확 RNG(발각 굴림). |
| `src/core/turn_manager.gd` | 오케스트레이션: `get_blocks`·`publish`·`check_ending`·압박·`discover_theo`·F16 개폐. |
| `src/core/data/opinion_config.json` | **모델 상수 단일 출처**(세그먼트·k·epsMax·detection·mission). |
| `src/core/data/content_slice.json` | **사실(F#)·조각·헤드라인 + 댓글**. 태그(유리/불리/중립)는 내부 계산용. |
| `src/core/lever_tuning.json` | 게임 계층 튜닝: `w_omit`(은폐→δ), `k_lean`(기울기), 고정 tone/channel. |
| `src/ui/main.gd` | UI 전체(데스크·CRT OS 창·발행·엔딩·책상탐색). |
| `src/ui/shaders/crt_screen.gdshader` | CRT 후처리(gl_compatibility). |
| `scenes/main.tscn` | 진입 씬(루트 Main → main.gd). |
| `pipeline/tests/opinion_parity_test.gd` | 이식 ↔ sim 골든 대조(RNG·시나리오·발각). |
| `pipeline/tests/turn_flow_test.gd` | 턴 흐름·엔딩·압박·분기 로직 검증(헤드리스). |
| `pipeline/tests/dump_opinion_golden.mjs` | 골든 픽스처 생성기(config 바꾸면 재실행). |

## 4. 게임 규칙 요약 (코드에 반영됨)
- **논조 도출**: `lean = 유리노출 + 불리은폐 − 불리노출` → `frameValue = clamp(0.5 + k_lean·lean, 0.2, 0.8)`.
  `δ(발각) = clamp01(w_omit · 불리은폐수)`. (turn_manager.publish)
- **승/패·엔딩**(check_ending, 우선순위): 발각 2회+ → **발각파탄** / 압박 4회+ → **배신파탄** /
  부동층 ≥ winThreshold → **성공** / turn ≥ maxTurns → **실패**.
- **압박**: 반대각 기사 낼 때마다 +1, 단계별 암시 문구(수치 비표시). 4 초과 → 배신파탄.
- **분기**: F15는 `discover_theo()`(데스크 "책상 뒤지기")로만 등장(hidden). F16은 F7을 **반대각 보도**하면
  열림(gated), 찬성/중립 보도면 닫힘(편집장 메일 흔적).
- **태그 비노출**: 유리/불리/중립은 절대 UI에 보이지 않는다(플레이어가 판단).

## 5. 실행 & 검증 (이 저장소)
- 도구: Godot 4.5.1(로컬)/4.6.x(CI), Node 20, Python 3. **Windows는 python 앞에 `PYTHONUTF8=1`**(cp949 회피).
- `GODOT_BIN` 예(이 PC): `/c/Users/<계정>/Desktop/Godot_v4.5.1-stable_win64.exe/Godot_v4.5.1-stable_win64_console.exe`
```bash
# 임포트
"$GODOT_BIN" --headless --path . --import
# 이식 대조 (엔진 안 건드렸으면 항상 PASS 유지)
"$GODOT_BIN" --headless --path . --script res://pipeline/tests/opinion_parity_test.gd   # PARITY_RESULT: PASS
# 게임 로직(턴·엔딩·압박·분기)
"$GODOT_BIN" --headless --path . --script res://pipeline/tests/turn_flow_test.gd        # TURN_RESULT: PASS
# 파이프라인 게이트(임포트·스모크·매니페스트)
PYTHONUTF8=1 GODOT_BIN="$GODOT_BIN" python pipeline/scripts/play_test.py
# 실제 렌더 스크린샷(창 뜸)
PYTHONUTF8=1 GODOT_BIN="$GODOT_BIN" python pipeline/scripts/play_test.py --screenshot
```
- CI: push/PR에서 `verify.py --full`. art/se 자기검증 러너는 ffmpeg/API키 의존(로컬 Windows에선 실패해도
  코드 문제 아님, Linux CI 기준).

## 6. 확장 레시피 (코드 거의 안 건드림)
- **사실 추가**: `content_slice.json`의 `facts`에 `{topic,title,fragments:[{tag,text}],headlines}` 추가.
  `hidden:true`(책상 발견형) / `gated:true`(F16류 개폐형) 옵션. → `get_blocks`에 자동 반영, 코드 무수정.
- **댓글 추가**: `comments`에 `{seg,reaction,frame,topic,text}`. 선택은 seg+reaction 우선, frame/topic 가점.
- **밸런싱**: `opinion_config.json`(k·epsMax·anchorLambda·detection·`mission.maxTurns`/`winThreshold`) +
  `lever_tuning.json`(w_omit·k_lean). ⚠️ **opinion_config를 바꾸면 `node pipeline/tests/dump_opinion_golden.mjs`로
  골든 재생성** 후 parity 재확인(안 하면 대조 테스트가 깨진다).
- **엔딩 추가/수정**: `turn_manager.check_ending()` 조건 + `main.gd`의 `ENDINGS` 문구.
- **압박 단계**: `turn_manager`의 `PRESSURE_HINTS` / `PRESSURE_BREAK`.

## 7. 현재 상태 & 남은 작업
| 구간 | 상태 |
|---|---|
| 엔진 이식 + config 단일출처 + 대조 | ✅ (parity PASS) |
| 1턴 슬라이스 UI(CRT OS·문장취사·댓글·게이지) | ✅ |
| C1 다중턴+승/패+엔딩3종 · C3 압박+배신엔딩 · C4 분기(F15/F16) | ✅ |
| 엔딩 4종 도달 | ✅ (성공/실패/발각파탄/배신파탄) |
| **C6 밸런싱**(maxTurns·상수 확정) · topic 정본(요나스반전/임금) 정리 | ⬜ |
| **C5 후일담**(엔딩 정직/냉혹 분기 문구) | ⬜ (문구 필요) |
| **콘텐츠 대량 베이킹**(F 전체·댓글 변주) | ⬜ 사람+오프라인 LLM(스토리 §10) |
| **아트/사운드**: 배경 16:9 최종 reskin · 게이지 아트 · se gen/attach | ⬜ (placeholder 상태) |
| **웹 export → GitHub Pages** | ⬜ (실측은 `docs/web-export.md`) |

## 8. 주의점
- **엔진 로직 수정 시** 반드시 sim(오라클)과 대조(parity). config 변경 시 골든 재생성.
- `.import`는 커밋 안 함(임포트 시 재생성). PNG만 커밋.
- 매니페스트 쓰기는 `manifest.py`로만, placeholder는 `placeholder_gen.py`로만(직접 편집 금지).
- CRT 곡률은 클릭 정합 위해 약하게 유지.
- LF→CRLF 경고는 Windows 줄바꿈 자동변환 안내(무해).

## 9. 참고
- spec: `docs/specs/turn_loop_vertical_slice.md`, `docs/specs/phase_c_turn_progression.md`
- 계획: `docs/build/turn_loop_ui_plan.md`, `docs/build/phase_c_plan.md`
- 설계 원천: `docs/design/스토리_태엽인간_v0.3.md` 외
- 웹 export 실측: `docs/web-export.md` · 파이프라인 규약: `docs/conventions.md`, `docs/command-catalog.md`
