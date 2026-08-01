"""
代理定义服务
============

提供代理定义的校验、文件写入与 LLM 辅助生成能力，是 /agent 创建向导功能的核心后端服务。

核心设计：
    - 支持用户手动输入或 LLM 从自然语言描述生成代理定义
    - 代理定义存储为 frontmatter markdown 文件
    - 自动避免标识符重复

主要组件：
    - AGENT_CREATION_SYSTEM_PROMPT: LLM 生成代理定义使用的系统提示词
    - GeneratedAgent: LLM 生成的代理定义数据模型
    - validate_agent_definition: 校验用户输入的代理字段
    - write_agent_definition: 将代理定义写入 frontmatter markdown 文件
    - generate_agent_from_description: 通过 LLM 从自然语言生成代理定义
    - list_available_models: 返回可用模型列表
    - list_available_tools: 返回可用工具列表

使用示例：
    >>> errors = validate_agent_definition({"name": "test", "system_prompt": "..."}, cwd)
    >>> path = write_agent_definition(fields, scope, cwd)
    >>> agent = await generate_agent_from_description("帮助代码审查", "inherit", [], engine)
"""

from __future__ import annotations

import json
import logging
import re
from dataclasses import dataclass
from pathlib import Path
from typing import TYPE_CHECKING, Any

from illusion.api.client import ApiMessageRequest
from illusion.config.paths import get_config_dir, get_project_config_dir
from illusion.coordinator.agent_definitions import get_all_agent_definitions
from illusion.engine.messages import ConversationMessage

if TYPE_CHECKING:
    from illusion.engine.query_engine import QueryEngine
    from illusion.state import AppStateStore
    from illusion.tools.base import ToolRegistry

logger = logging.getLogger(__name__)

# AgentTool 的注册名（用于提示词中的工具引用）
_AGENT_TOOL_NAME = "agent"

AGENT_CREATION_SYSTEM_PROMPT = f"""You are an elite AI agent architect specializing in crafting high-performance agent configurations. Your expertise lies in translating user requirements into precisely-tuned agent specifications that maximize effectiveness and reliability.

**Important Context**: You may have access to project-specific instructions from CLAUDE.md files and other context that may include coding standards, project structure, and custom requirements. Consider this context when creating agents to ensure they align with the project's established patterns and practices.

When a user describes what they want an agent to do, you will:

1. **Extract Core Intent**: Identify the fundamental purpose, key responsibilities, and success criteria for the agent. Look for both explicit requirements and implicit needs. Consider any project-specific context from CLAUDE.md files. For agents that are meant to review code, you should assume that the user is asking to review recently written code and not the whole codebase, unless the user has explicitly instructed you otherwise.

2. **Design Expert Persona**: Create a compelling expert identity that embodies deep domain knowledge relevant to the task. The persona should inspire confidence and guide the agent's decision-making approach.

3. **Architect Comprehensive Instructions**: Develop a system prompt that:
   - Establishes clear behavioral boundaries and operational parameters
   - Provides specific methodologies and best practices for task execution
   - Anticipates edge cases and provides guidance for handling them
   - Incorporates any specific requirements or preferences mentioned by the user
   - Defines output format expectations when relevant
   - Aligns with project-specific coding standards and patterns from CLAUDE.md

4. **Optimize for Performance**: Include:
   - Decision-making frameworks appropriate to the domain
   - Quality control mechanisms and self-verification steps
   - Efficient workflow patterns
   - Clear escalation or fallback strategies

5. **Create Identifier**: Design a concise, descriptive identifier that:
   - Uses lowercase letters, numbers, and hyphens only
   - Is typically 2-4 words joined by hyphens
   - Clearly indicates the agent's primary function
   - Is memorable and easy to type
   - Avoids generic terms like "helper" or "assistant"

6. **Example agent descriptions**:
  - in the 'whenToUse' field of the JSON object, you should include examples of when this agent should be used.
  - examples should be of the form:
    - <example>
      Context: The user is creating a test-runner agent that should be called after a logical chunk of code is written.
      user: "Please write a function that checks if a number is prime"
      assistant: "Here is the relevant function: "
      <function call omitted for brevity only for this example>
      <commentary>
      Since a significant piece of code was written, use the {_AGENT_TOOL_NAME} tool to launch the test-runner agent to run the tests.
      </commentary>
      assistant: "Now let me use the test-runner agent to run the tests"
    </example>
    - <example>
      Context: User is creating an agent to respond to the word "hello" with a friendly joke.
      user: "Hello"
      assistant: "I'm going to use the {_AGENT_TOOL_NAME} tool to launch the greeting-responder agent to respond with a friendly goodbye"
      <commentary>
      Since the user is greeting, use the greeting-responder agent to respond with a friendly goodbye.
      </commentary>
    </example>
  - If the user mentioned or implied that the agent should be used proactively, you should include examples of this.
- NOTE: Ensure that in the examples, you are making the assistant use the {_AGENT_TOOL_NAME} tool and not simply respond directly to the task.

Your output must be a valid JSON object with exactly these fields:
{{
  "identifier": "A unique, descriptive identifier using lowercase letters, numbers, and hyphens (e.g., 'test-runner', 'api-docs-writer', 'code-formatter')",
  "whenToUse": "A precise, actionable description starting with 'Use this agent when...' that clearly defines the triggering conditions and use cases. Ensure you include examples as described above.",
  "systemPrompt": "The complete system prompt that will govern the agent's behavior, written in second person ('You are...', 'You will...') and structured for maximum clarity and effectiveness"
}}

Key principles for your system prompts:
- Be specific rather than generic - avoid vague instructions
- Include concrete examples when they would clarify behavior
- Balance comprehensiveness with clarity - every instruction should add value
- Ensure the agent has enough context to handle variations of the core task
- Make the agent proactive in seeking clarification when needed
- Build in quality assurance and self-correction mechanisms

Remember: The agents you create should be autonomous experts capable of handling their designated tasks with minimal additional guidance. Your system prompts are their complete operational manual.
"""


@dataclass
class GeneratedAgent:
    """LLM 生成的代理定义。

    属性:
        identifier: 代理标识符（小写字母、数字、连字符）
        when_to_use: 使用时机描述
        system_prompt: 系统提示词
    """

    identifier: str
    when_to_use: str
    system_prompt: str


def _get_agents_dir(scope: str, cwd: str | Path) -> Path:
    """根据 scope 返回 agents 目录路径。

    Args:
        scope: 作用域，``"user"`` 返回用户级目录，``"project"`` 返回项目级目录
        cwd: 当前工作目录（仅 ``"project"`` scope 使用）

    Returns:
        Path: agents 目录路径

    Raises:
        ValueError: 不支持的 scope
    """
    if scope == "user":
        return get_config_dir() / "agents"
    if scope == "project":
        return get_project_config_dir(cwd) / "agents"
    raise ValueError(f"Unsupported scope: {scope!r}")


def validate_agent_definition(
    fields: dict[str, Any],
    cwd: str | Path = ".",
) -> dict[str, str]:
    """校验代理定义字段，返回错误字典。

    空字典表示校验通过。检查项：
        - ``name`` 非空且不与现有代理冲突
        - ``description`` 非空
        - ``system_prompt`` 非空
        - ``model`` 若提供需为非空字符串

    Args:
        fields: 代理定义字段
        cwd: 当前工作目录（保留参数，供后续扩展使用）

    Returns:
        dict[str, str]: 字段名到错误信息的映射
    """
    del cwd  # 预留：当前校验不依赖 cwd
    errors: dict[str, str] = {}

    name = str(fields.get("name", "")).strip()
    if not name:
        errors["name"] = "代理名称不能为空"
    else:
        for existing in get_all_agent_definitions():
            if existing.name == name:
                errors["name"] = f"代理名称 '{name}' 已存在"
                break

    if not str(fields.get("description", "")).strip():
        errors["description"] = "代理描述不能为空"

    if not str(fields.get("system_prompt", "")).strip():
        errors["system_prompt"] = "系统提示词不能为空"

    model = fields.get("model")
    if model is not None and model != "inherit" and (not isinstance(model, str) or not str(model).strip()):
        errors["model"] = "模型必须是非空字符串或 'inherit'"

    return errors


def write_agent_definition(
    fields: dict[str, Any],
    scope: str = "user",
    cwd: str | Path = ".",
) -> Path:
    """将代理定义写入 frontmatter markdown 文件。

    frontmatter 字段与 ``AgentDefinition`` 一致（name/description/model 等），
    markdown body 作为 ``system_prompt``。

    Args:
        fields: 代理定义字段
        scope: 写入作用域，``"user"`` 或 ``"project"``
        cwd: 当前工作目录（仅 ``"project"`` scope 使用）

    Returns:
        Path: 写入的文件路径

    Raises:
        ValueError: 代理名称为空
    """
    agents_dir = _get_agents_dir(scope, cwd)
    agents_dir.mkdir(parents=True, exist_ok=True)

    name = str(fields.get("name", "")).strip()
    if not name:
        raise ValueError("代理名称不能为空")

    # 文件名安全化：仅保留字母、数字、点、下划线、连字符
    safe_name = re.sub(r"[^a-zA-Z0-9._-]", "-", name).strip("-") or "agent"
    file_path = agents_dir / f"{safe_name}.md"

    # 构建 frontmatter（字段顺序与现有 agent 定义文件一致）
    fm_lines: list[str] = ["---"]
    fm_lines.append(f"name: {name}")

    description = str(fields.get("description", "")).strip()
    if description:
        fm_lines.append(f"description: {description}")

    model = fields.get("model")
    if model:
        fm_lines.append(f"model: {model}")

    tools = fields.get("tools")
    if tools:
        if isinstance(tools, list):
            fm_lines.append("tools: [" + ", ".join(str(t) for t in tools) + "]")
        else:
            fm_lines.append(f"tools: {tools}")

    disallowed_tools = fields.get("disallowed_tools") or fields.get("disallowedTools")
    if disallowed_tools:
        if isinstance(disallowed_tools, list):
            fm_lines.append(
                "disallowedTools: [" + ", ".join(str(t) for t in disallowed_tools) + "]"
            )
        else:
            fm_lines.append(f"disallowedTools: {disallowed_tools}")

    effort = fields.get("effort")
    if effort:
        fm_lines.append(f"effort: {effort}")

    permission_mode = fields.get("permission_mode") or fields.get("permissionMode")
    if permission_mode:
        fm_lines.append(f"permissionMode: {permission_mode}")

    color = fields.get("color")
    if color:
        fm_lines.append(f"color: {color}")

    fm_lines.append("---")

    body = str(fields.get("system_prompt", "")).strip()
    content = "\n".join(fm_lines) + "\n" + body + "\n"

    file_path.write_text(content, encoding="utf-8")
    return file_path


def _extract_json(text: str) -> str:
    """从可能包含 markdown 代码块的文本中提取 JSON 字符串。

    Args:
        text: 原始文本

    Returns:
        str: 提取出的 JSON 字符串
    """
    text = text.strip()
    # 尝试提取 ```json ... ``` 代码块
    match = re.search(r"```(?:json)?\s*\n?(.*?)\n?```", text, re.DOTALL)
    if match:
        return match.group(1).strip()
    # 否则提取第一个 { 到最后一个 }
    start = text.find("{")
    end = text.rfind("}")
    if start != -1 and end != -1 and end > start:
        return text[start : end + 1]
    return text


async def generate_agent_from_description(
    user_prompt: str,
    model: str,
    existing_identifiers: list[str],
    engine: QueryEngine,
    abort_signal: Any = None,
) -> GeneratedAgent:
    """通过 LLM 从自然语言描述生成代理定义。

    使用 ``AGENT_CREATION_SYSTEM_PROMPT`` 作为系统提示词，将用户描述发送
    给 LLM，解析返回的 JSON 为 ``GeneratedAgent``。

    Args:
        user_prompt: 用户的自然语言描述
        model: 使用的模型名称
        existing_identifiers: 已存在的代理标识符列表（用于去重提示）
        engine: 查询引擎（用于访问 api_client 和 max_tokens）
        abort_signal: 中止信号（保留参数，当前未使用）

    Returns:
        GeneratedAgent: 生成的代理定义

    Raises:
        ValueError: LLM 返回的内容不是有效 JSON 或缺少必需字段
    """
    del abort_signal  # 预留

    # 构造用户消息：附加已存在标识符以避免重复
    if existing_identifiers:
        user_content = (
            f"Existing agent identifiers (avoid duplicates): "
            f"{', '.join(existing_identifiers)}\n\n"
            f"User request: {user_prompt}"
        )
    else:
        user_content = user_prompt

    messages = [ConversationMessage.from_user_text(user_content)]

    # inherit 不是真实模型名，需替换为 engine 当前默认模型
    actual_model = model if model and model != "inherit" else engine.model

    request = ApiMessageRequest(
        model=actual_model,
        messages=messages,
        system_prompt=AGENT_CREATION_SYSTEM_PROMPT,
        max_tokens=engine.max_tokens,
        tools=[],
        effort=None,
    )

    chunks: list[str] = []
    async for event in engine.api_client.stream_message(request):  # type: ignore[attr-defined]
        text = getattr(event, "text", None)
        if text:
            chunks.append(text)

    raw_text = "".join(chunks).strip()
    json_text = _extract_json(raw_text)

    try:
        data = json.loads(json_text)
    except json.JSONDecodeError as exc:
        raise ValueError(
            f"LLM 返回的内容不是有效的 JSON: {exc}\n内容: {raw_text}"
        ) from exc

    identifier = str(data.get("identifier", "")).strip()
    when_to_use = str(data.get("whenToUse", "")).strip()
    system_prompt_text = str(data.get("systemPrompt", "")).strip()

    if not identifier or not when_to_use or not system_prompt_text:
        raise ValueError(
            f"LLM 返回的 JSON 缺少必需字段 (identifier/whenToUse/systemPrompt): {raw_text}"
        )

    return GeneratedAgent(
        identifier=identifier,
        when_to_use=when_to_use,
        system_prompt=system_prompt_text,
    )


def list_available_models(
    app_state: AppStateStore | None = None,
) -> list[dict[str, str]]:
    """返回可用模型列表。

    列表包含 ``inherit``（继承默认模型）以及 settings 中配置的所有模型。

    Args:
        app_state: 应用状态（保留参数，当前未使用）

    Returns:
        list[dict[str, str]]: 模型信息列表，每项包含 ``name`` 和 ``label``
    """
    del app_state  # 预留
    models: list[dict[str, str]] = [
        {"name": "inherit", "label": "继承默认模型"}
    ]
    try:
        from illusion.config.settings import load_settings

        settings = load_settings()
        for env_key, env in settings.list_envs().items():
            for model_key, model_name in env.list_models().items():
                models.append(
                    {
                        "name": model_name,
                        "label": f"{env_key}.{model_key} ({model_name})",
                    }
                )
    except Exception as exc:  # noqa: BLE001
        logger.debug("列出可用模型失败: %s", exc)

    return models


def list_available_tools(
    tool_registry: ToolRegistry | None = None,
) -> list[dict[str, str]]:
    """返回可用工具列表。

    Args:
        tool_registry: 工具注册表，为 None 时返回空列表

    Returns:
        list[dict[str, str]]: 工具信息列表，每项包含 ``name`` 和 ``description``
    """
    if tool_registry is None:
        return []

    tools: list[dict[str, str]] = []
    for tool in tool_registry.list_tools():
        tools.append(
            {
                "name": tool.name,
                "description": tool.description,
            }
        )
    return tools
