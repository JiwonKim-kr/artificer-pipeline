class_name Rng
extends RefCounted
## 시드 기반 RNG 스트림 — `RandomNumberGenerator` 래핑.
##
## 전투·스폰의 랜덤은 **전역 `randi()`(무시드)를 절대 쓰지 않고** 이 스트림으로만
## 뽑는다. 같은 시드로 만든 스트림은 같은 순서로 같은 값을 낸다 → 재현성
## (monsters_and_combat spec: 결정성, 수용 기준 8). 스트림은 던전 시드에서 파생한다
## (예: `Rng.new(dungeon_seed + 상수)`) — 전투용·스폰용을 별도 상수로 분리해
## 서로 간섭하지 않게 한다.
##
## spec: docs/specs/monsters_and_combat.md (rng.gd 역할).

var seed_value: int = 0
var _rng: RandomNumberGenerator = null


func _init(p_seed: int = 0) -> void:
	seed_value = p_seed
	_rng = RandomNumberGenerator.new()
	_rng.seed = p_seed


## [lo, hi] 폐구간 정수 균등 롤. hi < lo 이면 lo 로 안전 보정.
func roll(lo: int, hi: int) -> int:
	if hi < lo:
		hi = lo
	return _rng.randi_range(lo, hi)


## 스트림을 재시드해 처음 상태로 되돌린다(같은 시드 → 같은 시퀀스 재현).
func reseed(p_seed: int) -> void:
	seed_value = p_seed
	_rng.seed = p_seed
