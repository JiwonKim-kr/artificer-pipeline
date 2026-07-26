class_name MonsterAi
extends RefCounted
## 그리디 접근 AI — 순수 함수. 경로탐색(A*) 없음(spec 범위 밖).
##
## 대상(승탑자) 방향으로 그리드 한 칸 이동 후보를 판정한다. 큰 축(거리 차가 큰
## 축)을 우선하고, 막히면 다른 축으로 우회하며, 둘 다 막히면 대기(ZERO)한다.
## 이동 가능 여부(벽·다른 개체 회피)는 호출자가 준 술어(`is_free: Callable`)로만
## 판단해 이 로직을 씬/그리드에서 독립시킨다 → 단위 테스트 용이(수용 기준 4).
##
## spec: docs/specs/monsters_and_combat.md (monster_ai.gd 역할).

## 4방향 직교 이웃(결정적 순서).
const ORTHO: Array[Vector2i] = [
	Vector2i(1, 0), Vector2i(-1, 0), Vector2i(0, 1), Vector2i(0, -1)
]


## 맨해튼 거리(직교 스텝 수). 인접(공격) 판정에 사용.
static func manhattan(a: Vector2i, b: Vector2i) -> int:
	return absi(a.x - b.x) + absi(a.y - b.y)


## 체비쇼프 거리(임의 방향 최대 축 거리). aggro 범위 판정에 사용.
static func chebyshev(a: Vector2i, b: Vector2i) -> int:
	return maxi(absi(a.x - b.x), absi(a.y - b.y))


## 직교 인접(맨해튼 == 1)인지 — 범프 공격 가능 위치.
static func is_adjacent(a: Vector2i, b: Vector2i) -> bool:
	return manhattan(a, b) == 1


## from → target 방향으로 선호되는 직교 스텝 후보를 순서대로 반환한다.
## 거리 차가 큰 축을 먼저, 동률이면 x 축을 먼저(결정적 tie-break). 이미 정렬된
## 축(차이 0)은 후보에서 제외. 최대 2개.
static func ranked_steps(from: Vector2i, target: Vector2i) -> Array[Vector2i]:
	var dx: int = target.x - from.x
	var dy: int = target.y - from.y
	var step_x: Vector2i = Vector2i(signi(dx), 0)
	var step_y: Vector2i = Vector2i(0, signi(dy))
	var steps: Array[Vector2i] = []
	if absi(dx) >= absi(dy):
		if dx != 0:
			steps.append(step_x)
		if dy != 0:
			steps.append(step_y)
	else:
		if dy != 0:
			steps.append(step_y)
		if dx != 0:
			steps.append(step_x)
	return steps


## from 에서 target 으로 한 칸 접근하는 스텝을 고른다. 선호 후보 중 `is_free`
## (호출자 술어: 목적 셀이 보행 가능 + 비점유)가 참인 첫 스텝을 반환. 모두
## 막히면 Vector2i.ZERO(대기).
## is_free: Callable(cell: Vector2i) -> bool
static func choose_move(from: Vector2i, target: Vector2i, is_free: Callable) -> Vector2i:
	for step in ranked_steps(from, target):
		if bool(is_free.call(from + step)):
			return step
	return Vector2i.ZERO
