# 「태엽 인간」 작업 진행 상황 + 다음 작업 (다른 기기에서 이어받기용)

> 작성 2026-08-02 · 기준 브랜치 `game/gireki-sim` (origin 반영 완료).
> 이 문서 하나 + [gireki_dev_guide.md](gireki_dev_guide.md)(구조·확장) 면 다른 기기의 Claude Code 에서 이어서 개발할 수 있다.
> ※ 재설계 v0.4 상세·Phase5 상세는 원래 작성자 로컬 메모리에만 있었음 → 이어받기 위해 이 문서에 요약 포함.

## 0. 이어받는 법 (다른 기기)
```bash
git clone <repo>            # 또는 git pull
git checkout game/gireki-sim   # 게임 본체(모든 작업 통합)
```
- **엔진**: Godot 4.6.x 고정(정본). 로컬 4.5.x 여도 동작하나 임포트/렌더 차이는 CI(4.6.3) 기준. 실행 exe 경로는 기기마다 다름 → `GODOT_BIN` 로 지정.
- **검증 게이트**(엔진 안 건드려도 매번):
  ```bash
  "$GODOT_BIN" --headless --path . --import
  "$GODOT_BIN" --headless --path . --script res://pipeline/tests/opinion_parity_test.gd   # PARITY_RESULT: PASS
  "$GODOT_BIN" --headless --path . --script res://pipeline/tests/turn_flow_test.gd        # TURN_RESULT: PASS
  PYTHONUTF8=1 GODOT_BIN="$GODOT_BIN" python pipeline/scripts/play_test.py                # 스모크
  ```
  Windows 는 python 앞에 `PYTHONUTF8=1`. 로컬 아트 PNG `ERR_FILE_CORRUPT` 는 4.5.x 특성(무해, main.gd null 폴백).
- **규칙**: `src/core`(엔진·turn_manager)는 **승인 spec 없이 수정 금지**(CLAUDE.md). 새 브랜치에서 작업 → `game/gireki-sim` 병합. 커밋 접두사 `[play build]`/`[content]`/`[play spec]`/`[docs]`.

---

## 1. 지금까지 완료 (전부 `game/gireki-sim` 반영·push 완료)

**기반(팀·이전)**: 검증된 여론 엔진(opinion_model 비트-정확 이식 + parity) · 8턴 루프·엔딩 4종·압박·분기(F15/F16) · C6 밸런싱 · 아트(디젤펑크 desk/frame/gauge) · 효과음 5종 + SE/BGM 버스·소리 설정.

**재설계 v0.4 (플레이테스트 반영, UI-only — 엔진 불변)**
- **P1 정보 시간축**: 정보원 패널 = "오늘 입수"만 턴별 표시(전엔 16개 한꺼번에 떴음).
- **P2/P4 기사 렌더**: 발행 시 **「헤드라인」 + prose 본문**(블럭 나열 아님). 16 fact × 프레임별 authored 본문(`content_slice.json` 각 fact `bodies`). 같은 사실도 논조(찬성각/중립/반대각)로 톤이 달라짐.
- **P3 정보 선별**: 정보원=오늘만 + **「받은 자료」 오버레이**로 과거 정보 열람·"이 기사에 넣기"(원고=오늘+끌어온 것, 턴마다 초기화).
- **발행 오버레이 UX**: 기사는 원고 창 인라인이 아니라 **중앙 오버레이**(발행 자동팝 · X 닫기 · 「발행 기사 다시 보기」 버튼 · **< > 로 지난 기사 히스토리 탐색** "T{턴}·N/총").
- **폴리시**: 창 텍스트 삐짐 수정, 오버레이 센터링(grow_direction).

**댓글 리얼리티**
- 뱅크 51→87(실제 정치 댓글 어조: 물타기·진영조롱·생계호소·팩트코스프레·냉소).
- 작성자 **랜덤 닉네임**(세그먼트별 핸들 풀, main.gd `HANDLE_POOLS`).
- **플레이스홀더 치환**: 기존 `{대상}`/`{수치}`/`{키워드}` 리터럴 노출 해결(main.gd `COMMENT_SLOTS`).

핵심 파일: `src/ui/main.gd`(UI 전부), `src/core/data/content_slice.json`(사실·본문·댓글), `src/core/turn_manager.gd`(로직·코어).

---

## 2. 다음 작업 목록

### A. 개발 — Phase 5 라이트 경제 ⭐ (다음 dev, UI-only 가능)
정보원 무료 드립 → **취재비 예산으로 구매**하는 취재 결정. 원 구상 "의뢰→돈→정보원 수급"의 라이트 버전. #4 난이도(무제한 투입)도 완화.
- **루프**: 의뢰 수락→예산 지급 → 매턴 신규 사실이 "제안 목록"(비용 표시) → 예산 내 **구매**로 해금 → 부족 시 취사 압박 → 이월(받은 자료)은 재사용 무료.
- **구현 계층(중요)**: **P1~P4처럼 UI-only 가능** — `get_blocks`(core)는 "제안 풀"(턴 게이팅)로 두고 **main.gd가 예산·구매(`_purchased` 집합)로 게이트**. opinion_model은 발행 included_ids만 받으므로 **parity 0** → **코어 spec 게이트 비해당**.
- **데이터**: fact `cost`(일반 1~2, 특종 F10·F16·F7 은 3~4) + 예산 상수.
- **UI(main.gd)**: 예산 HUD · 정보원 패널에 "제안(미구매) + 구매됨" · 제안 항목 `[구매 N]` 버튼(예산 차감 + `_refresh_informant/_refresh_blocks` 재사용).
- **확정할 결정**: 예산 모델(턴당 정액 추천) · 비용 분포(가치별) · 미구매 처리(누적 구매 가능) · 밸런스(최적 플레이가 예산 내 도달 가능하게 튜닝 → c6 불변).
- **예외**: F15(책상 발견)·F16(F7 개폐)·거리(보류)는 구매 대상 아님.
- **단계**: P5a 데이터+예산HUD → P5b 구매 UI+`_purchased` 게이트 → P5c 밸런스 튜닝.
- (선택) 기사 포커스 제약(#4a): 한 기사에 넣는 사실 수 제한 — 경제와 함께 난이도 조율.

### B. 제출 준비 — 사람만 가능 (마감 8/10, 시간 민감)
- **Pages 배포**: Settings→Pages→Source=GitHub Actions(public 필요) → Actions 에서 `deploy-web` 실행 → **실제 URL** 확보(심사자 경험, 로컬 대체 불가).
- **아트 `review` 승인**: `python3 pipeline/scripts/review.py list` → `approve --id <id>`.
- **AI 활용 기술 문서**: 팀원 담당(인수인계 `gireki_handoff_2026-08-02.md`). 2계층 아키텍처 · "AI 안 쓴 곳"(여론엔진·효과음·밸런싱).
- 시연 영상 · 게임 소개서 · 팀원 역할 기술서.

### C. 보류 (제출 후)
- P3 좌하단 그래프(현 바늘 게이지로 충족) · 거리 채널(순찰 뷰, 댓글뱅크 재활용) · 콘텐츠 추가 베이킹.

---

## 3. 현재 상태 한 줄
`game/gireki-sim` = Phase 1~4 + 댓글 리얼리티 전부 통합·push 완료, 트리 clean, 게이트 PASS. **다음: Phase 5(P5a부터) 또는 배포(#B).**
