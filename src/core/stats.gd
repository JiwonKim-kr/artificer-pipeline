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
## spec: docs/specs/monsters_and_combat.md (stats.gd 역할).

## 최대 HP(참고·회복 상한용). 데미지로 hp 만 줄고 max_hp 는 불변.
var max_hp: int = 1
## 현재 HP. 0 이하이면 사망(`is_dead`). 데미지가 정확히 반영되도록 하한 클램프는 두지
## 않는다(수용 기준 1: HP 감소량 = 실제 롤 데미지).
var hp: int = 1
## 공격력 하한(포함). 데미지 롤의 최소값.
var attack_min: int = 0
## 공격력 상한(포함). 데미지 롤의 최대값.
var attack_max: int = 0


func _init(p_max_hp: int = 1, p_attack_min: int = 0, p_attack_max: int = 0) -> void:
	max_hp = p_max_hp
	hp = p_max_hp
	attack_min = p_attack_min
	attack_max = maxi(p_attack_max, p_attack_min)


## 데이터 사전에서 Stats 를 만든다(노멀 난이도 몬스터 데이터 등). 키:
## `hp`·`attack_min`·`attack_max`. 값의 출처는 항상 데이터(코드 상수 금지).
static func from_data(data: Dictionary) -> Stats:
	return Stats.new(
		int(data.get("hp", 1)),
		int(data.get("attack_min", 0)),
		int(data.get("attack_max", 0)),
	)


## 데미지를 HP 에서 차감하고 실제 적용량을 돌려준다. 하한 클램프 없음
## (HP 는 음수까지 내려갈 수 있고, 감소량은 항상 정확히 `amount`).
func take_damage(amount: int) -> int:
	hp -= amount
	return amount


## HP 가 0 이하이면 사망.
func is_dead() -> bool:
	return hp <= 0
