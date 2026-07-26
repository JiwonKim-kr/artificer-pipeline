class_name Stats
extends RefCounted
## 전투 능력치 컴포넌트 — 승탑자·몬스터 공용.
##
## HP 와 공격력 범위(최소~최대)를 들고, 데미지 적용(`take_damage`)과 사망 판정
## (`is_dead`)만 책임진다. 방어·회피·크리티컬은 이 spec 범위 밖 → 피격자 HP 에서
## 데미지만 차감한다(monsters_and_combat spec: 전투). 능력치 **값 자체는** 이 클래스에
## 박지 않고 데이터(monster.gd 의 노멀 데이터 사전 등)에서 주입받는다 —
## 장르/밸런스 상수 하드코딩 금지(CLAUDE.md).
##
## progression_and_clear(Spec C) 확장: **레벨·EXP·경험치 보상** 필드와 레벨업 시 스탯
## 증가·HP 회복 적용(`apply_growth`)을 더한다. 레벨업 판정(임계치·연쇄)은 순수 로직인
## `progression.gd` 가 담당하고, 이 컴포넌트는 그 결과(레벨·EXP·능력치)를 담는 상태다.
## 레벨업 순간 `leveled_up` 시그널을 낸다(UI 갱신·SE 앵커 연결점) — 값은 progression 이
## 채운다. 승탑자만 성장하며, 몬스터의 `exp_reward` 는 처치 시 처치자에게 넘어간다.
##
## spec: docs/specs/monsters_and_combat.md, docs/specs/progression_and_clear.md (stats.gd 역할).

## 레벨업이 성립한 순간(잉여 이월·스탯 증가·회복 적용 후) 방출. 인자는 새 레벨.
## progression.add_exp 가 레벨업마다 1회씩 낸다. 상태창 갱신·레벨업 SE(게임 컨트롤러가
## 관측해 code_event 로 중계)의 연결점이다.
signal leveled_up(new_level: int)

## 최대 HP(참고·회복 상한용). 데미지로 hp 만 줄고 max_hp 는 불변.
var max_hp: int = 1
## 현재 HP. 0 이하이면 사망(`is_dead`). 데미지가 정확히 반영되도록 하한 클램프는 두지
## 않는다(수용 기준 1: HP 감소량 = 실제 롤 데미지).
var hp: int = 1
## 공격력 하한(포함). 데미지 롤의 최소값.
var attack_min: int = 0
## 공격력 상한(포함). 데미지 롤의 최대값.
var attack_max: int = 0

## 현재 레벨(성장). 승탑자만 실제로 오르며, 몬스터는 1 고정.
var level: int = 1
## 현재 레벨에서 다음 레벨까지 누적한 경험치(잉여는 레벨업 시 이월). 임계치는 progression.
var exp: int = 0
## 이 개체를 처치했을 때 처치자에게 주는 경험치 보상(종류별 노멀 데이터). 승탑자는 0.
var exp_reward: int = 0


func _init(p_max_hp: int = 1, p_attack_min: int = 0, p_attack_max: int = 0) -> void:
	max_hp = p_max_hp
	hp = p_max_hp
	attack_min = p_attack_min
	attack_max = maxi(p_attack_max, p_attack_min)


## 데이터 사전에서 Stats 를 만든다(노멀 난이도 몬스터 데이터 등). 키:
## `hp`·`attack_min`·`attack_max`·(선택)`exp_reward`. 값의 출처는 항상 데이터(코드 상수 금지).
static func from_data(data: Dictionary) -> Stats:
	var s := Stats.new(
		int(data.get("hp", 1)),
		int(data.get("attack_min", 0)),
		int(data.get("attack_max", 0)),
	)
	s.exp_reward = int(data.get("exp_reward", 0))
	return s


## 데미지를 HP 에서 차감하고 실제 적용량을 돌려준다. 하한 클램프 없음
## (HP 는 음수까지 내려갈 수 있고, 감소량은 항상 정확히 `amount`).
func take_damage(amount: int) -> int:
	hp -= amount
	return amount


## HP 가 0 이하이면 사망.
func is_dead() -> bool:
	return hp <= 0


## 레벨업 1회분의 성장을 적용한다(progression 이 임계치 판정 후 레벨마다 호출).
## 최대 HP·공격력(최소/최대)을 데이터 증가치만큼 올리고, 회복 정책이 참이면 최대치까지
## 회복한다(서바이벌에서 성장이 유일한 회복 보상 — spec 2). 증가치·회복 여부는 데이터에서
## 온다(코드 상수 금지). `level`·`exp` 이월은 progression 이 관리한다.
func apply_growth(hp_gain: int, attack_min_gain: int, attack_max_gain: int, heal_to_full: bool) -> void:
	max_hp += hp_gain
	attack_min += attack_min_gain
	attack_max = maxi(attack_max + attack_max_gain, attack_min)
	if heal_to_full:
		hp = max_hp
