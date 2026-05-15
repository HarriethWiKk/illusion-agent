"""Tests for InProcessBackend: spawn, shutdown, send_message."""

from __future__ import annotations

import asyncio
from pathlib import Path

import pytest

from illusion.swarm.agent_executor import (
    AgentExecutionContext,
    AgentAbortController,
    get_agent_context,
    set_agent_context,
    get_active_agent,
    get_active_agent_by_name,
)
from illusion.swarm.in_process import InProcessBackend
from illusion.swarm.types import TeammateMessage, TeammateSpawnConfig


# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def spawn_config():
    return TeammateSpawnConfig(
        name="worker",
        team="test-team",
        prompt="hello",
        cwd="/tmp",
        parent_session_id="sess-001",
    )


@pytest.fixture
def backend(tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    return InProcessBackend()


# ---------------------------------------------------------------------------
# AgentExecutionContext
# ---------------------------------------------------------------------------


def test_agent_context_defaults():
    ctx = AgentExecutionContext(
        agent_id="w@t",
        agent_name="w",
    )
    assert ctx.color is None if hasattr(ctx, 'color') else True
    assert not ctx.abort_controller.is_cancelled


# ---------------------------------------------------------------------------
# ContextVar get / set
# ---------------------------------------------------------------------------


def test_get_agent_context_returns_none_outside_task():
    # Force reset to ensure clean state (ContextVar may leak between tests)
    from illusion.swarm.agent_executor import _agent_context_var
    token = _agent_context_var.set(None)
    try:
        result = get_agent_context()
        assert result is None
    finally:
        _agent_context_var.reset(token)


async def test_set_and_get_agent_context():
    ctx = AgentExecutionContext(agent_id="x@y", agent_name="x")
    set_agent_context(ctx)
    assert get_agent_context() is ctx
    # Clean up
    from illusion.swarm.agent_executor import _agent_context_var
    _agent_context_var.set(None)


# ---------------------------------------------------------------------------
# AgentAbortController
# ---------------------------------------------------------------------------


def test_abort_controller_graceful():
    ctrl = AgentAbortController()
    assert not ctrl.is_cancelled
    ctrl.request_cancel(reason="test")
    assert ctrl.is_cancelled
    assert ctrl.cancel_event.is_set()
    assert not ctrl.force_cancel.is_set()


def test_abort_controller_force():
    ctrl = AgentAbortController()
    ctrl.request_cancel(reason="force", force=True)
    assert ctrl.is_cancelled
    assert ctrl.cancel_event.is_set()
    assert ctrl.force_cancel.is_set()


# ---------------------------------------------------------------------------
# InProcessBackend.spawn
# ---------------------------------------------------------------------------


async def test_spawn_returns_success_result(backend, spawn_config):
    result = await backend.spawn(spawn_config)
    assert result.success is True
    assert result.agent_id == "worker@test-team"
    assert result.backend_type == "in_process"
    assert result.task_id.startswith("in_process_")


async def test_spawn_duplicate_returns_failure(backend, spawn_config):
    await backend.spawn(spawn_config)
    result = await backend.spawn(spawn_config)
    assert result.success is False
    assert result.error is not None


# ---------------------------------------------------------------------------
# InProcessBackend.shutdown
# ---------------------------------------------------------------------------


async def test_shutdown_unknown_agent_returns_false(backend):
    result = await backend.shutdown("nonexistent@team")
    assert result is False


async def test_graceful_shutdown(backend, spawn_config):
    await backend.spawn(spawn_config)
    result = await backend.shutdown("worker@test-team", timeout=2.0)
    assert result is True


async def test_force_shutdown(backend, spawn_config):
    await backend.spawn(spawn_config)
    result = await backend.shutdown("worker@test-team", force=True, timeout=2.0)
    assert result is True


# ---------------------------------------------------------------------------
# InProcessBackend.send_message
# ---------------------------------------------------------------------------


async def test_send_message_to_active_agent(backend, spawn_config):
    await backend.spawn(spawn_config)
    # Give the asyncio task time to start and register the agent
    for _ in range(10):
        await asyncio.sleep(0.1)
        if "worker@test-team" in [a[0] for a in backend.list_agents()]:
            break
    msg = TeammateMessage(text="work on it", from_agent="leader")
    # Should not raise
    await backend.send_message("worker@test-team", msg)
    await backend.shutdown("worker@test-team", force=True, timeout=2.0)


async def test_send_message_invalid_agent_id_raises(backend):
    with pytest.raises(ValueError):
        await backend.send_message("no-at-sign", TeammateMessage(text="hi", from_agent="l"))


# ---------------------------------------------------------------------------
# list_agents / shutdown_all
# ---------------------------------------------------------------------------


async def test_list_agents(backend, spawn_config):
    await backend.spawn(spawn_config)
    agents = backend.list_agents()
    assert len(agents) == 1
    assert agents[0][0] == "worker@test-team"


async def test_shutdown_all(backend, tmp_path, monkeypatch):
    monkeypatch.setattr(Path, "home", lambda: tmp_path)
    for name in ("a", "b"):
        cfg = TeammateSpawnConfig(
            name=name,
            team="t",
            prompt="run",
            cwd="/tmp",
            parent_session_id="s",
        )
        await backend.spawn(cfg)

    await backend.shutdown_all(force=True, timeout=2.0)
    assert backend.list_agents() == []
