"""
技能内容读取工具
================

本模块提供读取已加载技能内容的功能，用于执行斜杠命令和自定义技能。

主要组件：
    - SkillTool: 读取技能内容的工具

使用示例：
    >>> from illusion.tools import SkillTool
    >>> tool = SkillTool()
"""

from __future__ import annotations

from pydantic import BaseModel, Field

from illusion.skills import load_skill_registry
from illusion.tools.base import BaseTool, ToolExecutionContext, ToolResult


class SkillToolInput(BaseModel):
    """技能查找参数。

    属性：
        name: 技能名称
        args: 技能的可选参数
    """

    name: str = Field(description="Skill name")
    args: str | None = Field(default=None, description="Optional arguments for the skill")


class SkillTool(BaseTool):
    """返回已加载技能的内容。

    用于执行斜杠命令（/command）或调用自定义技能。
    """

    name = "skill"
    description = """Load a skill's instructions so you can then execute them yourself.

This tool does NOT execute anything — it only returns the skill's content (instructions, workflows, examples). You must read the returned content and follow it step by step to complete the task.

When users ask you to perform tasks, check if any of the available skills match. Skills provide specialized capabilities and domain knowledge.

When users reference a "slash command" or "/<something>" (e.g., "/commit", "/review-pr"), they are referring to a skill. Use this tool to load its instructions.

How to use:
- Call this tool with the skill name and optional arguments
- The tool returns the skill's instructions — you then execute them
- Examples:
  - `skill: "pdf"` — loads the pdf skill's instructions
  - `skill: "commit", args: "-m 'Fix bug'"` — loads with arguments
  - `skill: "review-pr", args: "123"` — loads with arguments
  - `skill: "ms-office-suite:pdf"` — loads using fully qualified name

Important:
- Available skills are listed in <system-reminder> messages in the conversation
- When a skill matches the user's request, this is a BLOCKING REQUIREMENT: call this Skill tool to load its instructions BEFORE generating any other response about the task
- NEVER mention a skill without actually calling this tool
- Do not load a skill that is already active in the current context
- Do not use this tool for built-in CLI commands (like /help, /clear, etc.)
- If you see a <command-name> tag in the current conversation turn, the skill's instructions have ALREADY been loaded — follow the instructions directly instead of calling this tool again"""
    input_model = SkillToolInput

    def is_read_only(self, arguments: SkillToolInput) -> bool:
        del arguments
        return True

    async def execute(self, arguments: SkillToolInput, context: ToolExecutionContext) -> ToolResult:
        # 加载技能注册表
        registry = load_skill_registry(context.cwd)
        # 尝试多种名称格式匹配
        skill = registry.get(arguments.name) or registry.get(arguments.name.lower()) or registry.get(arguments.name.title())
        if skill is None:
            return ToolResult(output=f"Skill not found: {arguments.name}", is_error=True)

        # 获取技能内容
        content = skill.content
        # 如果提供了参数，替换 $ARGUMENTS 占位符
        if arguments.args and "$ARGUMENTS" in content:
            content = content.replace("$ARGUMENTS", arguments.args)

        return ToolResult(output=content)
