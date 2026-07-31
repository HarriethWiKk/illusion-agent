""" agent_creator 服务测试 """
from __future__ import annotations

from pathlib import Path
from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.services.agent_creator import (
    GeneratedAgent,
    AGENT_CREATION_SYSTEM_PROMPT,
    validate_agent_definition,
    write_agent_definition,
)


def test_prompt_no_claude_brand():
    """提示词中品牌名已替换为 illusion agent。"""
    assert "Claude" not in AGENT_CREATION_SYSTEM_PROMPT


def test_validate_name_conflict(monkeypatch):
    """名称与现有 agent 冲突时报错。"""
    existing = MagicMock()
    existing.name = "existing-agent"
    monkeypatch.setattr("illusion.services.agent_creator.get_all_agent_definitions", lambda: [existing])
    result = validate_agent_definition({"name": "existing-agent", "system_prompt": "x", "description": "y"}, cwd=".")
    assert "name" in result


def test_validate_valid_definition(monkeypatch):
    """合法定义返回空错误 dict。"""
    monkeypatch.setattr("illusion.services.agent_creator.get_all_agent_definitions", lambda: [])
    result = validate_agent_definition({"name": "new-agent", "system_prompt": "x", "description": "y", "model": "inherit"}, cwd=".")
    assert result == {}


def test_write_agent_definition_user_scope(tmp_path, monkeypatch):
    """user scope 写入 agents 目录。"""
    fake_dir = tmp_path / "agents"
    monkeypatch.setattr("illusion.services.agent_creator._get_agents_dir", lambda scope, cwd: fake_dir)
    fields = {"name": "my-agent", "description": "Use when x", "system_prompt": "You are...", "model": "inherit"}
    path = write_agent_definition(fields, scope="user", cwd=".")
    assert path.exists()
    content = path.read_text(encoding="utf-8")
    assert "---" in content
    assert "name: my-agent" in content
    assert "You are..." in content


@pytest.mark.asyncio
async def test_generate_agent_from_description_parses_json(monkeypatch):
    """generate_agent_from_description 解析 LLM 返回的 JSON。"""
    from illusion.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
    from illusion.engine.messages import ConversationMessage, TextBlock
    from illusion.services import agent_creator

    json_text = '{"identifier":"test-runner","whenToUse":"Use this agent when tests","systemPrompt":"You are a test runner"}'

    async def fake_stream(request):
        yield ApiTextDeltaEvent(text=json_text)
        yield ApiMessageCompleteEvent(message=ConversationMessage(role="assistant", content=[TextBlock(text=json_text)]), usage=None, stop_reason="end_turn")

    api_client = MagicMock()
    api_client.stream_message = MagicMock(return_value=fake_stream(None))
    engine = MagicMock()
    engine.api_client = api_client
    engine.model = "test-model"
    engine.max_tokens = 4096

    result = await agent_creator.generate_agent_from_description("write a test runner", model="test-model", existing_identifiers=[], engine=engine)
    assert isinstance(result, GeneratedAgent)
    assert result.identifier == "test-runner"
    assert result.system_prompt == "You are a test runner"


@pytest.mark.asyncio
async def test_generate_agent_inherit_uses_engine_model():
    """model='inherit' 时应回退到 engine.model，而非将 'inherit' 传给 API。"""
    from illusion.api.client import ApiMessageCompleteEvent, ApiTextDeltaEvent
    from illusion.engine.messages import ConversationMessage, TextBlock
    from illusion.services import agent_creator

    json_text = '{"identifier":"test","whenToUse":"use when","systemPrompt":"you are"}'

    captured: dict[str, str] = {}

    async def fake_stream(request):
        # 捕获传给 ApiMessageRequest 的 model，验证回退到 engine.model
        captured["model"] = request.model
        yield ApiTextDeltaEvent(text=json_text)
        yield ApiMessageCompleteEvent(
            message=ConversationMessage(role="assistant", content=[TextBlock(text=json_text)]),
            usage=None,
            stop_reason="end_turn",
        )

    api_client = MagicMock()
    api_client.stream_message = MagicMock(side_effect=fake_stream)
    engine = MagicMock()
    engine.api_client = api_client
    engine.model = "gpt-4o"
    engine.max_tokens = 4096

    result = await agent_creator.generate_agent_from_description(
        "test prompt", "inherit", [], engine,
    )

    assert captured["model"] == "gpt-4o"
    assert captured["model"] != "inherit"
    assert result.identifier == "test"


def test_get_agents_dir_user_scope(monkeypatch, tmp_path):
    """user scope 返回 <config_dir>/agents（默认 ~/.illusion/agents）。"""
    from illusion.services import agent_creator

    monkeypatch.setenv("ILLUSION_CONFIG_DIR", str(tmp_path))
    result = agent_creator._get_agents_dir("user", ".")
    assert result == tmp_path / "agents"


def test_get_agents_dir_project_scope(tmp_path):
    """project scope 返回 {cwd}/.illusion/agents。"""
    from illusion.services import agent_creator

    cwd = tmp_path / "proj"
    cwd.mkdir()
    result = agent_creator._get_agents_dir("project", cwd)
    assert result == cwd.resolve() / ".illusion" / "agents"
