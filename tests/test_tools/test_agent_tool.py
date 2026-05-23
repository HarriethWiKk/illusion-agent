"""Tests for agent tool foreground/background behavior in team mode."""

from __future__ import annotations

import asyncio
from types import SimpleNamespace
from pathlib import Path

import pytest

from illusion.state import AppState, AppStateStore
from illusion.swarm.agent_executor import AgentResult
from illusion.tools.agent_tool import AgentTool, AgentToolInput
from illusion.tools.base import ToolExecutionContext, ToolRegistry


def _query_engine(tmp_path: Path) -> SimpleNamespace:
    registry = ToolRegistry()
    return SimpleNamespace(
        _api_client=object(),
        _tool_registry=registry,
        _permission_checker=object(),
        _cwd=tmp_path,
        _model="demo-model",
        _system_prompt="demo-system",
        _max_tokens=1024,
        _max_turns=8,
        _permission_prompt=None,
        _ask_user_prompt=None,
        _hook_executor=None,
    )


def _context(tmp_path: Path, store: AppStateStore) -> ToolExecutionContext:
    registry = ToolRegistry()
    return ToolExecutionContext(
        cwd=tmp_path,
        metadata={
            "tool_registry": registry,
            "query_engine": _query_engine(tmp_path),
            "app_state_store": store,
            "session_id": "session-test",
        },
    )


@pytest.mark.asyncio
async def test_agent_tool_forces_foreground_for_team_lead(tmp_path: Path, monkeypatch):
    store = AppStateStore(
        AppState(
            model="demo-model",
            permission_mode="default",
            team_context={"teamName": "demo-team"},
        )
    )
    context = _context(tmp_path, store)
    calls: dict[str, bool] = {}

    async def _fake_run_agent_in_process(
        config,
        query_context,
        parent_registry,
        is_async: bool = False,
        existing_context=None,
    ):
        del config, query_context, parent_registry, existing_context
        calls["is_async"] = is_async
        return AgentResult(agent_id="agent-test", success=True, result_text="agent done")

    monkeypatch.setattr(
        "illusion.swarm.agent_executor.run_agent_in_process",
        _fake_run_agent_in_process,
    )

    result = await AgentTool().execute(
        AgentToolInput(
            description="run teammate task",
            prompt="Do a short task and return.",
            run_in_background=True,
        ),
        context,
    )

    assert result.is_error is False
    assert "launched in background" in result.output

    await asyncio.sleep(0)
    assert calls["is_async"] is True


@pytest.mark.asyncio
async def test_agent_tool_keeps_background_outside_team_mode(tmp_path: Path, monkeypatch):
    store = AppStateStore(AppState(model="demo-model", permission_mode="default"))
    context = _context(tmp_path, store)
    calls: dict[str, bool] = {}

    async def _fake_run_agent_in_process(
        config,
        query_context,
        parent_registry,
        is_async: bool = False,
        existing_context=None,
    ):
        del config, query_context, parent_registry, existing_context
        calls["is_async"] = is_async
        return AgentResult(agent_id="agent-test", success=True, result_text="agent done")

    monkeypatch.setattr(
        "illusion.swarm.agent_executor.run_agent_in_process",
        _fake_run_agent_in_process,
    )

    result = await AgentTool().execute(
        AgentToolInput(
            description="run background task",
            prompt="Do a short task and return.",
            run_in_background=True,
        ),
        context,
    )

    assert result.is_error is False
    assert "launched in background" in result.output

    await asyncio.sleep(0)
    assert calls["is_async"] is True
