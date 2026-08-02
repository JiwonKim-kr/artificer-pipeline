# 「태엽 인간」 인수인계 — 2026-08-02 (재설계 P1~P3 + 사운드 + 댓글 리얼리티)

> 대상: 이어서 작업할 팀원. 기준 브랜치 `game/gireki-sim` (origin 반영 완료, HEAD = 병합 `20ce953`).
> 구조·확장은 [gireki_dev_guide.md](gireki_dev_guide.md), 제출 체크리스트는 [playtest_checklist.md](playtest_checklist.md), 재설계 명세는 [../specs/redesign_v0.4.md](../specs/redesign_v0.4.md) 참고.
> 이 문서 = "이번에 뭘 했고 / 왜 구조가 바뀌었고 / 다음에 뭐가 남았는지".

---

## 1. 이번에 본체(`game/gireki-sim`)에 들어간 것 — 전부 push 완료

**아트 (JiwonKim, 이미 병합됨)**: 디젤펑크 컨셉→lock→gen→reskin(desk_bg·window frame·게이지) + CRT 레이아웃 수정 5건.

**사운드**
- 효과음 5종(jsfxr 절차생성): monitor_on·publish(타자기)·detected(발각)·ending·clue_found. `se_emitter` 브리지가 시그널 구독(코어 무지). 재현 spec `pipeline/se_specs/`.
- **SE/BGM 오디오 버스**(`default_bus_layout.tres`) + CRT OS 우상단 **「소리 설정」 버튼**(효과음·배경음 슬라이더, `user://settings.cfg` 저장). BGM 버스는 배경음 추가 대비 미리 만들어둠.

**재설계 v0.4 (P1~P3, UI-only — `src/core` 불변)** — 아래 §2 이유
- **P1 정보 시간축**: 정보원 패널이 '오늘 입수'만, 턴마다 갱신.
- **P2 기사 렌더**: 발행 시 「헤드라인」 + 본문 카드(상태줄 대체). 헤드라인은 fact `headlines[논조]`.
- **P3 정보 선별**: 정보원=오늘만 + **「받은 자료」 오버레이**로 과거 정보 날짜별 열람·"이 기사에 넣기"(원고=오늘+끌어온 것, 턴마다 초기화).

**폴리시**: 창 텍스트 프레임 밖 삐짐 수정(content_margin 실측), 데스크 복귀(← 버튼·ESC), 댓글 창 스크롤.

**댓글 리얼리티**
- 뱅크 **51→87** (실제 정치 댓글 어조: 물타기·진영조롱·생계호소·팩트코스프레·냉소·whataboutism. 세그먼트별 목소리). `src/core/data/content_slice.json` `comments`.
- 댓글 작성자 **랜덤 닉네임**(main.gd `HANDLE_POOLS` 세그먼트별 디젤펑크 톤 + 숫자 접미) — 기존 `[seg id]` 반복 대체.

검증: 각 단계 import·`opinion_parity_test`·`turn_flow_test`·smoke 전부 PASS. 엔진(opinion_model) 불변.

---

## 2. 왜 게임 구조가 처음과 달라졌나 (플레이테스트 반영)

"정보가 한꺼번에 다 뜨고 재활용되는 느낌" 피드백 → 진단: `content_slice.json`의 fact에 `turn`·`headlines`가 이미 있는데 **정보원 패널이 전체를 1회만 렌더**하고 헤드라인 미사용이었음(get_blocks 턴 게이팅은 이미 정상). → **원 설계(스토리 v0.3 §2·§6 비트시트)로 되돌리는 방향**으로 P1~P3을 UI만 고쳐 구현. 창 배치·아트는 보존.

**결정된 재설계 방향**: 경제=라이트 / 여론=바늘 게이지 유지(부정확 미학) / 왜곡=취사+재배치 / 거리 채널·과장=보류.

---

## 3. 남은 작업 (이어받을 사람 — 우선순위 순)

| 항목 | 내용 | 코어 영향 |
|---|---|---|
| **플레이스홀더 치환** | 기존 댓글 11개의 `{대상}`·`{수치}`·`{키워드}`가 런타임 치환 없이 **문자 그대로 노출** 중. 기사 태그에서 슬롯 채우는 로직 필요(설계 `댓글뱅크_설계_v0.1.md` §4) | main.gd/turn_manager |
| **Phase 4 기사 본문 prose화** | 본문이 블럭 나열이라 몰입 저하. fact×프레임 **authored 본문**(headlines처럼) 데이터화 → 조립. 스토리 §10 "본문 확장=베이킹". + 기사 포커스 제약 | 데이터 위주 |
| **Phase 5 라이트 경제** | 의뢰 수락→소액 예산→정보원 구매(취사) 제약. **`src/core` 수정이라 spec 먼저**(CLAUDE.md 게이트) | src/core |

**제출(8/10) 관련 — 사람만 가능** (playtest_checklist §B):
- 아트 `review` 승인(desk_bg 등 generated 3종) · **Pages 배포**(Settings→Pages→GitHub Actions, public 필요) → 실제 URL로 심사자 경험 재현
- 게임 감각 완주 체감 · **AI 활용 기술 문서**(2계층 아키텍처 — 이 프로젝트 승부처)

---

## 4. 이어서 작업하는 법
- **새 브랜치**를 `game/gireki-sim`에서 파서 진행(예: `content/article-prose`, `feature/economy`). 완료 시 PR/병합.
- **`src/core` 수정은 승인된 spec 없이 금지**(CLAUDE.md). Phase 5·플레이스홀더는 spec부터.
- 매 단계 게이트 유지: `opinion_parity_test`(엔진 바꾸면 골든 재생성) · `turn_flow_test` · `play_test.py`(스모크). opinion_config 변경 시 `dump_opinion_golden.mjs` 재실행.
- Windows 로컬: `PYTHONUTF8=1`, 로컬 Godot 4.5.1이면 아트 PNG `ERR_FILE_CORRUPT` 뜨나 무해(정본 CI 4.6.x, main.gd null 폴백).
- 커밋 접두사: `[play build]`/`[content]`/`[play spec]`/`[docs]`.
