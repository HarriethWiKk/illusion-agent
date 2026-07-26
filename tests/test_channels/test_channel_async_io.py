"""Task 16 测试：渠道 SDK 专用 executor + 大文件 I/O 异步化 + except BaseException 拆分

覆盖 4 个修复模式：
    1. 飞书 SDK 专用 executor 模块级定义且命名正确
    2. 飞书 WS 客户端专用 executor 模块级定义且 max_workers=1
    3. except BaseException 拆分后 CancelledError 正确上抛
    4. 大文件 I/O 通过 asyncio.to_thread 异步化（不阻塞事件循环）
"""
from __future__ import annotations

import asyncio
import inspect
from concurrent.futures import ThreadPoolExecutor
from pathlib import Path

import pytest


# ─── 模式 1 + 2：模块级 executor 检查 ──────────────────────────────


def test_feishu_sdk_executor_is_module_level():
    """_feishu_executor 在 feishu.adapter 模块级定义且属性正确。

    验证：
        - 是 ThreadPoolExecutor 实例
        - max_workers=8（SDK 调用并发上限）
        - thread_name_prefix="feishu-sdk"（便于排查线程 dump）
    """
    from illusion.channels.feishu.adapter import _feishu_executor

    assert isinstance(_feishu_executor, ThreadPoolExecutor)
    # _max_workers 是 ThreadPoolExecutor 的私有属性，CPython 稳定接口
    assert _feishu_executor._max_workers == 8
    assert _feishu_executor._thread_name_prefix == "feishu-sdk"


def test_feishu_ws_executor_is_module_level():
    """_ws_executor 在 feishu.adapter 模块级定义且 max_workers=1。

    WS 客户端 start() 是无限阻塞的，必须独占一个线程。
    """
    from illusion.channels.feishu.adapter import _ws_executor

    assert isinstance(_ws_executor, ThreadPoolExecutor)
    assert _ws_executor._max_workers == 1
    assert _ws_executor._thread_name_prefix == "feishu-ws"


def test_messaging_imports_feishu_executor():
    """messaging.py 从 adapter.py 导入 _feishu_executor 复用，而非重新定义。

    验证 executor 单例：所有飞书相关模块共享同一个线程池。
    """
    from illusion.channels.feishu.adapter import _feishu_executor
    from illusion.channels.feishu.messaging import _feishu_executor as messaging_executor

    assert _feishu_executor is messaging_executor, (
        "messaging.py 必须从 adapter.py 导入 _feishu_executor，不能重新定义"
    )


def test_delivery_imports_feishu_executor():
    """delivery.py 从 adapter.py 导入 _feishu_executor 复用。"""
    from illusion.channels.delivery import _feishu_executor as delivery_executor
    from illusion.channels.feishu.adapter import _feishu_executor

    assert delivery_executor is _feishu_executor


def test_feishu_adapter_no_default_executor_for_ws_start():
    """feishu/adapter.py 的 connect() 用 _ws_executor 而非 None 启动 WS。

    通过源码检查：run_in_executor(None, ...) 不应出现在 WS start 调用附近。
    """
    from illusion.channels.feishu.adapter import FeishuChannel

    source = inspect.getsource(FeishuChannel.connect)
    assert "_ws_executor" in source, "connect() 必须用 _ws_executor 启动 WS"
    # 不应再使用默认 executor（None）跑 WS start
    assert "run_in_executor(None, self._ws.start)" not in source


def test_feishu_adapter_no_asyncio_to_thread_for_sdk_calls():
    """feishu/adapter.py 的 SDK 调用不再用 asyncio.to_thread，改用 loop.run_in_executor。

    检查 send_image / download_attachment 两个方法的源码：
        - 不含 asyncio.to_thread(self._client...) 调用
        - 含 loop.run_in_executor(_feishu_executor, ...) 调用

    send_document 已改为薄壳转发到 messaging.send_file，SDK 调用移至
    messaging 层，由 test_messaging_no_asyncio_to_thread_for_sdk_calls 覆盖。
    """
    from illusion.channels.feishu.adapter import FeishuChannel

    for method_name in ("send_image", "download_attachment"):
        method = getattr(FeishuChannel, method_name)
        source = inspect.getsource(method)
        # SDK 调用不应再用 asyncio.to_thread
        assert "asyncio.to_thread(self._client" not in source, (
            f"{method_name} 不应再用 asyncio.to_thread 包装 SDK 调用"
        )
        # 应使用 _feishu_executor
        assert "_feishu_executor" in source, (
            f"{method_name} 应使用 _feishu_executor 跑 SDK 调用"
        )


def test_messaging_no_asyncio_to_thread_for_sdk_calls():
    """messaging.py 的 SDK 调用不再用 asyncio.to_thread，改用 loop.run_in_executor。"""
    from illusion.channels.feishu import messaging

    sdk_funcs = [
        "send_text", "edit_message", "send_file", "send_card", "patch_card",
        "create_card_entity", "send_card_by_card_id",
        "set_card_streaming_mode", "update_cardkit_card",
    ]
    for func_name in sdk_funcs:
        func = getattr(messaging, func_name)
        source = inspect.getsource(func)
        assert "asyncio.to_thread(client." not in source, (
            f"{func_name} 不应再用 asyncio.to_thread 包装 SDK 调用"
        )
        assert "_feishu_executor" in source, (
            f"{func_name} 应使用 _feishu_executor 跑 SDK 调用"
        )


# ─── 模式 4：except BaseException 拆分 ──────────────────────────────


def test_except_base_exception_split_in_ws_client_cleanup():
    """ws_client._cleanup_loop 已拆分 BaseException 为 CancelledError + Exception。

    拆分动机：BaseException 会吞掉 CancelledError，导致取消信号无法传播。
    """
    from illusion.channels.feishu.ws_client import FeishuWSClient

    source = inspect.getsource(FeishuWSClient._cleanup_loop)
    assert "except BaseException" not in source, (
        "_cleanup_loop 不应再用 except BaseException"
    )
    assert "except asyncio.CancelledError" in source
    assert "raise" in source


def test_except_base_exception_split_in_serve_shutdown():
    """serve.py 的渠道关闭循环已拆分 BaseException。"""
    from illusion.channels import serve

    # 源码中应不再有 except BaseException
    source = inspect.getsource(serve)
    # channels/__init__.py 不应有 except BaseException
    assert "except BaseException" not in source


def test_except_base_exception_split_in_feishu_adapter_cleanup():
    """feishu/adapter.py 的 _cleanup_resources 已拆分 BaseException。"""
    from illusion.channels.feishu.adapter import FeishuChannel

    source = inspect.getsource(FeishuChannel._cleanup_resources)
    assert "except BaseException" not in source, (
        "_cleanup_resources 不应再用 except BaseException"
    )
    assert "except asyncio.CancelledError" in source


def test_cancelled_error_propagates_through_split_except():
    """拆分后的 except 块正确上抛 CancelledError。

    模拟 ws_client._cleanup_loop 的拆分模式：
        try: ... raise asyncio.CancelledError()
        except asyncio.CancelledError: raise
        except Exception: pass

    验证 CancelledError 不被 Exception 分支吞掉。
    """

    async def _simulate_cleanup():
        """模拟拆分后的 except 块行为"""
        try:
            # 模拟清理过程中触发 CancelledError
            raise asyncio.CancelledError()
        except asyncio.CancelledError:
            raise  # 必须上抛
        except Exception:  # noqa: BLE001
            pass  # 其他异常静默

    with pytest.raises(asyncio.CancelledError):
        asyncio.run(_simulate_cleanup())


def test_regular_exception_swallowed_in_split_except():
    """拆分后的 except 块正确吞掉普通 Exception（不影响取消信号传播）。"""

    async def _simulate_cleanup():
        try:
            raise RuntimeError("cleanup failed")
        except asyncio.CancelledError:
            raise
        except Exception:  # noqa: BLE001
            pass  # 普通异常静默

    # 不应抛异常
    asyncio.run(_simulate_cleanup())


def test_no_except_base_exception_in_channels_init():
    """channels/__init__.py 不应有 except BaseException（Task 15 已修复，本任务保持）。"""
    import illusion.channels as channels_init

    source = inspect.getsource(channels_init)
    assert "except BaseException" not in source


# ─── 模式 3：大文件 I/O 异步化 ──────────────────────────────────────


def test_large_file_write_uses_to_thread_in_qq_adapter(tmp_path: Path):
    """qq/adapter.download_attachment 用 asyncio.to_thread 包装 write_bytes。

    通过 mock 验证：写盘调用走 asyncio.to_thread，不直接同步执行。
    """
    from illusion.channels.qq.adapter import QQChannel

    source = inspect.getsource(QQChannel.download_attachment)
    assert "asyncio.to_thread(save_path_obj.write_bytes" in source, (
        "QQ download_attachment 应用 asyncio.to_thread 包装 write_bytes"
    )


def test_large_file_read_uses_to_thread_in_qq_api(tmp_path: Path):
    """qq/api.py 的 upload_file 用 asyncio.to_thread 包装哈希计算和分片读取。"""
    from illusion.channels.qq import api as qq_api

    upload_source = inspect.getsource(qq_api.upload_file)
    assert "asyncio.to_thread(_compute_file_hashes" in upload_source, (
        "upload_file 应用 asyncio.to_thread 包装 _compute_file_hashes"
    )
    assert "asyncio.to_thread(_read_part" in upload_source, (
        "upload_file 应用 asyncio.to_thread 包装分片读取"
    )


def test_large_file_io_uses_to_thread_in_weixin_adapter():
    """weixin/adapter.py 的 _send_file 和 download_attachment 用 asyncio.to_thread。"""
    from illusion.channels.weixin.adapter import WeixinChannel

    send_file_source = inspect.getsource(WeixinChannel._send_file)
    assert "asyncio.to_thread(Path(path).read_bytes" in send_file_source

    download_source = inspect.getsource(WeixinChannel.download_attachment)
    assert "asyncio.to_thread(out_path.write_bytes" in download_source


def test_large_file_io_uses_to_thread_in_feishu_drive():
    """feishu_drive.py 的上传和下载用 asyncio.to_thread 包装文件 I/O。"""
    from illusion.channels.tools.feishu_drive import (
        FeishuDriveDownloadTool,
        FeishuDriveUploadTool,
    )

    upload_all_source = inspect.getsource(FeishuDriveUploadTool._upload_all)
    assert "asyncio.to_thread(path.read_bytes" in upload_all_source

    chunked_source = inspect.getsource(FeishuDriveUploadTool._upload_chunked)
    assert "asyncio.to_thread(_read_chunk" in chunked_source

    download_source = inspect.getsource(FeishuDriveDownloadTool.execute)
    assert "asyncio.to_thread(save_path.write_bytes" in download_source


def test_file_io_does_not_block_event_loop(tmp_path: Path):
    """大文件写盘通过 to_thread 执行，不阻塞事件循环。

    通过监控事件循环 tick 频率验证：写盘期间事件循环仍在调度其他 task。
    """
    large_data = b"x" * (2 * 1024 * 1024)  # 2MB
    target = tmp_path / "large.bin"
    tick_count = 0

    async def _ticker():
        """高频 tick 协程，每 5ms 一次"""
        nonlocal tick_count
        for _ in range(20):
            await asyncio.sleep(0.005)
            tick_count += 1

    async def _writer():
        # 模拟 to_thread 写盘
        await asyncio.to_thread(target.write_bytes, large_data)

    async def _run():
        # 并发跑 ticker 和 writer
        await asyncio.gather(_ticker(), _writer())

    asyncio.run(_run())

    # ticker 应能跑完所有 tick（事件循环未被阻塞）
    # 容忍一点抖动，至少应能跑一半以上
    assert tick_count >= 10, (
        f"事件循环被阻塞：tick_count={tick_count}/20，"
        "to_thread 应让写盘在后台线程执行"
    )
    # 文件确实写入了
    assert target.read_bytes() == large_data


def test_commands_context_uses_to_thread_for_io():
    """commands/context.py 的 read_text/write_text 用 asyncio.to_thread 包装。"""
    from illusion.commands import context

    issue_source = inspect.getsource(context.issue_handler)
    assert "asyncio.to_thread(path.read_text" in issue_source
    assert "asyncio.to_thread(path.write_text" in issue_source

    pr_source = inspect.getsource(context.pr_comments_handler)
    assert "asyncio.to_thread(path.read_text" in pr_source
    assert "asyncio.to_thread(path.write_text" in pr_source


# ─── 集成：executor 行为验证 ────────────────────────────────────────


def test_feishu_executor_runs_callable_in_thread():
    """_feishu_executor 能在后台线程执行可调用对象，返回结果。"""
    import threading

    from illusion.channels.feishu.adapter import _feishu_executor

    loop = asyncio.new_event_loop()
    try:

        async def _run():
            main_thread = threading.get_ident()

            def _in_thread() -> int:
                return threading.get_ident()

            # 通过 loop.run_in_executor 在 _feishu_executor 上跑
            other_thread = await loop.run_in_executor(_feishu_executor, _in_thread)
            return main_thread, other_thread

        main_thread, other_thread = loop.run_until_complete(_run())
        # 必须在不同线程执行
        assert main_thread != other_thread, "_feishu_executor 应在后台线程执行"
    finally:
        loop.close()


def test_ws_executor_max_workers_one():
    """_ws_executor 只有一个线程，串行执行（WS start 独占）。"""
    import threading

    from illusion.channels.feishu.adapter import _ws_executor

    loop = asyncio.new_event_loop()
    try:

        async def _run():
            threads: list[int] = []

            def _record_thread() -> int:
                threads.append(threading.get_ident())
                return threading.get_ident()

            # 并发提交 3 个任务
            await asyncio.gather(
                loop.run_in_executor(_ws_executor, _record_thread),
                loop.run_in_executor(_ws_executor, _record_thread),
                loop.run_in_executor(_ws_executor, _record_thread),
            )
            return threads

        threads = loop.run_until_complete(_run())
        # 所有任务在同一个线程上执行（max_workers=1 串行化）
        assert len(set(threads)) == 1, (
            f"_ws_executor 应只有 1 个线程，实际 {len(set(threads))}"
        )
    finally:
        loop.close()
