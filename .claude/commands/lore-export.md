---
description: lore export — canon 컨텍스트로 게임 내 텍스트(댓글 뱅크 등) 생성·검증·반영
argument-hint: <대상: comments 등> [규모/조합 지침]
---

너는 게임 개발 파이프라인의 오케스트레이터다. `lore export` 를 실행한다.
계약: `pipeline/commands/lore.md` 의 `lore export` 절. 규칙: `CLAUDE.md`.

**대상**: `$ARGUMENTS` (비어 있으면 무엇을 export 할지 되묻고 멈춘다. 현 구현 대상: `comments`)

## 1. 생성 (Claude)

1. canon 컨텍스트 확보: `python pipeline/scripts/lore_index.py query --canon lore/canon "<세그먼트|topic 관련 키워드>"`
   — 세그먼트 성향(factions.md), topic 정본(world.md)을 근거로만 쓴다. canon 에 없는 설정을 지어내지 않는다.
2. 현황 파악: `python pipeline/scripts/lore_export.py report` 로 seg×reaction·topic 커버리지를 확인하고
   얇은 셀부터 채운다. **죽은 조합(apathetic×수용/역풍, 그 외 seg×시큰둥)은 생성하지 않는다.**
3. 기존 뱅크(`src/core/data/content_slice.json` comments)를 읽고 어조·레지스터(물타기·진영조롱·
   생계호소·팩트코스프레·냉소 등)를 맞춘다. 중복·유사 반복을 피하고, 슬롯은 `{키워드}{대상}{수치}{집단}` 만.
4. 후보를 `{"comments": [...]}` JSON 파일로 임시 저장한다(스크래치 디렉토리, id 는 `lx_` 접두 snake_case).

## 2. 자동 검증

```
python pipeline/scripts/lore_export.py validate --input <후보.json>
```
오류 0 이 될 때까지 후보를 수정한다. 경고(기존 뱅크 죽은 조합)는 리포트에 포함해 알린다.

## 3. 사람 검수

후보 텍스트(전문)와 반영 전/후 커버리지(`report`)를 제시하고 **명시적 승인**을 요청한다.

## 4. 반영 (승인 후에만)

```
python pipeline/scripts/lore_export.py apply --input <후보.json>
```
반영 후 회귀 확인: `lore_check.py`(정본 모순 없음) + `turn_flow_test.gd`(코어 선택 정상) 통과를 확인하고
`[content]` 접두 커밋으로 남긴다.
