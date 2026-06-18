"""消息渠道模块
================

提供 IllusionCode 的消息渠道能力（飞书等）。

主要功能：
    - 渠道配置管理（channels.json）
    - 渠道守护进程自动激活
    - 渠道消息接入 illusion 引擎

本模块仅做延迟导入，不顶层依赖任何渠道 SDK。
"""
from __future__ import annotations

# 占位：后续 Task 在此填充 maybe_spawn_channel_daemon / ChannelRunner 等
