"""CostTracker 单元测试。"""
from illusion.engine.cost_tracker import CostTracker
from illusion.api.usage import UsageSnapshot


def test_apply_restore_from_result() -> None:
    """apply_restore 从 RestoreResult 恢复 usage。"""
    from illusion.services.checkpoint_store import RestoreResult
    from illusion.engine.cost_tracker import CostTracker
    from illusion.engine.messages import ConversationMessage

    result = RestoreResult(
        messages=[ConversationMessage.from_user_text("x")],
        usage_input=500,
        usage_output=50,
        system_overhead=2000,
        checkpoint_count=1,
    )
    tracker = CostTracker()
    tracker.apply_restore(result)
    assert tracker.total.input_tokens == 500
    assert tracker.total.output_tokens == 50


def test_set_usage() -> None:
    """set_usage 直接设置累积值。"""
    from illusion.engine.cost_tracker import CostTracker
    tracker = CostTracker()
    tracker.set_usage(300, 30)
    assert tracker.total.input_tokens == 300
    assert tracker.total.output_tokens == 30


def test_add_accumulates_usage():
    tracker = CostTracker()
    tracker.add(UsageSnapshot(input_tokens=100, output_tokens=50))
    assert tracker.total.input_tokens == 100
    assert tracker.total.output_tokens == 50
    tracker.add(UsageSnapshot(input_tokens=200, output_tokens=100))
    assert tracker.total.input_tokens == 300
    assert tracker.total.output_tokens == 150


def test_initial_state_zero():
    tracker = CostTracker()
    assert tracker.total.input_tokens == 0
    assert tracker.total.output_tokens == 0
