"""checkpoint 持久化、round driver 与 /goal 命令测试。"""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from illusion.engine.messages import ConversationMessage
from illusion.engine.query_engine import QueryEngine
from illusion.goal.manager import GoalManager
from illusion.goal.prompts import render_goal_round_prompt
from illusion.goal.types import GoalSettings
from illusion.services.checkpoint_store import CheckpointStore


# ---------------------------------------------------------------------------
# checkpoint _goal 行持久化
# ---------------------------------------------------------------------------


@pytest.fixture
def store(tmp_path: Path) -> CheckpointStore:
    return CheckpointStore(tmp_path / "session", "test-session")


async def _restore(store: CheckpointStore):
    return await store.restore()


def test_goal_row_roundtrip(store: CheckpointStore) -> None:
    async def run() -> None:
        manager = GoalManager(GoalSettings(default_max_goal_rounds=4))
        manager.current_source = "human"
        manager.create("objective")
        await store.append_goal(manager.persisted_state())

        result = await store.restore()
        assert result.goal_state is not None
        assert result.goal_state["snapshot"]["objective"] == "objective"

        # clear 墓碑
        manager.current_source = "human"
        manager.clear()
        await store.append_goal(manager.persisted_state())
        result = await store.restore()
        assert result.goal_state is None

    asyncio.run(run())


def test_goal_row_last_wins(store: CheckpointStore) -> None:
    async def run() -> None:
        manager = GoalManager(GoalSettings(default_max_goal_rounds=4))
        manager.current_source = "human"
        manager.create("v1")
        await store.append_goal(manager.persisted_state())
        manager.create  # noqa: B018 (intentional no-op for clarity)
        # 编辑后再次落盘 → last-wins
        view = manager.get_view()
        assert view is not None
        manager.edit(view.snapshot.id, view.snapshot.revision, objective="v2")
        await store.append_goal(manager.persisted_state())
        result = await store.restore()
        assert result.goal_state is not None
        assert result.goal_state["snapshot"]["objective"] == "v2"

    asyncio.run(run())


def test_goal_row_rewind_compatible(store: CheckpointStore) -> None:
    async def run() -> None:
        manager = GoalManager(GoalSettings(default_max_goal_rounds=4))
        manager.current_source = "human"
        manager.create("objective")
        await store.append_checkpoint()  # id 0
        await store.append_message(ConversationMessage.from_user_text("hello"))
        await store.append_checkpoint()  # id 1
        await store.append_message(ConversationMessage.from_user_text("world"))
        await store.append_goal(manager.persisted_state())

        # rewind 到 checkpoint 1：丢弃其后的内容（含 _goal 行）→ 恢复无目标
        result = await store.rewind_to(1)
        assert result.goal_state is None
        assert len(result.messages) == 1

    asyncio.run(run())


# ---------------------------------------------------------------------------
# round driver（drive_goal_rounds）
# ---------------------------------------------------------------------------


class _FakeApiClient:
    """最小 API 客户端桩：不回调用具，直接产出一句最终文本。"""

    async def stream_message(self, *args, **kwargs):
        from illusion.api.client import ApiMessageCompleteEvent
        from illusion.api.usage import UsageSnapshot
        from illusion.engine.messages import ConversationMessage as CM
        from illusion.engine.messages import TextBlock

        msg = CM(role="assistant", content=[TextBlock(text="working")])
        yield ApiMessageCompleteEvent(
            message=msg,
            usage=UsageSnapshot(
                input_tokens=1,
                output_tokens=1,
                cache_read_input_tokens=0,
                cache_creation_input_tokens=0,
            ),
        )


class _FakeEngine(QueryEngine):
    """绕过 __init__ 的轻量桩（仅跑 drive_goal_rounds 需要的部分）。"""

    def __init__(self, manager: GoalManager | None, cwd: str = ".") -> None:
        self._goal_manager = manager
        self._cwd = Path(cwd)
        self._messages: list[ConversationMessage] = []
        self._max_turns = 10
        self._checkpoint_store = None
        from illusion.engine.cost_tracker import CostTracker

        self._cost_tracker = CostTracker()
        self._last_api_usage = None
        self._last_api_usage_message_count = 0
        self._api_client = _FakeApiClient()
        from illusion.tools.base import ToolRegistry

        self._tool_registry = ToolRegistry()
        self._permission_checker = None
        self._system_prompt = "system"
        self._model = "fake-model"
        self._max_tokens = 1024
        self._permission_prompt = None
        self._ask_user_prompt = None
        self._plan_approval_prompt = None
        self._print_mode = False
        self._sandbox_permission_prompt = None
        self._hook_executor = None
        self._tool_metadata: dict = {}
        self._effort = None
        self._bg_agent_tracker = None
        self._compact_state = None
        self._file_history = None
        self._file_state_cache = None
        self._session_id = ""


@pytest.mark.asyncio
async def test_drive_rounds_injects_goal_round_messages() -> None:
    manager = GoalManager(GoalSettings(default_max_goal_rounds=3))
    manager.current_source = "human"
    manager.create("do the thing")
    engine = _FakeEngine(manager)

    from illusion.engine.stream_events import GoalStatusEvent

    events = [ev async for ev in engine.drive_goal_rounds()]
    # 3 轮各注入 <goal_round> 用户消息 + GoalStatusEvent(round)
    goal_rounds = [
        m for m in engine.messages
        if m.role == "user" and m.text.startswith("<goal_round>")
    ]
    assert len(goal_rounds) == 3
    assert manager.rounds_started == 3
    rounds = [e for e in events if isinstance(e, GoalStatusEvent) and e.kind == "round"]
    assert [r.round for r in rounds] == [1, 2, 3]
    assert all(r.max_rounds == 3 for r in rounds)
    # 消息内容与渲染函数输出一致（含内嵌的精确 CAS ref）
    snap = manager.snapshot
    assert snap is not None
    assert goal_rounds[0].text == render_goal_round_prompt(
        "do the thing", 1, 3, goal_id=snap.id, revision=1
    )
    assert f"id={snap.id} revision=1" in goal_rounds[0].text
    # 轮次耗尽：round-limit 自动受阻 + limit 事件
    assert snap.phase == "blocked"
    assert snap.blocked_reason is not None
    assert snap.blocked_reason.code == "round-limit"
    assert any(isinstance(e, GoalStatusEvent) and e.kind == "limit" for e in events)


@pytest.mark.asyncio
async def test_drive_rounds_stops_when_disarmed() -> None:
    manager = GoalManager(GoalSettings(default_max_goal_rounds=5))
    manager.current_source = "human"
    manager.create("do the thing")
    engine = _FakeEngine(manager)
    manager.disarm()
    events = [ev async for ev in engine.drive_goal_rounds()]
    assert events == []
    assert manager.rounds_started == 0


@pytest.mark.asyncio
async def test_wrapup_injected_then_stops() -> None:
    from illusion.goal.types import PendingWrapup

    manager = GoalManager(GoalSettings(default_max_goal_rounds=5))
    manager.current_source = "human"
    manager.create("do the thing")
    view = manager.get_view()
    assert view is not None
    manager.complete(view.snapshot.id, view.snapshot.revision)
    manager.set_pending_wrapup(PendingWrapup(kind="complete", objective="do the thing"))
    engine = _FakeEngine(manager)

    await _drain(engine.drive_goal_rounds())
    wrapup = [
        m for m in engine.messages
        if m.role == "user" and m.text.startswith("<goal_complete>")
    ]
    assert len(wrapup) == 1
    # 终态后不再注入 goal round
    assert not any(m.text.startswith("<goal_round>") for m in engine.messages)


@pytest.mark.asyncio
async def test_drive_rounds_emits_wrapup_event() -> None:
    from illusion.engine.stream_events import GoalStatusEvent
    from illusion.goal.types import PendingWrapup

    manager = GoalManager(GoalSettings(default_max_goal_rounds=5))
    manager.current_source = "human"
    manager.create("do the thing")
    view = manager.get_view()
    assert view is not None
    manager.complete(view.snapshot.id, view.snapshot.revision)
    manager.set_pending_wrapup(PendingWrapup(kind="complete", objective="do the thing"))
    engine = _FakeEngine(manager)

    events = [ev async for ev in engine.drive_goal_rounds()]
    wrapups = [e for e in events if isinstance(e, GoalStatusEvent) and e.kind == "wrapup"]
    assert len(wrapups) == 1
    assert wrapups[0].phase == "complete"


async def _drain(agen) -> None:
    async for _ in agen:
        pass


# ---------------------------------------------------------------------------
# /goal 命令
# ---------------------------------------------------------------------------


class _FakeCommandEngine:
    """/goal 命令 handler 所需的最小引擎桩。"""

    def __init__(self, manager: GoalManager | None) -> None:
        self._goal_manager = manager


def test_goal_command_create_and_status() -> None:
    from illusion.commands.goal import goal_handler
    from illusion.commands.types import CommandContext

    manager = GoalManager(GoalSettings(default_max_goal_rounds=5))
    engine = _FakeCommandEngine(manager)
    ctx = CommandContext(engine=engine)  # type: ignore[arg-type]

    async def run() -> None:
        result = await goal_handler("build the thing", ctx)
        assert result.drive_goal is True
        assert manager.snapshot is not None
        assert manager.snapshot.objective == "build the thing"
        assert manager.activation == "armed"

        result = await goal_handler("", ctx)
        assert "Objective: build the thing" in (result.message or "")

        result = await goal_handler("pause", ctx)
        assert manager.snapshot is not None and manager.snapshot.phase == "paused"
        assert result.drive_goal is False

        result = await goal_handler("resume", ctx)
        assert manager.snapshot is not None and manager.snapshot.phase == "active"
        assert result.drive_goal is True

        result = await goal_handler("edit new objective", ctx)
        assert manager.snapshot is not None
        assert manager.snapshot.objective == "new objective"

        result = await goal_handler("clear", ctx)
        assert manager.snapshot is None

    asyncio.run(run())


def test_goal_command_no_goal() -> None:
    from illusion.commands.goal import goal_handler
    from illusion.commands.types import CommandContext

    manager = GoalManager()
    engine = _FakeCommandEngine(manager)
    ctx = CommandContext(engine=engine)  # type: ignore[arg-type]

    async def run() -> None:
        result = await goal_handler("", ctx)
        assert result.message == "No goal is currently set."
        result = await goal_handler("pause", ctx)
        assert "No goal is currently set." in (result.message or "")

    asyncio.run(run())


# ---------------------------------------------------------------------------
# GoalManager 生命周期（full_reset / restore_from）
# ---------------------------------------------------------------------------


def test_engine_goal_lifecycle() -> None:
    manager = GoalManager(GoalSettings(default_max_goal_rounds=5))
    manager.current_source = "human"
    manager.create("objective")
    assert manager.snapshot is not None

    manager.reset()
    assert manager.snapshot is None
    assert manager.activation == "disarmed"

    manager.restore_from({
        "snapshot": {
            "id": "goal-x",
            "revision": 2,
            "objective": "restored",
            "phase": "active",
            "max_goal_rounds": 5,
        },
        "rounds_started": 1,
        "created_at": 1.0,
        "updated_at": 1.0,
    })
    assert manager.snapshot is not None
    assert manager.snapshot.objective == "restored"
    assert manager.rounds_started == 1
    assert manager.activation == "disarmed"  # 恢复后恒 disarmed
    assert not manager.should_continue()
