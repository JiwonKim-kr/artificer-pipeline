class_name Skill
extends RefCounted
## 강타 (Power Strike) — 데모의 유일한 액티브 스킬. 순수 로직 상태기계.
##
## canon 의 "조건 만족 시 스킬 획득"을 최소 형태로 구현한다. 획득 레벨·데미지 배수/보너스·
## 쿨다운은 **노멀 데이터**(`NORMAL_SKILL`)이며 로직에 상수를 박지 않는다(CLAUDE.md).
##
## 흐름: 특정 레벨 도달 시 `check_acquire` 로 **획득**(그 전에는 `activate` 무효) →
## 스킬 입력으로 `activate`(턴 미소비 모드 토글, "강타 준비" = armed) → 다음 범프 공격이
## 성립할 때 combat 이 `consume_for_attack` 을 불러 **데미지를 배수/보너스로 강화**(시드
## RNG 롤 위에 적용)하고 그 순간 **쿨다운 시작**(N턴). 쿨다운은 `tick_cooldown` 으로
## 턴마다 1 감소(게임 컨트롤러가 turn_manager 의 turn_advanced 에 연결). 쿨다운 중·획득
## 전에는 재활성화 불가. 강화 공격이 성립하면 `skill_used` 를 방출한다(상태창·SE 앵커).
##
## Node/씬 비의존 순수 로직이라 `Skill.new()` 로 만들어 획득·강화·쿨다운을 직접 단위
## 테스트할 수 있다(수용 기준 11·12).
## spec: docs/specs/progression_and_clear.md (skill.gd 역할).

## 강화 공격이 실제로 성립한 순간 방출(쿨다운 시작 + 데미지 강화). "강타 발동" 효과음의
## code_event 연결점을 게임 컨트롤러가 관측해 중계한다(src/core 는 SE 를 모른다).
signal skill_used

## 노멀 난이도 강타 데이터(밸런스의 단일 출처 — 코드 로직에 상수 금지).
##  · acquire_level: 이 레벨에 도달하면 강타 획득.
##  · damage_mult / damage_bonus: 강화 데미지 = round(기본 롤 × mult) + bonus.
##  · cooldown: 강화 공격 성립 후 재활성화까지 대기 턴 수.
const NORMAL_SKILL: Dictionary = {
	"acquire_level": 2,
	"damage_mult": 2.0,
	"damage_bonus": 0,
	"cooldown": 5,
}

## 사용할 강타 데이터. 기본은 노멀. 테스트/난이도가 오버라이드할 수 있다.
var data: Dictionary = NORMAL_SKILL

## 강타를 획득했는가(획득 전에는 활성화 불가).
var acquired: bool = false
## "강타 준비" 상태 — 다음 범프 공격이 강화된다(활성화로 켜짐, 강화 공격 성립으로 꺼짐).
var armed: bool = false
## 남은 쿨다운 턴 수(0 이면 재활성화 가능). 강화 공격 성립 시 cooldown_max 로 설정.
var cooldown: int = 0


func _init(p_data: Dictionary = {}) -> void:
	if not p_data.is_empty():
		data = p_data


func acquire_level() -> int:
	return int(data.get("acquire_level", 2))


func cooldown_max() -> int:
	return int(data.get("cooldown", 5))


## 레벨이 획득 조건에 도달했으면 강타를 획득한다. 이번 호출에서 **새로** 획득했으면 true.
## (레벨업마다 게임 컨트롤러가 현재 레벨로 호출한다.)
func check_acquire(level: int) -> bool:
	if not acquired and level >= acquire_level():
		acquired = true
		return true
	return false


## 지금 활성화(강타 준비)할 수 있는가 — 획득했고, 이미 준비 상태가 아니며, 쿨다운이 없을 때.
func can_activate() -> bool:
	return acquired and not armed and cooldown <= 0


## 강타를 활성화한다(턴 미소비 — 호출자가 턴을 소비하지 않는다). 조건 불충족이면 false.
func activate() -> bool:
	if not can_activate():
		return false
	armed = true
	return true


## 범프 공격이 성립하는 순간 combat 이 기본 롤 데미지를 넘겨 호출한다.
##  · 준비(armed) 상태가 아니면 기본 데미지를 그대로 돌려준다(비강화, 부작용 없음).
##  · 준비 상태면 강화 데미지 = round(기본 × mult) + bonus 를 돌려주고, armed 해제 +
##    쿨다운 시작(강화 공격이 실제로 성립한 시점) + `skill_used` 방출.
func consume_for_attack(base_damage: int) -> int:
	if not armed:
		return base_damage
	armed = false
	cooldown = cooldown_max()
	var mult: float = float(data.get("damage_mult", 1.0))
	var bonus: int = int(data.get("damage_bonus", 0))
	var enhanced: int = int(round(float(base_damage) * mult)) + bonus
	skill_used.emit()
	return enhanced


## 쿨다운을 1 감소(하한 0). 게임 컨트롤러가 turn_manager.turn_advanced(턴 경계)에 연결한다.
func tick_cooldown() -> void:
	if cooldown > 0:
		cooldown -= 1


## 새 런 시작(재시작) 시 강타 상태를 초기화한다 — 미획득·비준비·쿨다운 0.
func reset() -> void:
	acquired = false
	armed = false
	cooldown = 0
