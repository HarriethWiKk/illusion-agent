"""
Textual 终端 UI 模块
==================

本模块实现基于 Textual 框架的默认终端用户界面。

主要功能：
    - 交互式对话界面（Transcript 显示对话历史）
    - 实时流式输出（Assistant 输出流式显示）
    - 工具执行状态显示
    - 侧边栏（状态、任务、MCP 服务器信息）
    - 权限确认对话框（PermissionScreen）
    - 用户问答对话框（QuestionScreen）

类说明：
    - AppConfig: 终端应用配置数据类
    - PermissionScreen: 权限确认模态对话框
    - QuestionScreen: 用户问答模态对话框
    - illusionTerminalApp: 主终端应用类

使用示例：
    >>> from illusion.ui.textual_app import illusionTerminalApp
    >>> app = illusionTerminalApp()
    >>> app.run()
"""

from __future__ import annotations

import asyncio
import json
from dataclasses import dataclass
from typing import Any, Coroutine

from rich.panel import Panel
from textual import on
from textual.app import App, ComposeResult
from textual.binding import Binding
from textual.containers import Container, Horizontal, Vertical
from textual.screen import ModalScreen
from textual.widgets import Button, Checkbox, Footer, Header, Input, RadioButton, RadioSet, RichLog, Static

from illusion.api.client import SupportsStreamingMessages
from illusion.engine.stream_events import (
    AssistantTextDelta,
    AssistantTurnComplete,
    ErrorEvent,
    StatusEvent,
    StreamEvent,
    ToolExecutionCompleted,
    ToolExecutionStarted,
)
from illusion.swarm.agent_executor import list_active_agents
from illusion.tasks import get_task_manager
from illusion.tasks.types import to_task_display_status
from illusion.ui.runtime import RuntimeBundle, build_runtime, close_runtime, handle_line, start_runtime

# Agent 状态指示器颜色（与 agent_definitions.py 中的 AGENT_COLORS 一致）
_AGENT_INDICATOR_COLOR = "purple"


@dataclass(frozen=True)
class AppConfig:
    """终端应用配置数据类。

    用于存储终端应用会话的配置参数。

    Attributes:
        prompt: 初始用户提示词
        model: 使用的模型名称
        base_url: API 基础 URL
        system_prompt: 系统提示词
        api_key: API 密钥
        api_client: 流式 API 客户端实例
    """

    prompt: str | None = None
    model: str | None = None
    base_url: str | None = None
    system_prompt: str | None = None
    api_key: str | None = None
    api_client: SupportsStreamingMessages | None = None


class PermissionScreen(ModalScreen[bool]):
    """权限确认模态对话框。

    当工具需要用户确认时显示此对话框，让用户决定是否允许执行该工具。
    支持快捷键：Y=允许，N=拒绝，Escape=拒绝。

    Attributes:
        _tool_name: 请求执行的工具名称
        _reason: 工具请求的原因说明
    """

    BINDINGS = [
        Binding("escape", "deny", "Deny"),
        Binding("y", "allow", "Allow"),
        Binding("n", "deny", "Deny"),
    ]

    def __init__(self, tool_name: str, reason: str) -> None:
        super().__init__()
        self._tool_name = tool_name  # 存储工具名称
        self._reason = reason    # 存储原因说明

    def compose(self) -> ComposeResult:
        yield Container(
            Static(
                Panel.fit(
                    f"Allow tool [bold]{self._tool_name}[/bold]?\n\n{self._reason}",
                    title="Permission Required",
                )
            ),
            Horizontal(
                Button("Allow", id="allow", variant="success"),
                Button("Deny", id="deny", variant="error"),
                classes="permission-actions",
            ),
            id="permission-dialog",
        )

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        # 根据按钮ID决定是否允许：allow=True, deny=False
        self.dismiss(event.button.id == "allow")

    def action_allow(self) -> None:
        self.dismiss(True)  # 允许执行

    def action_deny(self) -> None:
        self.dismiss(False)  # 拒绝执行


class QuestionScreen(ModalScreen[Any]):
    """用户问答模态对话框。

    支持两种模式：
    - 结构化模式：当提供 questions 数据时，渲染单选(RadioSet)/多选(Checkbox)UI
    - 文本模式：无结构化数据时，回退为文本输入框
    """

    BINDINGS = [
        Binding("escape", "cancel", "Cancel"),
        # Enter 不再全局绑定提交。多选时 Space 切换，Tab 到 Submit 按钮后回车提交。
    ]

    def __init__(self, question: str, questions_data: list[Any] | None = None) -> None:
        super().__init__()
        self._question = question
        self._questions_data: list[dict[str, Any]] = []
        if questions_data:
            self._questions_data = [
                q.model_dump() if hasattr(q, "model_dump") else q
                for q in questions_data
            ]

    def compose(self) -> ComposeResult:
        if self._questions_data:
            yield from self._compose_structured()
        else:
            yield from self._compose_fallback()

    def _compose_fallback(self) -> ComposeResult:
        """文本输入模式（兼容旧行为）"""
        yield Container(
            Static(Panel.fit(self._question, title="Question")),
            Input(placeholder="Type your answer", id="question-input"),
            Horizontal(
                Button("Submit", id="submit", variant="primary"),
                Button("Cancel", id="cancel", variant="default"),
                classes="permission-actions",
            ),
            id="permission-dialog",
        )

    def _compose_structured(self) -> ComposeResult:
        """结构化选项模式：单选用 RadioSet，多选用 Checkbox"""
        with Container(id="permission-dialog"):
            for i, q in enumerate(self._questions_data):
                header = q.get("header", "")
                question_text = q.get("question", "")
                options: list[dict[str, Any]] = q.get("options", [])
                multi: bool = q.get("multiSelect", False)

                title = f"[{header}] {question_text}" if header else question_text
                yield Static(title, classes="question-title")
                yield Static("─" * 40, classes="question-separator")

                if multi:
                    for j, opt in enumerate(options):
                        desc = opt.get("description", "")
                        label = f"{opt['label']} — {desc}" if desc else opt["label"]
                        yield Checkbox(label, id=f"q_{i}_opt_{j}", classes="question-option")
                else:
                    with RadioSet(id=f"q_{i}", classes="question-radioset"):
                        for j, opt in enumerate(options):
                            desc = opt.get("description", "")
                            label = f"{opt['label']} — {desc}" if desc else opt["label"]
                            yield RadioButton(label, id=f"q_{i}_opt_{j}")
                yield Static("")

            yield Horizontal(
                Button("Submit", id="submit", variant="primary"),
                Button("Cancel", id="cancel", variant="default"),
                classes="permission-actions",
            )
            yield Static(
                "空格=选中/取消   Tab=切换选项   聚焦[提交]后回车=确认   Esc=取消",
                classes="question-hint",
            )

    def on_mount(self) -> None:
        if not self._questions_data:
            self.query_one("#question-input", Input).focus()

    @on(Button.Pressed)
    def handle_button_press(self, event: Button.Pressed) -> None:
        if event.button.id == "cancel":
            self.dismiss("")
            return
        if self._questions_data:
            self.dismiss(self._collect_structured_answers())
        else:
            self.dismiss(self.query_one("#question-input", Input).value.strip())

    @on(Input.Submitted, "#question-input")
    def handle_input_submit(self, event: Input.Submitted) -> None:
        self.dismiss(event.value.strip())

    def action_submit(self) -> None:
        if self._questions_data:
            self.dismiss(self._collect_structured_answers())
        else:
            self.dismiss(self.query_one("#question-input", Input).value.strip())

    def action_cancel(self) -> None:
        self.dismiss("")

    def _collect_structured_answers(self) -> dict[str, list[str] | str]:
        """收集结构化问题的用户答案。"""
        result: dict[str, list[str] | str] = {}
        for i, q in enumerate(self._questions_data):
            header = q.get("header", f"q{i}")
            options: list[dict[str, Any]] = q.get("options", [])
            multi: bool = q.get("multiSelect", False)

            if multi:
                selected: list[str] = []
                for j, opt in enumerate(options):
                    cb = self.query_one(f"#q_{i}_opt_{j}", Checkbox)
                    if cb.value:
                        selected.append(opt["label"])
                result[header] = selected
            else:
                rs = self.query_one(f"#q_{i}", RadioSet)
                pressed = rs.pressed_button
                if pressed is not None:
                    try:
                        opt_idx = int(str(pressed.id).rsplit("_", 1)[-1])
                        result[header] = options[opt_idx]["label"]
                    except (ValueError, IndexError):
                        result[header] = str(pressed.label).split(" — ")[0]
                else:
                    result[header] = ""
        return result


class illusionTerminalApp(App[None]):
    """Textual 终端应用程序主类。

    提供基于 Textual 框架的交互式终端用户界面。
    支持快捷键：Ctrl+L 清空对话，Ctrl+R 刷新侧边栏，Ctrl+D 退出。

    Attributes:
        _config: 应用配置参数
        _bundle: 运行时数据bundle
        _assistant_buffer: 助手输出缓冲区（用于流式输出）
        _busy: 当前是否正在处理请求
        transcript_lines: 对话历史记录列表
    """

    # CSS 样式定义 - 终端布局
    CSS = """
    Screen {
        layout: vertical;
    }

    #main-row {
        height: 1fr;
    }

    #transcript-column {
        width: 3fr;
        min-width: 60;
    }

    #side-column {
        width: 1fr;
        min-width: 28;
    }

    #transcript {
        height: 1fr;
        border: solid $accent;
    }

    #current-response {
        min-height: 3;
        max-height: 8;
        border: round $primary;
        padding: 0 1;
    }

    #composer {
        dock: bottom;
        height: 3;
        border: solid $accent;
    }

    #status-bar, #tasks-panel, #mcp-panel {
        border: round $surface;
        padding: 0 1;
        margin-bottom: 1;
    }

    #permission-dialog {
        width: 60;
        height: auto;
        padding: 1 2;
        background: $panel;
        border: round $accent;
    }

    .permission-actions {
        align: center middle;
        height: auto;
        margin-top: 1;
    }
    """

    # 快捷键绑定
    BINDINGS = [
        Binding("ctrl+l", "clear_conversation", "Clear"),       # 清空对话
        Binding("ctrl+r", "refresh_sidebars", "Refresh"),         # 刷新侧边栏
        Binding("ctrl+d", "quit_session", "Exit"),                # 退出会话
    ]

    def __init__(
        self,
        *,
        prompt: str | None = None,
        model: str | None = None,
        base_url: str | None = None,
        system_prompt: str | None = None,
        api_key: str | None = None,
        api_client: SupportsStreamingMessages | None = None,
    ) -> None:
        super().__init__()
        # 初始化应用配置
        self._config = AppConfig(
            prompt=prompt,
            model=model,
            base_url=base_url,
            system_prompt=system_prompt,
            api_key=api_key,
            api_client=api_client,
        )
        self._bundle: RuntimeBundle | None = None                   # 运行时数据bundle
        self._assistant_buffer = ""           # 助手输出缓冲区
        self._busy = False                  # 当前是否正在处理请求
        self.transcript_lines: list[str] = []  # 对话历史
        # fire-and-forget task 强引用集合，防止 GC 抢收
        self._dispatch_tasks: set[asyncio.Task[None]] = set()

    def compose(self) -> ComposeResult:
        """构建界面布局。"""
        yield Header(show_clock=True)  # 显示时钟的标题栏
        with Horizontal(id="main-row"):
            with Vertical(id="transcript-column"):
                # 对话历史显示区域
                yield RichLog(id="transcript", wrap=True, highlight=True, markup=True)
                # 当前响应显示区域
                yield Static("Ready.", id="current-response")
                # 用户输入框
                yield Input(placeholder="Ask illusion or enter a /command", id="composer")
            with Vertical(id="side-column"):
                # 状态栏
                yield Static("Starting...", id="status-bar")
                # 任务面板
                yield Static("No tasks yet.", id="tasks-panel")
                # MCP 服务器面板
                yield Static("No MCP servers configured.", id="mcp-panel")
        yield Footer()

    async def on_mount(self) -> None:
        """应用挂载时初始化运行时。"""
        # 构建运行时环境
        self._bundle = await build_runtime(
            prompt=self._config.prompt,
            model=self._config.model,
            base_url=self._config.base_url,
            system_prompt=self._config.system_prompt,
            api_key=self._config.api_key,
            api_client=self._config.api_client,
            permission_prompt=self._ask_permission,
            ask_user_prompt=self._ask_question,  # type: ignore[arg-type]
        )
        assert self._bundle is not None
        await start_runtime(self._bundle)  # 启动运行时（执行会话开始钩子）
        # 聚焦输入框
        self.query_one("#composer", Input).focus()
        # 刷新侧边栏
        self._refresh_sidebars()
        # 设置定时刷新侧边栏（每秒）
        self.set_interval(1.0, self._refresh_sidebars)
        # 如果有初始提示词，自动执行
        if self._config.prompt:
            self.call_later(
                lambda: self._create_background_task(self._process_line(self._config.prompt or ""))
            )

    def _create_background_task(self, coro: Coroutine[Any, Any, None]) -> asyncio.Task[None]:
        """创建 fire-and-forget task 并保留强引用，防止 GC 抢收。

        Args:
            coro: 要执行的协程

        Returns:
            创建的 task
        """
        task = asyncio.create_task(coro)
        self._dispatch_tasks.add(task)
        task.add_done_callback(self._dispatch_tasks.discard)
        return task

    async def on_unmount(self) -> None:
        """应用卸载时清理资源。"""
        if self._bundle is not None:
            await close_runtime(self._bundle)

    async def _ask_permission(self, tool_name: str, reason: str) -> bool:
        """权限确认回调函数。"""
        return bool(await self._open_modal(PermissionScreen(tool_name, reason)))

    async def _ask_question(self, question: str, questions_data: list[Any] | None = None) -> str | dict[Any, Any]:
        """用户问答回调函数。"""
        result = await self._open_modal(QuestionScreen(question, questions_data))
        if isinstance(result, dict):
            return result  # 结构化答案（含多选 list）
        return str(result)

    async def _open_modal(self, screen: ModalScreen[Any]) -> object:
        """打开模态对话框并等待用户响应。"""
        loop = asyncio.get_running_loop()
        future: asyncio.Future[object] = loop.create_future()

        def _done(result: object) -> None:
            if not future.done():
                future.set_result(result)

        self.push_screen(screen, callback=_done)
        return await future

    @on(Input.Submitted, "#composer")
    async def handle_submit(self, event: Input.Submitted) -> None:
        """处理用户提交输入事件。"""
        event.input.value = ""
        await self._process_line(event.value)

    async def _process_line(self, line: str) -> None:
        """处理用户输入的行内容。"""
        # 空行或无运行时则忽略
        if not line.strip() or self._bundle is None or self._busy:
            return
        self._busy = True  # 设置忙碌状态
        # 获取并禁用输入框
        composer = self.query_one("#composer", Input)
        composer.disabled = True
        # 添加用户输入到对话历史
        self._append_line(f"user> {line}")
        self._set_current_response("[dim]Working...[/dim]")
        try:
            # 处理输入行
            should_continue = await handle_line(
                self._bundle,
                line,
                print_system=self._print_system,
                render_event=self._render_event,
                clear_output=self._clear_transcript,
            )
            self._refresh_sidebars()
            # 如果会话结束则退出
            if not should_continue:
                self.exit()
        finally:
            self._busy = False
            composer.disabled = False
            composer.focus()

    async def _print_system(self, message: str) -> None:
        """打印系统消息。"""
        self._append_line(f"system> {message}")
        self._set_current_response("Ready.")

    async def _render_event(self, event: StreamEvent) -> None:
        """渲染流式事件。"""
        # 助手文本增量事件
        if isinstance(event, AssistantTextDelta):
            self._assistant_buffer += event.text
            self._set_current_response(f"[bold]assistant>[/bold] {self._assistant_buffer}")
            return

        # 助手回合完成事件
        if isinstance(event, AssistantTurnComplete):
            text = self._assistant_buffer or event.message.text or "(empty response)"
            self._append_line(f"assistant> {text}")
            self._assistant_buffer = ""
            self._set_current_response("Ready.")
            return

        # 工具开始执行事件
        if isinstance(event, ToolExecutionStarted):
            payload = json.dumps(event.tool_input, ensure_ascii=False)
            self._append_line(f"tool> {event.tool_name} {payload}")
            return

        # 工具执行完成事件
        if isinstance(event, ToolExecutionCompleted):
            prefix = "tool-error>" if event.is_error else "tool-result>"
            self._append_line(f"{prefix} {event.tool_name}: {event.output}")
            return

        # 错误事件
        if isinstance(event, ErrorEvent):
            self._append_line(f"error> {event.message}")
            self._assistant_buffer = ""
            self._set_current_response("Ready.")
            return
        # 状态事件
        if isinstance(event, StatusEvent):
            self._append_line(f"system> {event.message}")

    def action_clear_conversation(self) -> None:
        """清空对话历史。"""
        if self._bundle is None:
            return
        self._bundle.engine.clear()  # 清空引擎对话历史
        # 清空界面显示
        self.query_one("#transcript", RichLog).clear()
        self.transcript_lines.clear()
        self._set_current_response("Conversation cleared.")
        self._refresh_sidebars()

    def action_refresh_sidebars(self) -> None:
        """刷新侧边栏显示。"""
        self._refresh_sidebars()

    def action_quit_session(self) -> None:
        """退出当前会话。"""
        self.exit()

    def _append_line(self, message: str) -> None:
        """添加一行到对话历史。"""
        self.transcript_lines.append(message)
        self.query_one("#transcript", RichLog).write(message)

    async def _clear_transcript(self) -> None:
        """清空对话显示区域。"""
        self.query_one("#transcript", RichLog).clear()
        self.transcript_lines.clear()

    def _set_current_response(self, message: str) -> None:
        """设置当前响应显示。"""
        self.query_one("#current-response", Static).update(message)

    def _refresh_sidebars(self) -> None:
        """刷新侧边栏信息。"""
        if self._bundle is None:
            return
        # 获取状态信息
        state = self._bundle.app_state.get()
        usage = self._bundle.engine.total_usage
        # 状态栏信息
        agent_count = len(list_active_agents())
        # Agent 状态指示器：使用主题色闪烁
        agent_indicator = ""
        if agent_count > 0:
            import time
            blink = int(time.time() * 2) % 2
            style = f"bold {_AGENT_INDICATOR_COLOR}" if blink else _AGENT_INDICATOR_COLOR
            agent_indicator = f" [{style}]· {agent_count} agent{'s' if agent_count > 1 else ''}[/{style}]"

        status_lines = [
            "[b]Status[/b]",
            f"model: {state.model}{agent_indicator}",
            f"permissions: {state.permission_mode}",
            f"fast: {'on' if state.fast_mode else 'off'}",
            f"language: {state.ui_language}",
            f"style: {state.output_style}",
            f"tokens: {usage.total_tokens}",
            f"messages: {len(self._bundle.engine.messages)}",
        ]
        self.query_one("#status-bar", Static).update("\n".join(status_lines))

        # 获取任务列表
        tasks = get_task_manager().list_tasks()
        if tasks:
            task_lines = ["[b]Tasks[/b]"]
            for task in tasks[:10]:
                suffix: list[str] = []
                if task.metadata.get("progress"):
                    suffix.append(f"{task.metadata['progress']}%")
                if task.metadata.get("status_note"):
                    suffix.append(task.metadata["status_note"])
                detail = f" ({' | '.join(suffix)})" if suffix else ""
                task_lines.append(
                    f"{task.id} {to_task_display_status(task.status)} {task.description}{detail}"
                )
        else:
            task_lines = ["[b]Tasks[/b]", "No background tasks."]
        self.query_one("#tasks-panel", Static).update("\n".join(task_lines))
        # 更新 MCP 服务器面板
        self.query_one("#mcp-panel", Static).update(self._bundle.mcp_summary())
