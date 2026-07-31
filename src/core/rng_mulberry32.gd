class_name RngMulberry32
extends RefCounted
## sim/opinion-model/opinion-model.mjs 의 makeRng(mulberry32) 비트-정확 이식.
## JS 의 32비트 정수 연산(|0, >>>, Math.imul)을 GDScript(64비트)에서 마스킹·에뮬레이션.
## spec: docs/specs/turn_loop_vertical_slice.md

var _a: int  # 32비트 unsigned 상태 (0 .. 2^32-1)

func _init(seed: int = 1) -> void:
	_a = seed & 0xFFFFFFFF

## JS Math.imul: 두 32비트 정수 곱의 하위 32비트. int64 오버플로 회피 위해 16비트 분할.
static func _imul(x: int, y: int) -> int:
	x &= 0xFFFFFFFF
	y &= 0xFFFFFFFF
	var xl: int = x & 0xFFFF
	var xh: int = (x >> 16) & 0xFFFF
	var yl: int = y & 0xFFFF
	var yh: int = (y >> 16) & 0xFFFF
	var low: int = xl * yl
	var mid: int = (xh * yl + xl * yh) & 0xFFFF  # <<16 후 하위 32비트만 남으므로 하위 16비트로 충분
	return (low + (mid << 16)) & 0xFFFFFFFF

## 테스트 대조용: 부동소수 division 이전의 uint32 (bit-exact 판정용).
func next_uint32() -> int:
	_a = (_a + 0x6D2B79F5) & 0xFFFFFFFF
	var t: int = _imul(_a ^ (_a >> 15), 1 | _a) & 0xFFFFFFFF
	t = ((t + _imul(t ^ (t >> 7), 61 | t)) & 0xFFFFFFFF) ^ t
	t &= 0xFFFFFFFF
	return (t ^ (t >> 14)) & 0xFFFFFFFF

## [0, 1) 실수. JS makeRng() 반환과 동일.
func next() -> float:
	return float(next_uint32()) / 4294967296.0
