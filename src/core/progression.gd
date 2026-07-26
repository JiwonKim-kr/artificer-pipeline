class_name Progression
extends RefCounted
## EXP 곡선 · 레벨업 판정 — 순수 로직(테스트 용이, 씬/전역 상태 무의존).
##
## 승탑자의 경험치 누적 → 레벨업을 처리한다. **임계치(EXP 곡선)와 레벨당 증가치·회복
## 정책은 전부 노멀 데이터**(`NORMAL_PROGRESSION` 딕셔너리, 필요 시 주입 오버라이드)이며
## 로직에 밸런스 상수를 박지 않는다(CLAUDE.md). `add_exp` 는 EXP 를 더한 뒤 임계치를
## 넘는 동안 **다중 레벨업을 연쇄**로 정확히 처리하고(잉여 EXP 이월), 레벨업마다 Stats
## 에 성장을 적용하고 `leveled_up` 을 방출한다. Stats(상태)와 분리된 순수 엔진이라
## `Progression.new()` 로 만들어 단위 테스트할 수 있다.
##
## spec: docs/specs/progression_and_clear.md (progression.gd 역할, 수용 기준 1·2).

## 노멀 난이도 성장 데이터(밸런스의 단일 출처 — 코드 로직에 상수 금지).
##  · exp_base / exp_step: 다음 레벨 임계치 = exp_base + (level-1)*exp_step (완만한 선형 곡선).
##  · *_gain: 레벨업 1회당 최대 HP·공격력 증가치.
##  · heal_to_full: 레벨업 시 최대치까지 회복(서바이벌의 유일한 회복 보상 — spec 2 권장).
const NORMAL_PROGRESSION: Dictionary = {
	"exp_base": 5,
	"exp_step": 5,
	"hp_gain": 5,
	"attack_min_gain": 1,
	"attack_max_gain": 1,
	"heal_to_full": true,
}

## 사용할 성장 데이터. 기본은 노멀. 테스트/난이도가 다른 곡선을 주입할 수 있다.
var data: Dictionary = NORMAL_PROGRESSION


func _init(p_data: Dictionary = {}) -> void:
	if not p_data.is_empty():
		data = p_data


## `level` 에서 다음 레벨로 오르기 위해 필요한 누적 EXP 임계치(데이터 기반 곡선).
## 항상 1 이상을 보장해 잘못된 데이터로도 무한 루프가 나지 않게 한다.
func exp_to_next(level: int) -> int:
	var base: int = int(data.get("exp_base", 5))
	var step: int = int(data.get("exp_step", 5))
	return maxi(1, base + maxi(0, level - 1) * step)


## `stats` 에 EXP 를 더하고 임계치를 넘는 동안 레벨업을 연쇄 처리한다.
## 레벨업마다: 임계치만큼 EXP 차감(잉여 이월) → level +1 → 데이터 증가치로 성장 적용
## (최대 HP·공격력 + 회복 정책) → `stats.leveled_up(new_level)` 방출.
## 반환: 이번 호출에서 일어난 레벨업 횟수(0 = 레벨업 없음).
func add_exp(stats: Stats, amount: int) -> int:
	if stats == null or amount <= 0:
		return 0
	stats.exp += amount
	var levels: int = 0
	while stats.exp >= exp_to_next(stats.level):
		var need: int = exp_to_next(stats.level)
		stats.exp -= need
		stats.level += 1
		levels += 1
		stats.apply_growth(
			int(data.get("hp_gain", 0)),
			int(data.get("attack_min_gain", 0)),
			int(data.get("attack_max_gain", 0)),
			bool(data.get("heal_to_full", true)),
		)
		stats.leveled_up.emit(stats.level)
	return levels
