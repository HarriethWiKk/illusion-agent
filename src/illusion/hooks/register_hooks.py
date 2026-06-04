"""
Frontmatter 钩子注册
====================

从 agent/skill 的 frontmatter 中注册会话钩子。
对齐 Claude Code 的 registerFrontmatterHooks.ts 和 registerSkillHooks.ts。
"""

from __future__ import annotations

from illusion.hooks.events import HookEvent, resolve_event
from illusion.hooks.schemas import HookMatcherDefinition
from illusion.hooks.session_hooks import SessionHookStore


def register_frontmatter_hooks(
    store: SessionHookStore,
    session_id: str,
    hooks_settings: dict[str, list[HookMatcherDefinition]],
    source_name: str,
    is_agent: bool = False,
) -> None:
    """从 frontmatter 注册钩子到会话。

    当 is_agent=True 时，将 Stop 事件转换为 SubagentStop（因为子代理触发的是 SubagentStop）。
    """
    for event_name, matchers in hooks_settings.items():
        event = resolve_event(event_name)
        if event is None:
            continue
        target_event = event
        if is_agent and event == HookEvent.STOP:
            target_event = HookEvent.SUBAGENT_STOP
        for matcher_def in matchers:
            for hook in matcher_def.hooks:
                store.add(session_id, target_event, matcher_def.matcher, hook)


def register_skill_hooks(
    store: SessionHookStore,
    session_id: str,
    hooks_settings: dict[str, list[HookMatcherDefinition]],
    skill_name: str,
    skill_root: str | None = None,
) -> None:
    """从 skill frontmatter 注册钩子到会话。

    对齐 Claude Code 的 registerSkillHooks.ts。
    """
    for event_name, matchers in hooks_settings.items():
        event = resolve_event(event_name)
        if event is None:
            continue
        for matcher_def in matchers:
            for hook in matcher_def.hooks:
                store.add(session_id, event, matcher_def.matcher, hook, skill_root=skill_root)
