---
track: play
name: phase_c_turn_progression
title: Phase C1 — 다중 턴 루프 + 승/패 + 엔딩
---

- **status**: approved

# 목적 (goal)
1턴 슬라이스를 **완주 가능한 다중 턴 게임**으로 확장한다: 턴 진행, maxTurns 도달 판정, 승/패,
엔딩 3종(성공/실패/발각파탄). 압박·분기·엔딩4종·콘텐츠 확장은 Phase C 후속 증분.

# 동작
- 발행 = 1턴 진행(`model.turn++`). 턴 카운터 `N / maxTurns` 표시.
- 매 발행 후 종료 판정(우선순위): 발각 2회 이상 → **발각파탄** / 부동층 ≥ winThreshold → **성공** /
  turn ≥ maxTurns → **실패** / 그 외 → 진행.
- 종료 시 엔딩 화면(제목+문구) 표시, 발행 비활성.
- `maxTurns`·`winThreshold`·`target`은 `opinion_config.json`(mission)에서 읽는다(단일 출처).
- 콘텐츠는 대표 사실(현행 F1·F2)로 매 턴 제공(턴별 비트시트 콘텐츠는 C2).

# 대상 파일
- `src/core/turn_manager.gd` — `max_turns`, 종료 판정(`_check_ending`), publish 반환 확장(turn/over/ending).
- `src/ui/main.gd` — 턴 카운터, 엔딩 오버레이, 발행 흐름(종료 시 비활성).
- `pipeline/tests/turn_flow_test.gd` — 다중 턴·엔딩 검증.

# 수용 기준
1. maxTurns 회 발행 시 `over=true`, `ending ∈ {성공, 실패, 발각파탄}`.
2. 부동층이 winThreshold 도달 시 즉시 **성공** 엔딩.
3. 발각 2회 누적 시 **발각파탄** 엔딩.
4. 종료 후 발행 버튼 비활성. play_test PASS, parity 불변.

# 후속 (Phase C)
- C2 콘텐츠(F1~F16·댓글, 대량은 사용자 베이킹) · C3 압박+배신엔딩 · C4 분기(F15/F16) ·
  C5 엔딩4종+후일담 · C6 maxTurns 밸런싱·topic 정리.
