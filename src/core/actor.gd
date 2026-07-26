class_name Actor
extends Node2D
## 그리드 위 개체의 공통 기반 — 승탑자(Player)·몬스터(Monster)의 부모.
##
## 셀 좌표(`cell`)·능력치(`stats`)·진영(`faction`)을 들고, 전투가 공통으로 부르는
## **이벤트 훅**(`on_hurt`/`on_death`)을 가상 메서드로 연다. 하위 클래스는 이 훅을
## override 해 자기 시그널을 방출하고, `se attach` 가 그 시그널에 효과음을 붙인다
## (src/core 는 SE 를 모른다 — 브리지가 시그널만 구독).
##
## spec: docs/specs/monsters_and_combat.md (actor.gd 역할).

## 진영. 같은 진영끼리는 비적대, 다른 진영은 적대(범프 공격 대상).
enum Faction { PLAYER, ENEMY }

## 그리드 셀 좌표(월드 좌표 = cell × tile_size). 이동/스폰이 갱신한다.
var cell: Vector2i = Vector2i.ZERO
## 전투 능력치(HP·공격력). configure/spawn 시 데이터로 주입.
var stats: Stats = null
## 진영. 기본 승탑자. 몬스터는 스폰 시 ENEMY 로 설정한다.
var faction: int = Faction.PLAYER


## HP 가 0 이하이면 사망.
func is_dead() -> bool:
	return stats != null and stats.is_dead()


## 다른 개체가 적대 대상인지(진영이 다르면 적대 → 범프 공격 가능).
func is_hostile_to(other: Actor) -> bool:
	return other != null and other.faction != faction


## 피격 이벤트 훅(가상). 데미지가 적용된 직후 combat 가 호출한다.
## 하위 클래스(Player)가 override 해 시그널을 방출한다. 기본은 no-op.
func on_hurt() -> void:
	pass


## 사망 이벤트 훅(가상). 데미지 적용 후 사망이 확정되면 combat 가 호출한다.
## 하위 클래스(Player=게임오버 신호, Monster=제거 신호)가 override 한다. 기본은 no-op.
func on_death() -> void:
	pass
