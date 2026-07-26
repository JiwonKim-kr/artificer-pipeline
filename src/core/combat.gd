class_name Combat
extends Node
## 범프 공격 해석 — 승탑자↔몬스터 공용.
##
## 공격자·피격자를 받아 `rng.roll(공격자 최소, 공격자 최대)` 로 데미지를 뽑고
## 피격자 stats 에 적용한다(방어·회피 없음). 랜덤은 **주입된 시드 스트림(`rng`)**
## 으로만 뽑아 재현 가능하다(수용 기준 8).
##
## **SE code_event 지점**(`on_player_attack`/`on_enemy_hit`)을 시그널 방출 메서드로
## 둔다. 이 스크립트가 씬(scenes/dungeon.tscn::Combat)에 붙은 노드이므로,
## `se attach` 가 그 시그널에 브리지(효과음)를 연결한다 — src/core 는 SE 를 모른다.
## 피격자 쪽 이벤트(승탑자 피해/몬스터 처치)는 피격자 Actor 의 `on_hurt`/`on_death`
## 훅(각 스크립트가 자기 시그널 방출)으로 위임한다.
##
## progression_and_clear(Spec C) 확장: **강타 강화**(승탑자 준비 상태면 범프 데미지를
## 시드 롤 위에 강화)와 **처치 EXP 부여**(승탑자가 몬스터를 처치하면 그 개체의 exp_reward
## 를 처치자에게)를 연결한다. 둘 다 주입 훅(`skill`/`progression`)이며 미주입 시 무영향 —
## Spec A/B 동작을 그대로 보존한다(하위 호환).
##
## spec: docs/specs/monsters_and_combat.md, docs/specs/progression_and_clear.md (combat.gd 역할).

## 승탑자 범프 공격 순간(효과음: se:player_attack 연결 지점).
signal player_attacked
## 몬스터 피격 순간(효과음: se:enemy_hit 연결 지점).
signal enemy_hit

## 데미지 롤에 쓰는 시드 스트림. 던전 런타임이 던전 시드에서 파생해 주입한다.
## (단위 테스트는 고정 시드 Rng 를 직접 주입해 재현성을 검증.)
var rng: Rng = null
## 강타 강화 훅(Spec C, 승탑자 전용). 승탑자의 Skill 을 주입하면 준비된 강타가 이 범프의
## 데미지를 배수/보너스로 강화한다(시드 롤 위에). null 이면 강화 없음 — 하위 호환.
var skill: Skill = null
## 처치 EXP 엔진(Spec C). 주입하면 승탑자가 몬스터를 처치할 때 exp_reward 를 부여한다
## (다중 레벨업 연쇄는 progression 이 처리). null 이면 EXP 부여 없음 — 하위 호환.
var progression: Progression = null


## 범프 공격 1회를 해석한다. attacker 가 defender 를 친다.
## 반환: 이번에 적용된 데미지(테스트/로그용).
##   1) rng 로 [attacker.min, attacker.max] 데미지 롤
##   2) 공격자가 승탑자면 on_player_attack (공격 효과음 지점)
##   3) defender.stats 에 데미지 적용 + defender.on_hurt (피격자 훅)
##   4) 피격자가 몬스터면 on_enemy_hit (몬스터 피격 효과음 지점)
##   5) 피격자가 사망하면 defender.on_death (처치/게임오버 훅)
func resolve_bump(attacker: Actor, defender: Actor) -> int:
	if attacker == null or defender == null or attacker.stats == null or defender.stats == null:
		return 0
	var damage: int = _roll_damage(attacker.stats)

	# 강타(Spec C): 승탑자의 준비된 강타면 이 범프에서 시드 롤 위에 데미지를 강화한다
	# (강화 공격이 성립하는 시점 → 쿨다운 시작). 준비 아님/미주입이면 그대로 반환(무영향).
	if attacker.faction == Actor.Faction.PLAYER and skill != null:
		damage = skill.consume_for_attack(damage)

	if attacker.faction == Actor.Faction.PLAYER:
		on_player_attack()

	defender.stats.take_damage(damage)
	defender.on_hurt()

	if defender.faction == Actor.Faction.ENEMY:
		on_enemy_hit()

	if defender.is_dead():
		# 처치 EXP(Spec C): 승탑자가 몬스터를 처치하면 그 개체의 exp_reward 를 부여한다
		# (다중 레벨업 연쇄는 progression 이 처리). on_death(제거) 전에 stats 를 읽어 부여.
		if progression != null and attacker.faction == Actor.Faction.PLAYER \
				and defender.faction == Actor.Faction.ENEMY:
			progression.add_exp(attacker.stats, defender.stats.exp_reward)
		defender.on_death()

	return damage


## [최소, 최대] 폐구간 데미지 롤. rng 미주입 시 최소값으로 안전 동작(무시드 randi 금지).
func _roll_damage(attacker_stats: Stats) -> int:
	if rng == null:
		return attacker_stats.attack_min
	return rng.roll(attacker_stats.attack_min, attacker_stats.attack_max)


## 승탑자 공격 효과음 지점(se:player_attack). se attach 가 이 시그널에 붙는다.
func on_player_attack() -> void:
	player_attacked.emit()


## 몬스터 피격 효과음 지점(se:enemy_hit). se attach 가 이 시그널에 붙는다.
func on_enemy_hit() -> void:
	enemy_hit.emit()
