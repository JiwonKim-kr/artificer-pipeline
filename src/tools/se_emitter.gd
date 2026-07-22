class_name SeEmitter
extends AudioStreamPlayer
## 범용 SE 브리지 — 지정 노드의 지정 시그널이 발생하면 stream 을 재생한다.
##
## `se attach`(pipeline/scripts/se_attach.py)가 씬에 삽입하는 연결 장치다.
## src/core/ 게임 로직은 SE 를 전혀 몰라도 되고(수정 금지 영역), 이 노드가
## `_ready` 에서 시그널을 구독하는 것으로 연결이 완성된다.
##
## 장르·이벤트 하드코딩 금지(CLAUDE.md/HANDOFF §6-3): 어떤 노드의 어떤 시그널에
## 붙을지(target_path/signal_name)와 무엇을 재생할지(stream)는 전부 씬 데이터
## (매니페스트 requested_by 에서 유도)로 주입된다. 이 스크립트는 특정 씬/게임을
## 참조하지 않는 범용 코드다.

## 시그널을 가진 노드 경로 (기본: 부모 — attach 가 시그널 소유 노드의 자식으로 삽입)
@export var target_path: NodePath = NodePath("..")
## 구독할 시그널 이름 (예: &"step_completed")
@export var signal_name: StringName = &""

func _ready() -> void:
	if signal_name == &"":
		push_warning("SeEmitter: signal_name 미지정 — 연결을 생략합니다 (%s)" % get_path())
		return
	var target: Node = get_node_or_null(target_path)
	if target == null:
		push_warning("SeEmitter: 대상 노드를 찾을 수 없음: %s (%s)" % [target_path, get_path()])
		return
	if not target.has_signal(signal_name):
		push_warning("SeEmitter: '%s' 에 시그널 '%s' 이 없음" % [target.name, signal_name])
		return
	# 시그널 인자 수와 무관하게 동작: 인자를 unbind 로 버리고 재생만 한다.
	var argc: int = _signal_argument_count(target, signal_name)
	var handler: Callable = Callable(self, &"_on_event")
	if argc > 0:
		handler = handler.unbind(argc)
	target.connect(signal_name, handler)

## 대상 노드 시그널의 선언 인자 수를 조회한다 (unbind 용).
func _signal_argument_count(target: Node, p_signal: StringName) -> int:
	for info: Dictionary in target.get_signal_list():
		if StringName(str(info.get("name", ""))) == p_signal:
			var args: Array = info.get("args", [])
			return args.size()
	return 0

func _on_event() -> void:
	play()
