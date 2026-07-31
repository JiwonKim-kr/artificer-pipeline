# Phase B UI/씬 구현 계획 — 1턴 수직 슬라이스

> spec: `docs/specs/turn_loop_vertical_slice.md` (approved) · 브랜치: `turn-loop`
> 코어 엔진(rng·opinion_model·config·lever_tuning)은 커밋 `b9c3341`에서 이식·검증 완료.
> 이 문서는 그 위에 얹을 **UI/씬 층의 구현 계획**이다. 단계별로 진행·갱신한다.

## 1. 씬 트리 (`scenes/main.tscn`, 루트 `Main`)

```
Main (Control, 풀 화면)
├─ DeskView (Control)                     ← 데스크 상태(정적 배경)
│  ├─ Background (TextureRect)            ← art:ui/main/desk_bg (placeholder→실제 배경)
│  └─ MonitorButton (Button, 투명)        ← 모니터 화면 영역, 클릭 시 전환
├─ ScreenState (Control, visible=false)   ← 스크린 상태(줌 인 후)
│  ├─ ScreenOS (Control) [screen_os.gd]   ← 레트로 OS 데스크톱(창 관리)
│  │  ├─ InformantWindow (Panel)          ← F1·F2 전체 조각(유·불리)
│  │  ├─ EditorWindow (Panel)             ← 조각 취사 + 프레임/톤/채널 + 과장 + 발행
│  │  ├─ CommentsWindow (Panel)           ← 발행 후 세그먼트별 댓글
│  │  └─ OpinionGauge (Control)           ← 부정확 아날로그 바늘
│  ├─ BackBufferCopy (copy_mode=Viewport) ← web-export.md 검증 노드 순서
│  └─ CrtOverlay (ColorRect, CRT 셰이더, mouse_filter=IGNORE)
└─ TurnManager (Node) [turn_manager.gd]   ← 로직 브릿지(엔진↔UI)
```

## 2. 핵심 설계 결정
- **CRT = 스크린 상태 전체화면 1패스**: `[UI] → BackBufferCopy → CrtOverlay`(web-export.md 검증 구성 재사용). 데스크 상태엔 CRT 없음(정적 아트).
- **입력 정합**: `CrtOverlay.mouse_filter = IGNORE` → 클릭이 아래 UI로 통과. 배럴 왜곡은 시각/히트박스가 어긋나므로 **곡률을 약하게** 유지.
- **전환**: `MonitorButton` 클릭 → `Tween` 줌 인 → `ScreenState` 표시(`desk_view.gd`). 시점 전환 없음(정면 고정).
- **창**: `Panel` + `os_window.gd`(타이틀바 드래그, 마우스 전용). **MVP는 고정 배치**, 드래그는 여유 시 폴리시.
- **입력 = 마우스/클릭 전용** (자유 텍스트 없음).

## 3. 데이터·로직 배선
- `EditorWindow` 레버 선택 → `TurnManager.publish(choices)`:
  - frame/tone/channel 그대로, **δ = `lever_tuning.json`**(누락 불리 조각 수·재배치·과장) → `article.distortion`.
  - `OpinionModel.step(article)` → 스냅샷.
- 스냅샷 → `CommentsWindow`(세그먼트 micro 반응 기반 댓글 선택) + `OpinionGauge`(tv_macro→바늘, 느린 갱신).
- `content_slice.json`: F1·F2 조각(유/불리/중립)+프레임별 헤드라인, 세그먼트·반응별 댓글(댓글뱅크 시드 발췌).

## 4. project.godot
- `main_scene` 설정됨. **디자인 해상도(16:9, 예 1152×648) + `stretch_mode=canvas_items`**를 `[display]`에 추가(spec 미결 확정). JiwonKim의 `[rendering]` 미변경, 섹션만 추가.

## 5. placeholder + 매니페스트
- `placeholder_gen.py`(`PYTHONUTF8=1`로 cp949 회피) + `manifest.py`로 3종 등록:
  `art:ui/main/desk_bg` · `art:ui/window/frame` · `art:ui/gauge/opinion_needle`.
- 실제 배경(Gemini)은 16:9 최종 + review 후 reskin 교체(그때까지 placeholder).

## 6. 증분 & 검증
| 증분 | 내용 | 검증 |
|---|---|---|
| **2a 로직/데이터** | `turn_manager.gd` + `content_slice.json` | 헤드리스 `turn_flow_test.gd`(레버→δ→step 1턴, 부동층 상승·δ 산출 단정) |
| **2b 씬/비주얼** | `main.tscn` + OS 창 + CRT 셰이더 + desk_view/screen_os/os_window + placeholder/매니페스트 + project.godot | `play_test`(임포트·스모크·매니페스트) + `--screenshot` 비-단색 렌더 |

## 7. 리스크
- CRT 배럴 왜곡 vs 클릭 정합 → 곡률 약하게.
- 1턴 변화폭 작음(부동층 +약0.02) → 게이지 체감 미미(검증 목적엔 충분, 데모용 2~3턴 확장은 후속).
- 실제 배경 3:2 → 16:9 재작업 필요(아웃페인팅), 그전까지 placeholder.
