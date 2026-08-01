# 콘텐츠 대량 베이킹 계획 — F1~F16 + 댓글 뱅크

> 브랜치: `content-bake` (game/gireki-sim 기반). 대상: `src/core/data/content_slice.json`(주) + 소폭 코드.
> 원천: `docs/design/스토리_태엽인간_v0.3.md`(§5 사실뱅크·§6 비트시트), `태엽인간_기사조각_헤드라인_초안_v0.1.md`,
> 댓글뱅크 시드. 분담(스토리 §10): 씨앗·목소리=사람 / 대량 변주=오프라인 LLM(=이 작업). **최종 톤 검수는 사람.**

## 현재 상태
- 사실: F1·F2·F7·F15·F16(대표) 이관됨. 댓글: 시드 흡수됨(찌라시=의심 reaction 제외).
- 공백: 사실 F3·F4·F5·F6·F8·F9·F10·F11·F12·F13·F14 미이관. **임금(F8) topic 댓글 0건**(c6_balance 지침).

## 증분
| # | 내용 | 위험 | 검증 |
|---|---|---|---|
| **CB1 댓글 확장** | 임금 topic(전 세그·반응) 필수 + 토픽×세그×반응 공백 메우기 + 톤 변주 밀도 | 낮음(순수 콘텐츠, 엔진·밸런스 무영향) | turn_flow·play_test PASS, parity 불변 |
| **CB2 사실 F3~F14 + 8턴 비트시트** | story §5 조각/태그/헤드라인 이관 + 턴별 노출(`turn` 필드 + get_blocks 턴 필터) | 중(가용 사실이 늘어 lean·난이도 변동) | balance_montecarlo 갱신·재확인, c6_balance 갱신 |
| **CB3 검증·재밸런싱** | 전 사실 반영 난이도 곡선 재확인, 필요 시 상수 미세조정 | — | 몬테카를로 + turn_flow |

## 규칙 (개발 가이드 §6 준수)
- 사실: `{topic,title,fragments:[{tag,text}],headlines}` + 옵션 `hidden`/`gated`/`turn`. 태그(유리/불리/중립)는 내부용, UI 비노출.
- 댓글: `{id,seg,reaction,frame,topic,text}`. 선택=seg+reaction 우선, frame/topic 가점, 쿨다운 랜덤(반복방어).
- topic 은 canon 목록만(world.md). F14(요나스반전)→`실업` 매핑(c6_balance).
- 엔진/config 무변경 → parity 골든 불변. 비트시트로 가용 사실이 바뀌면 balance_montecarlo 갱신.

## 진행 순서
CB1(저위험, 즉시 착수) → CB2(사실+비트시트) → CB3(재밸런싱). 각 증분 커밋·검증.
