# src/illusion/daemon_ipc.py
"""守护进程 IPC 层
==================

跨平台的守护进程间通信（IPC）模块。

用 Named Pipe (Windows) / Unix Socket (Unix) 替代 PID 文件 + refs 文件，
从根本上消除 PID 复用和残留文件问题。

核心设计：
    - DaemonServer: 守护进程侧，创建 pipe/socket，accept 连接，跟踪连接数
    - DaemonClient: 主程序侧，connect 到 pipe/socket，持有连接作为引用
    - 连接数 = 引用计数：所有主程序退出 → 连接归零 → 守护进程退出
    - 健康检查：Client 发 ping，Server 回 pong（含 daemon_pid）
    - 指纹检查：Client register 时发送指纹，Server 对比后回 ok/restart_required

协议：JSON 行协议（每行一个 JSON 消息，以 \\n 分隔）
    Client → {"type":"register","pid":1234,"fingerprint":"abc123"}
    Server → {"type":"ok"} 或 {"type":"restart_required"}
    Client → {"type":"ping"}
    Server → {"type":"pong","daemon_pid":5678,"channels":{...}}
"""
from __future__ import annotations

import asyncio
import json
import logging
import os
from enum import Enum
from typing import Callable

logger = logging.getLogger(__name__)

_IS_WINDOWS = os.name == "nt"


class DaemonType(Enum):
    """守护进程类型"""
    CRON = "cron"
    CHANNEL = "channel"


class DaemonClientRef:
    """线程安全的 DaemonClient 引用容器

    用于异步连接场景：spawn 守护进程后立即返回，后台线程轮询连接。
    连接成功后调用 set() 持有 client；主程序退出时调用 close() 关闭连接。

    线程安全：内部用 threading.Lock 保护。
    """

    def __init__(self) -> None:
        self._client: "DaemonClient | None" = None
        import threading
        self._lock = threading.Lock()

    def set(self, client: "DaemonClient") -> None:
        """设置 client（如果已有则关闭新的）"""
        with self._lock:
            if self._client is None:
                self._client = client
            else:
                # 已有 client（可能主程序多次调用），关闭多余的
                close_client(client)

    def close(self) -> None:
        """关闭 client（线程安全）"""
        with self._lock:
            if self._client is not None:
                close_client(self._client)
                self._client = None


# 默认 pipe/socket 名称
def _default_pipe_name(daemon_type: DaemonType) -> str:
    """获取默认的 pipe/socket 名称"""
    if _IS_WINDOWS:
        return f"\\\\.\\pipe\\illusion_{daemon_type.value}"
    else:
        from illusion.config.paths import get_cron_dir, get_channels_data_dir
        if daemon_type == DaemonType.CRON:
            return str(get_cron_dir() / "cron_daemon.sock")
        else:
            return str(get_channels_data_dir() / "channel_daemon.sock")


def _get_channel_status_provider() -> Callable[[], dict] | None:
    """获取渠道状态提供器（延迟导入避免循环依赖）"""
    try:
        from illusion.channels.serve import get_channel_status
        return get_channel_status
    except ImportError:
        return None


# ─── Windows Named Pipe 底层操作 ───

if _IS_WINDOWS:
    import ctypes
    from ctypes import wintypes

    _kernel32 = ctypes.windll.kernel32

    # 64-bit Windows + 64-bit Python 下 ctypes.windll 函数默认返回 c_int（32 位），
    # 会截断 CreateNamedPipeW / CreateFileW 返回的 64 位 HANDLE 值。
    # 必须显式设置 restype，避免句柄被截断。
    _kernel32.CreateNamedPipeW.restype = wintypes.HANDLE
    _kernel32.CreateFileW.restype = wintypes.HANDLE
    _kernel32.CloseHandle.restype = wintypes.BOOL
    _kernel32.ConnectNamedPipe.restype = wintypes.BOOL
    _kernel32.ReadFile.restype = wintypes.BOOL
    _kernel32.WriteFile.restype = wintypes.BOOL
    _kernel32.GetLastError.restype = wintypes.DWORD

    # Win32 常量
    _PIPE_ACCESS_DUPLEX = 0x00000003
    _PIPE_TYPE_BYTE = 0x00000000
    # PIPE_WAIT = 0x00000000：阻塞模式是默认行为，不是 flag 位。
    # （brief 误用 0x00000080，会令 dwPipeMode 出现未定义位 → ERROR_INVALID_PARAMETER 87）
    _PIPE_WAIT = 0x00000000
    _PIPE_UNLIMITED_INSTANCES = 255
    _INVALID_HANDLE_VALUE = ctypes.c_void_p(-1).value
    _GENERIC_READ = 0x80000000
    _GENERIC_WRITE = 0x40000000
    _OPEN_EXISTING = 3
    _ERROR_PIPE_CONNECTED = 535
    _ERROR_PIPE_NOT_CONNECTED = 233

    def _win_create_pipe(name: str) -> int:
        """创建 Named Pipe 实例（服务端）"""
        handle = _kernel32.CreateNamedPipeW(
            name,
            _PIPE_ACCESS_DUPLEX,
            _PIPE_TYPE_BYTE | _PIPE_WAIT,
            _PIPE_UNLIMITED_INSTANCES,
            65536, 65536, 0, None,
        )
        if handle == _INVALID_HANDLE_VALUE or handle == 0:
            err = _kernel32.GetLastError()
            raise OSError(f"CreateNamedPipe failed: error={err}")
        return handle

    def _win_connect_pipe(handle: int) -> bool:
        """等待客户端连接（阻塞）"""
        result = _kernel32.ConnectNamedPipe(handle, None)
        if result == 0:
            err = _kernel32.GetLastError()
            if err == _ERROR_PIPE_CONNECTED:
                return True  # 客户端已连接
            return False
        return True

    def _win_read_pipe(handle: int, size: int = 65536) -> bytes:
        """从 pipe 读取数据（阻塞）"""
        buf = ctypes.create_string_buffer(size)
        bytes_read = wintypes.DWORD()
        success = _kernel32.ReadFile(
            handle, buf, size, ctypes.byref(bytes_read), None
        )
        if success == 0:
            err = _kernel32.GetLastError()
            raise OSError(f"ReadFile failed: error={err}")
        return buf.raw[:bytes_read.value]

    def _win_write_pipe(handle: int, data: bytes) -> int:
        """写入 pipe（阻塞）"""
        bytes_written = wintypes.DWORD()
        success = _kernel32.WriteFile(
            handle, data, len(data), ctypes.byref(bytes_written), None
        )
        if success == 0:
            err = _kernel32.GetLastError()
            raise OSError(f"WriteFile failed: error={err}")
        return bytes_written.value

    def _win_connect_to_pipe(name: str) -> int | None:
        """客户端连接到 Named Pipe，失败返回 None"""
        handle = _kernel32.CreateFileW(
            name,
            _GENERIC_READ | _GENERIC_WRITE,
            0, None,
            _OPEN_EXISTING,
            0, None,
        )
        if handle == _INVALID_HANDLE_VALUE or handle == 0:
            err = _kernel32.GetLastError()
            logger.debug("连接 Named Pipe 失败: %s, error=%d", name, err)
            return None
        return handle

    def _win_close_handle(handle: int) -> None:
        """关闭句柄"""
        _kernel32.CloseHandle(handle)


# ─── 连接抽象 ───

class _BaseConnection:
    """连接抽象基类"""

    async def read_line(self) -> str | None:
        """读取一行 JSON，连接关闭返回 None"""
        raise NotImplementedError

    async def write_line(self, line: str) -> None:
        """写入一行 JSON"""
        raise NotImplementedError

    async def close(self) -> None:
        """关闭连接"""
        raise NotImplementedError


if _IS_WINDOWS:
    class _WindowsPipeConnection(_BaseConnection):
        """Windows Named Pipe 连接（用 asyncio.to_thread 包装阻塞调用）"""

        def __init__(self, handle: int) -> None:
            self._handle = handle
            self._read_buf = b""
            self._closed = False

        async def read_line(self) -> str | None:
            """读取一行（以 \\n 结尾），连接关闭返回 None"""
            while b"\n" not in self._read_buf:
                if self._closed:
                    return None
                try:
                    chunk = await asyncio.to_thread(_win_read_pipe, self._handle, 4096)
                except OSError:
                    self._closed = True
                    return None
                if not chunk:
                    self._closed = True
                    return None
                self._read_buf += chunk
            idx = self._read_buf.index(b"\n")
            line = self._read_buf[:idx]
            self._read_buf = self._read_buf[idx + 1:]
            return line.decode("utf-8")

        async def write_line(self, line: str) -> None:
            """写入一行"""
            data = (line + "\n").encode("utf-8")
            try:
                await asyncio.to_thread(_win_write_pipe, self._handle, data)
            except OSError:
                self._closed = True
                raise

        async def close(self) -> None:
            """关闭连接"""
            if not self._closed:
                self._closed = True
                try:
                    _win_close_handle(self._handle)
                except Exception:  # noqa: BLE001
                    pass

else:
    class _UnixSocketConnection(_BaseConnection):
        """Unix Socket 连接"""

        def __init__(
            self,
            reader: asyncio.StreamReader,
            writer: asyncio.StreamWriter,
        ) -> None:
            self._reader = reader
            self._writer = writer

        async def read_line(self) -> str | None:
            """读取一行，连接关闭返回 None"""
            try:
                data = await self._reader.readline()
            except (ConnectionResetError, asyncio.IncompleteReadError):
                return None
            if not data:
                return None
            return data.decode("utf-8").strip()

        async def write_line(self, line: str) -> None:
            """写入一行"""
            self._writer.write((line + "\n").encode("utf-8"))
            await self._writer.drain()

        async def close(self) -> None:
            """关闭连接"""
            self._writer.close()
            try:
                await self._writer.wait_closed()
            except Exception:  # noqa: BLE001
                pass


# ─── DaemonServer ───

class DaemonServer:
    """守护进程 IPC 服务端

    创建 pipe/socket 并 accept 连接，跟踪活跃连接数。
    连接数归零时可通过 wait_for_no_connections 触发守护进程退出。

    Attributes:
        daemon_type: 守护进程类型
        daemon_pid: 守护进程 PID（用于 pong 响应）
        pipe_name: pipe/socket 名称
        fingerprint: 配置指纹（仅渠道守护进程需要，None 表示不检查）
    """

    def __init__(
        self,
        daemon_type: DaemonType,
        daemon_pid: int,
        pipe_name: str | None = None,
        fingerprint: str | None = None,
        on_reload: Callable[[], None] | None = None,
    ) -> None:
        self._daemon_type = daemon_type
        self._daemon_pid = daemon_pid
        self._pipe_name = pipe_name or _default_pipe_name(daemon_type)
        self._fingerprint = fingerprint
        self._on_reload = on_reload
        self._connections: set[_BaseConnection] = set()
        self._client_tasks: set[asyncio.Task[None]] = set()
        self._stop = False
        # 是否曾有客户端连接过（防止启动竞态：守护进程刚启动时还没有客户端连接，
        # wait_for_no_connections 不应在此时判定"连接归零"而退出）
        self._had_connection = False
        self._accept_task: asyncio.Task[None] | None = None
        self._unix_server: asyncio.Server | None = None
        # Windows: 预创建的 pipe 句柄（由 accept loop 消费）
        self._pending_pipe_handle: int | None = None

    @property
    def connection_count(self) -> int:
        """当前活跃连接数"""
        return len(self._connections)

    async def start(self) -> None:
        """启动服务端，开始 accept 连接"""
        if _IS_WINDOWS:
            # 预创建首个 pipe 实例（同步），避免 client 在 accept loop 创建 pipe 前连接
            # 导致 ERROR_FILE_NOT_FOUND 的竞态。
            first_handle = await asyncio.to_thread(_win_create_pipe, self._pipe_name)
            self._pending_pipe_handle = first_handle
            self._accept_task = asyncio.create_task(self._windows_accept_loop())
        else:
            # Unix: 先清理残留 socket 文件
            try:
                os.unlink(self._pipe_name)
            except FileNotFoundError:
                pass
            self._unix_server = await asyncio.start_unix_server(
                self._handle_unix_client, path=self._pipe_name
            )
            # 设置 socket 文件权限为 0600（仅属主可读写）
            try:
                os.chmod(self._pipe_name, 0o600)
            except OSError:
                pass
            logger.debug("DaemonServer 监听: %s", self._pipe_name)

    async def stop(self) -> None:
        """停止服务端，关闭所有连接"""
        self._stop = True
        if _IS_WINDOWS:
            # 关闭预创建但未被消费的 pipe 句柄
            # （此句柄尚未传入 ConnectNamedPipe，CloseHandle 安全）
            if self._pending_pipe_handle is not None:
                _win_close_handle(self._pending_pipe_handle)
                self._pending_pipe_handle = None
            # Windows: accept loop 阻塞在 ConnectNamedPipe（在线程中执行），
            # asyncio.to_thread 无法中断线程，CloseHandle 也无法解除阻塞。
            # 唯一方法是以客户端身份连接 pipe 唤醒线程。
            # 需重试：accept loop 可能正介于两次迭代之间（pipe 尚未创建），
            # 此时假连接返回 None，等 accept loop 创建 pipe 后重试即可成功。
            if self._accept_task is not None and not self._accept_task.done():
                for _ in range(20):  # 最多重试 20 × 50ms = 1s
                    try:
                        fake_handle = await asyncio.to_thread(
                            _win_connect_to_pipe, self._pipe_name
                        )
                        if fake_handle is not None:
                            _win_close_handle(fake_handle)
                    except Exception:  # noqa: BLE001
                        pass
                    await asyncio.sleep(0.05)  # 让 accept loop 有时间处理
                    if self._accept_task.done():
                        break
        if self._accept_task:
            self._accept_task.cancel()
            try:
                await self._accept_task
            except asyncio.CancelledError:
                pass
        if self._unix_server:
            self._unix_server.close()
            await self._unix_server.wait_closed()
        # 关闭所有活跃连接
        for conn in list(self._connections):
            await conn.close()
        self._connections.clear()

    async def _windows_accept_loop(self) -> None:
        """Windows Named Pipe accept 循环"""
        while not self._stop:
            # 优先消费 start() 预创建的 pipe 句柄（避免竞态）
            if self._pending_pipe_handle is not None:
                handle = self._pending_pipe_handle
                self._pending_pipe_handle = None
            else:
                try:
                    handle = await asyncio.to_thread(_win_create_pipe, self._pipe_name)
                except OSError as exc:
                    logger.error("创建 Named Pipe 失败: %s", exc)
                    await asyncio.sleep(1)
                    continue
            # 等待客户端连接（阻塞，在线程中执行）
            # stop() 会以客户端身份连接 pipe 来唤醒此阻塞
            try:
                connected = await asyncio.to_thread(_win_connect_pipe, handle)
            except asyncio.CancelledError:
                _win_close_handle(handle)
                raise
            except Exception as exc:  # noqa: BLE001
                logger.warning("accept 连接异常: %s", exc)
                _win_close_handle(handle)
                continue
            if connected and not self._stop:
                conn = _WindowsPipeConnection(handle)
                self._connections.add(conn)
                self._had_connection = True
                task = asyncio.create_task(self._handle_client(conn))
                self._client_tasks.add(task)
                task.add_done_callback(self._client_tasks.discard)
            else:
                # 未连接或已停止：关闭句柄
                _win_close_handle(handle)

    async def _handle_unix_client(
        self,
        reader: asyncio.StreamReader,
        writer: asyncio.StreamWriter,
    ) -> None:
        """Unix Socket 客户端处理"""
        conn = _UnixSocketConnection(reader, writer)
        self._connections.add(conn)
        self._had_connection = True
        await self._handle_client(conn)

    async def _handle_client(self, conn: _BaseConnection) -> None:
        """处理客户端连接：读取消息，响应 ping/register"""
        try:
            while not self._stop:
                line = await conn.read_line()
                if line is None:
                    break  # 客户端断开
                try:
                    msg = json.loads(line)
                except json.JSONDecodeError:
                    continue
                resp = self._handle_message(msg)
                if resp is not None:
                    try:
                        await conn.write_line(json.dumps(resp))
                    except OSError:
                        break  # 写入失败，客户端已断开
        finally:
            self._connections.discard(conn)
            await conn.close()

    def _handle_message(self, msg: dict) -> dict | None:
        """处理消息，返回响应"""
        msg_type = msg.get("type")
        if msg_type == "ping":
            return {
                "type": "pong",
                "daemon_pid": self._daemon_pid,
                "connections": self.connection_count,
                "channels": self._get_channel_status(),
            }
        elif msg_type == "register":
            # 指纹检查（仅渠道守护进程）
            if self._fingerprint is not None:
                client_fp = msg.get("fingerprint")
                if client_fp != self._fingerprint:
                    return {"type": "restart_required"}
            return {"type": "ok"}
        elif msg_type == "reload":
            # 通知守护进程重新加载配置（如主程序 /model 切换模型后）
            if self._on_reload is not None:
                try:
                    self._on_reload()
                except Exception as exc:  # noqa: BLE001
                    logger.warning("reload 回调异常: %s", exc)
                    return {"type": "error", "message": str(exc)}
            return {"type": "ok"}
        return None

    def _get_channel_status(self) -> dict:
        """获取渠道状态（用于 pong 响应）"""
        provider = _get_channel_status_provider()
        if provider is not None:
            try:
                return provider()
            except Exception:  # noqa: BLE001
                pass
        return {}

    async def wait_for_no_connections(
        self, grace_seconds: float = 3.0
    ) -> None:
        """等待所有连接断开

        连接归零后等 grace_seconds 宽限期，仍为空则返回。
        用于守护进程判断是否该退出。

        注意：守护进程刚启动时还没有客户端连接，不能立即判定"连接归零"。
        先等待首个客户端连接（_had_connection），再进入连接归零检查。
        """
        # 阶段 1：等待首个客户端连接（无超时，防止启动竞态）
        while not self._stop and not self._had_connection:
            await asyncio.sleep(0.5)
        # 阶段 2：等待所有连接断开（带宽限期）
        while not self._stop:
            if self.connection_count == 0:
                # 宽限期：等 grace_seconds 后再次检查
                await asyncio.sleep(grace_seconds)
                if self.connection_count == 0:
                    return
            else:
                await asyncio.sleep(0.5)


# ─── DaemonClient ───

class DaemonClient:
    """守护进程 IPC 客户端

    连接到 DaemonServer，持有连接作为引用计数。
    进程退出时 OS 自动关闭连接，守护进程检测到后退出。

    Attributes:
        daemon_type: 守护进程类型
        pid: 主程序 PID
        fingerprint: 配置指纹（仅渠道守护进程需要）
    """

    def __init__(
        self,
        daemon_type: DaemonType,
        pid: int,
        fingerprint: str | None = None,
        pipe_name: str | None = None,
    ) -> None:
        self._daemon_type = daemon_type
        self._pid = pid
        self._fingerprint = fingerprint
        self._pipe_name = pipe_name or _default_pipe_name(daemon_type)
        self._conn: _BaseConnection | None = None
        self._daemon_pid: int | None = None

    @property
    def daemon_pid(self) -> int | None:
        """守护进程 PID（从 pong 响应获取）"""
        return self._daemon_pid

    @property
    def is_connected(self) -> bool:
        """是否已连接"""
        return self._conn is not None

    async def connect(self) -> bool:
        """连接到守护进程

        Returns:
            bool: 连接成功返回 True，守护进程未运行返回 False
        """
        if _IS_WINDOWS:
            return await self._windows_connect()
        else:
            return await self._unix_connect()

    async def _windows_connect(self) -> bool:
        """Windows Named Pipe 连接"""
        try:
            handle = await asyncio.to_thread(
                _win_connect_to_pipe, self._pipe_name
            )
        except OSError:
            return False
        if handle is None:
            return False
        self._conn = _WindowsPipeConnection(handle)
        # 让 server accept loop 有时间处理连接：
        # CreateFileW 连接后，server 端 ConnectNamedPipe（在线程中）才返回，
        # 需等待事件循环调度回调将连接加入 self._connections。
        await asyncio.sleep(0.05)
        return True

    async def _unix_connect(self) -> bool:
        """Unix Socket 连接"""
        try:
            reader, writer = await asyncio.wait_for(
                asyncio.open_unix_connection(self._pipe_name),
                timeout=5.0,
            )
        except (FileNotFoundError, ConnectionRefusedError, asyncio.TimeoutError):
            return False
        self._conn = _UnixSocketConnection(reader, writer)
        return True

    async def register(self) -> dict:
        """发送 register 消息，获取响应

        Returns:
            dict: {"type":"ok"} 或 {"type":"restart_required"}
        """
        if self._conn is None:
            raise RuntimeError("未连接")
        msg = {"type": "register", "pid": self._pid}
        if self._fingerprint is not None:
            msg["fingerprint"] = self._fingerprint
        await self._conn.write_line(json.dumps(msg))
        line = await asyncio.wait_for(self._conn.read_line(), timeout=5.0)
        if line is None:
            raise ConnectionError("连接关闭")
        return json.loads(line)

    async def ping(self, timeout: float = 10.0) -> dict | None:
        """发送 ping，等待 pong

        Args:
            timeout: 超时秒数

        Returns:
            dict: pong 响应，超时返回 None
        """
        if self._conn is None:
            return None
        try:
            await self._conn.write_line(json.dumps({"type": "ping"}))
            line = await asyncio.wait_for(self._conn.read_line(), timeout=timeout)
        except (OSError, asyncio.TimeoutError):
            return None
        if line is None:
            return None
        try:
            resp = json.loads(line)
            if resp.get("type") == "pong":
                self._daemon_pid = resp.get("daemon_pid")
            return resp
        except json.JSONDecodeError:
            return None

    async def reload(self, timeout: float = 5.0) -> dict | None:
        """发送 reload 消息，通知守护进程重新加载配置

        用于主程序 /model 切换模型后通知守护进程刷新 settings.json。

        Args:
            timeout: 超时秒数

        Returns:
            dict: 响应字典（{"type":"ok"} 或 {"type":"error",...}），失败返回 None
        """
        if self._conn is None:
            return None
        try:
            await self._conn.write_line(json.dumps({"type": "reload"}))
            line = await asyncio.wait_for(self._conn.read_line(), timeout=timeout)
        except (OSError, asyncio.TimeoutError):
            return None
        if line is None:
            return None
        try:
            return json.loads(line)
        except json.JSONDecodeError:
            return None

    async def close(self) -> None:
        """关闭连接"""
        if self._conn is not None:
            await self._conn.close()
            self._conn = None


# ─── 同步辅助函数 ───
# 以下函数封装了 DaemonClient 的异步操作，在同一个事件循环中完成，
# 避免 Unix 上 StreamWriter 绑定到已关闭的 loop 导致 drain() 失败。


def connect_and_register(client: "DaemonClient") -> tuple[bool, dict | None]:
    """在同一个事件循环中完成 connect + register

    Args:
        client: DaemonClient 实例

    Returns:
        tuple: (是否连接成功, register 响应)
        - 连接失败: (False, None)
        - 连接成功但 register 异常: (True, {"type": "ok"})
        - 连接成功且 register 成功: (True, 响应字典)
    """
    import asyncio

    async def _do() -> tuple[bool, dict | None]:
        connected = await client.connect()
        if not connected:
            return False, None
        try:
            resp = await client.register()
        except Exception:  # noqa: BLE001
            resp = {"type": "ok"}
        return True, resp

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do())
    finally:
        loop.close()


def close_client(client: "DaemonClient") -> None:
    """在独立事件循环中关闭 IPC 连接

    Args:
        client: DaemonClient 实例
    """
    import asyncio

    loop = asyncio.new_event_loop()
    try:
        loop.run_until_complete(client.close())
    except Exception:  # noqa: BLE001
        pass
    finally:
        loop.close()


def ping_daemon(client: "DaemonClient", timeout: float = 2.0) -> dict | None:
    """在独立事件循环中 ping 守护进程

    Args:
        client: DaemonClient 实例
        timeout: 超时秒数

    Returns:
        dict: pong 响应，失败返回 None
    """
    import asyncio

    async def _do() -> dict | None:
        connected = await client.connect()
        if not connected:
            return None
        try:
            return await client.ping(timeout=timeout)
        finally:
            await client.close()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do())
    finally:
        loop.close()


def notify_channel_daemon_reload() -> bool:
    """通知渠道守护进程重新加载 settings.json

    创建临时 DaemonClient，连接守护进程并发送 reload 消息。
    用于主程序 /model 命令切换模型后通知守护进程刷新配置。
    守护进程未运行时静默返回 False（无需 reload）。

    Returns:
        bool: 通知成功返回 True，守护进程未运行或通知失败返回 False
    """
    import asyncio

    async def _do() -> bool:
        client = DaemonClient(
            daemon_type=DaemonType.CHANNEL,
            pid=os.getpid(),
        )
        connected = await client.connect()
        if not connected:
            return False
        try:
            resp = await client.reload()
            return resp is not None and resp.get("type") == "ok"
        finally:
            await client.close()

    loop = asyncio.new_event_loop()
    try:
        return loop.run_until_complete(_do())
    except Exception:  # noqa: BLE001
        return False
    finally:
        loop.close()
