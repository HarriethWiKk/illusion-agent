"""CostTracker 单元测试。"""
from illusion.engine.cost_tracker import CostTracker
from illusion.api.usage import UsageSnapshot


def test_from_snapshot_restores_usage():
    usage_dict = {"input_tokens": 387519, "output_tokens": 1838}
    tracker = CostTracker.from_snapshot(usage_dict)
    assert tracker.total.input_tokens == 387519
    assert tracker.total.output_tokens == 1838


def test_from_snapshot_default_zero():
    tracker = CostTracker.from_snapshot({})
    assert tracker.total.input_tokens == 0
    assert tracker.total.output_tokens == 0


def test_from_snapshot_then_add():
    tracker = CostTracker.from_snapshot({"input_tokens": 100, "output_tokens": 50})
    tracker.add(UsageSnapshot(input_tokens=200, output_tokens=100))
    assert tracker.total.input_tokens == 300
    assert tracker.total.output_tokens == 150
