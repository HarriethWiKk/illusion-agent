"""SystemOverheadTracker 单元测试。"""
from illusion.services.compact.system_overhead_tracker import SystemOverheadTracker


def test_initial_state_no_measured_value():
    tracker = SystemOverheadTracker()
    assert tracker.tokens is None
    assert tracker.has_measured_value is False


def test_update_from_usage_success():
    tracker = SystemOverheadTracker()
    # api_input_tokens=50000, messages_tokens=25000 → overhead=25000
    ok = tracker.update_from_usage(50000, 25000)
    assert ok is True
    assert tracker.tokens == 25000
    assert tracker.has_measured_value is True


def test_update_from_usage_zero_input_returns_false():
    tracker = SystemOverheadTracker()
    ok = tracker.update_from_usage(0, 1000)
    assert ok is False
    assert tracker.tokens is None


def test_update_from_usage_negative_overhead_returns_false():
    tracker = SystemOverheadTracker()
    # messages > input → overhead < 0
    ok = tracker.update_from_usage(1000, 2000)
    assert ok is False
    assert tracker.tokens is None


def test_update_from_usage_huge_overhead_returns_false():
    tracker = SystemOverheadTracker()
    # overhead > 500000 视为异常
    ok = tracker.update_from_usage(600000, 1000)
    assert ok is False
    assert tracker.tokens is None


def test_invalidate_on_prompt_change():
    tracker = SystemOverheadTracker()
    tracker.update_from_usage(50000, 25000)
    assert tracker.tokens == 25000
    # system prompt 变化 → 失效
    tracker.invalidate("new system prompt content")
    assert tracker.tokens is None
    assert tracker.has_measured_value is False


def test_invalidate_no_change_keeps_value():
    tracker = SystemOverheadTracker()
    tracker.invalidate("prompt v1")
    tracker.update_from_usage(50000, 25000)
    assert tracker.tokens == 25000
    # 相同 prompt 不失效
    tracker.invalidate("prompt v1")
    assert tracker.tokens == 25000


def test_reset():
    tracker = SystemOverheadTracker()
    tracker.invalidate("prompt")
    tracker.update_from_usage(50000, 25000)
    tracker.reset()
    assert tracker.tokens is None
    assert tracker.has_measured_value is False


def test_apply_restore_from_result() -> None:
    """apply_restore 从 RestoreResult 恢复 overhead。"""
    from illusion.services.checkpoint_store import RestoreResult
    from illusion.services.compact.system_overhead_tracker import SystemOverheadTracker
    from illusion.engine.messages import ConversationMessage

    result = RestoreResult(
        messages=[],
        usage_input=0,
        usage_output=0,
        system_overhead=3000,
        system_overhead_hash="hash_xyz",
        system_prompt="sys prompt",
        system_prompt_hash="hash_xyz",
        checkpoint_count=0,
    )
    tracker = SystemOverheadTracker()
    tracker.apply_restore(result)
    assert tracker.tokens == 3000
    assert tracker.has_measured_value is True
