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


def test_update_from_usage_overrides_previous():
    """每轮无条件覆盖，接受自然波动。"""
    tracker = SystemOverheadTracker()
    tracker.update_from_usage(50000, 25000)
    assert tracker.tokens == 25000
    # 下一轮反推值不同 → 直接覆盖
    tracker.update_from_usage(55000, 25000)
    assert tracker.tokens == 30000


def test_reset():
    tracker = SystemOverheadTracker()
    tracker.update_from_usage(50000, 25000)
    tracker.reset()
    assert tracker.tokens is None
    assert tracker.has_measured_value is False


def test_apply_restore_from_result() -> None:
    """apply_restore 从 RestoreResult 恢复 overhead。"""
    from illusion.services.checkpoint_store import RestoreResult
    from illusion.services.compact.system_overhead_tracker import SystemOverheadTracker

    result = RestoreResult(
        messages=[],
        usage_input=0,
        usage_output=0,
        system_overhead=3000,
        checkpoint_count=0,
    )
    tracker = SystemOverheadTracker()
    tracker.apply_restore(result)
    assert tracker.tokens == 3000
    assert tracker.has_measured_value is True


def test_apply_restore_none_overhead_resets() -> None:
    """apply_restore 遇到 None overhead 时 reset。"""
    from illusion.services.checkpoint_store import RestoreResult
    from illusion.services.compact.system_overhead_tracker import SystemOverheadTracker

    result = RestoreResult(
        messages=[],
        usage_input=0,
        usage_output=0,
        system_overhead=None,
        checkpoint_count=0,
    )
    tracker = SystemOverheadTracker()
    tracker.update_from_usage(50000, 25000)  # 先有值
    tracker.apply_restore(result)
    assert tracker.tokens is None
