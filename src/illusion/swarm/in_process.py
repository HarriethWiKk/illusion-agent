"""
进程内代理执行后端模块
=====================

本模块实现进程内的代理执行后端。
使用 :mod:`contextvars` 在当前 Python 进程中将代理作为 asyncio Task 运行，
实现每个代理的上下文隔离。

主要组件：
    - InProcessBackend: 进程内执行后端，实现 TeammateExecutor 协议

使用示例：
    >>> from illusion.swarm.in_process import InProcessBackend
    >>> backend = InProcessBackend()
    >>> result = await backend.spawn(config)
"""

from __future__ import annotations

import asyncio
import contextlib
import logging
import time
import uuid
from dataclasses import dataclass, field

from illusion.swarm.agent_executor import (
    AgentExecutionContext,
    AgentSpawnConfig,
    AgentAbortController,
    set_agent_context,
    _register_agent,
    _unregister_agent,
)
from illusion.swarm.types import (
    BackendType,
    SpawnResult,
    TeammateMessage,
    TeammateSpawnConfig,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# InProcessBackend
# ---------------------------------------------------------------------------


@dataclass
class _AgentEntry:
    """运行中进程内代理的内部注册表条目。"""

    task: asyncio.Task[None]
    abort_controller: AgentAbortController
    task_id: str
    started_at: float = field(default_factory=time.time)


class InProcessBackend:
    """将代理作为当前进程中的 asyncio Task 运行的 TeammateExecutor。"""

    type: BackendType = "in_process"

    def __init__(self) -> None:
        self._active: dict[str, _AgentEntry] = {}

    def is_available(self) -> bool:
        """进程内后端始终可用。"""
        return True

    async def spawn(self, config: TeammateSpawnConfig) -> SpawnResult:
        """将进程内代理生成为 asyncio Task。"""
        agent_id = f"{config.name}@{config.team}"
        task_id = f"in_process_{uuid.uuid4().hex[:12]}"

        # 检查是否已存在活跃的同名代理
        if agent_id in self._active:
            entry = self._active[agent_id]
            if not entry.task.done():
                logger.warning("[InProcessBackend] spawn(): %s is already running", agent_id)
                return SpawnResult(
                    task_id=task_id,
                    agent_id=agent_id,
                    backend_type=self.type,
                    success=False,
                    error=f"Agent {agent_id!r} is already running",
                )

        # 创建中止控制器
        abort_controller = AgentAbortController()

        # 创建代理生成配置
        spawn_config = AgentSpawnConfig(
            name=config.name,
            prompt=config.prompt,
            cwd=config.cwd,
            model=config.model,
            system_prompt=config.system_prompt,
            permission_mode=None,
            parent_session_id=config.parent_session_id,
        )

        # 预先创建并注册执行上下文，以便 send_message 可以立即找到代理
        from illusion.swarm.agent_executor import AgentExecutionContext, _register_agent
        ctx = AgentExecutionContext(
            agent_id=agent_id,
            agent_name=config.name,
            prompt=config.prompt,
            model=config.model,
            cwd=__import__("pathlib").Path(config.cwd),
            abort_controller=abort_controller,
        )
        _register_agent(ctx)

        # 创建 asyncio Task
        task = asyncio.create_task(
            self._run_agent(spawn_config, agent_id, abort_controller, ctx),
            name=f"agent-{agent_id}",
        )

        entry = _AgentEntry(
            task=task,
            abort_controller=abort_controller,
            task_id=task_id,
        )
        self._active[agent_id] = entry

        # 添加完成回调
        def _on_done(t: asyncio.Task[None]) -> None:
            self._active.pop(agent_id, None)
            if not t.cancelled() and t.exception() is not None:
                logger.error("[InProcessBackend] Agent %s raised exception: %s", agent_id, t.exception())

        task.add_done_callback(_on_done)

        logger.debug("[InProcessBackend] spawned %s (task_id=%s)", agent_id, task_id)
        return SpawnResult(
            task_id=task_id,
            agent_id=agent_id,
            backend_type=self.type,
        )

    async def _run_agent(
        self,
        config: AgentSpawnConfig,
        agent_id: str,
        abort_controller: AgentAbortController,
        ctx: AgentExecutionContext | None = None,
    ) -> None:
        """运行代理的内部协程。"""
        if ctx is None:
            ctx = AgentExecutionContext(
                agent_id=agent_id,
                agent_name=config.name,
                prompt=config.prompt,
                model=config.model,
                cwd=__import__("pathlib").Path(config.cwd),
                abort_controller=abort_controller,
            )
            _register_agent(ctx)
        set_agent_context(ctx)

        try:
            # 注意：这里需要 query_context 和 parent_registry
            # 在实际使用中，这些应该通过某种方式传入
            # 目前这是一个占位实现
            logger.info("[InProcessBackend] %s: agent started (stub)", agent_id)
            ctx.status = "running"

            # 等待取消或完成
            while not abort_controller.is_cancelled:
                await asyncio.sleep(0.1)

        except asyncio.CancelledError:
            logger.debug("[InProcessBackend] %s: task cancelled", agent_id)
            raise
        except Exception:
            logger.exception("[InProcessBackend] %s: unhandled exception", agent_id)
        finally:
            ctx.status = "stopped"
            _unregister_agent(agent_id)

    async def send_message(self, agent_id: str, message: TeammateMessage) -> None:
        """向运行中的代理发送消息。"""
        # 首先检查 self._active 中是否有该代理
        entry = self._active.get(agent_id)
        if entry is not None and not entry.task.done():
            # 代理正在运行，但需要找到其 AgentExecutionContext
            # 从全局注册表中查找
            from illusion.swarm.agent_executor import get_active_agent
            agent_ctx = get_active_agent(agent_id)
            if agent_ctx is not None:
                await agent_ctx.message_queue.put(message)  # type: ignore[arg-type]
                logger.debug("[InProcessBackend] sent message to %s", agent_id)
                return

        # 回退：尝试从全局注册表查找
        from illusion.swarm.agent_executor import get_active_agent, get_active_agent_by_name
        agent_name = agent_id.split("@")[0] if "@" in agent_id else agent_id

        agent_ctx = get_active_agent(agent_id)
        if agent_ctx is None:
            agent_ctx = get_active_agent_by_name(agent_name)

        if agent_ctx is not None:
            await agent_ctx.message_queue.put(message)  # type: ignore[arg-type]
            logger.debug("[InProcessBackend] sent message to %s", agent_id)
        else:
            raise ValueError(f"No active agent found for {agent_id!r}")

    async def shutdown(self, agent_id: str, *, force: bool = False, timeout: float = 10.0) -> bool:
        """终止运行中的进程内代理。"""
        entry = self._active.get(agent_id)
        if entry is None:
            logger.debug("[InProcessBackend] shutdown(): %s not found", agent_id)
            return False

        if entry.task.done():
            self._active.pop(agent_id, None)
            return True

        if force:
            entry.abort_controller.request_cancel(reason="force shutdown", force=True)
            entry.task.cancel()
            with contextlib.suppress(asyncio.CancelledError):
                await asyncio.wait_for(asyncio.shield(entry.task), timeout=timeout)
        else:
            entry.abort_controller.request_cancel(reason="graceful shutdown")
            try:
                await asyncio.wait_for(asyncio.shield(entry.task), timeout=timeout)
            except asyncio.TimeoutError:
                logger.warning("[InProcessBackend] %s did not exit within %.1fs — forcing", agent_id, timeout)
                entry.abort_controller.request_cancel(reason="timeout — forcing", force=True)
                entry.task.cancel()
                with contextlib.suppress(asyncio.CancelledError):
                    await entry.task

        self._active.pop(agent_id, None)
        logger.debug("[InProcessBackend] shut down %s", agent_id)
        return True

    def list_agents(self) -> list[tuple[str, bool, float]]:
        """返回 (agent_id, is_running, duration_seconds) 元组列表。"""
        now = time.time()
        result = []
        for agent_id, entry in self._active.items():
            is_running = not entry.task.done()
            duration = now - entry.started_at
            result.append((agent_id, is_running, duration))
        return result

    async def shutdown_all(self, *, force: bool = False, timeout: float = 10.0) -> None:
        """终止所有活跃代理。"""
        agent_ids = list(self._active.keys())
        await asyncio.gather(
            *(self.shutdown(aid, force=force, timeout=timeout) for aid in agent_ids),
            return_exceptions=True,
        )
