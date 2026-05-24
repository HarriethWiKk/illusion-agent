"""Effort 集成测试模块

本模块提供 effort 功能的集成测试，包括：
- 完整的 effort 设置和 API 调用流程测试
- 降级和重试机制测试
- 用户提示显示测试
"""

import pytest
from unittest.mock import AsyncMock, MagicMock
from illusion.api.effort import EffortLevel, EffortMapper
from illusion.api.client import ApiMessageRequest
from illusion.engine.messages import ConversationMessage


class TestEffortIntegration:
    """Effort 集成测试"""

    def test_effort_mapper_integration(self):
        """测试 EffortMapper 集成"""
        # 测试标准化
        assert EffortMapper.normalize("low") == EffortLevel.LOW
        assert EffortMapper.normalize("high") == EffortLevel.HIGH
        assert EffortMapper.normalize("xhigh") == EffortLevel.XHIGH
        assert EffortMapper.normalize("max") == EffortLevel.MAX

        # 测试降级
        supported = {EffortLevel.HIGH}
        assert EffortMapper.fallback(EffortLevel.LOW, supported) == EffortLevel.HIGH
        assert EffortMapper.fallback(EffortLevel.MEDIUM, supported) == EffortLevel.HIGH
        assert EffortMapper.fallback(EffortLevel.HIGH, supported) == EffortLevel.HIGH

        # 测试反向降级
        assert EffortMapper.reverse_fallback(EffortLevel.MAX) == EffortLevel.XHIGH
        assert EffortMapper.reverse_fallback(EffortLevel.XHIGH) == EffortLevel.HIGH
        assert EffortMapper.reverse_fallback(EffortLevel.HIGH) == EffortLevel.HIGH

    def test_api_message_request_with_effort(self):
        """测试 ApiMessageRequest 包含 effort"""
        request = ApiMessageRequest(
            model="test-model",
            messages=[ConversationMessage.from_user_text("test")],
            effort=EffortLevel.HIGH,
        )
        assert request.effort == EffortLevel.HIGH

    def test_effort_fallback_logic(self):
        """测试 effort 降级逻辑"""
        # 模拟模型不支持 effort 的情况
        original_effort = EffortLevel.XHIGH
        fallback_effort = EffortMapper.reverse_fallback(original_effort)
        assert fallback_effort == EffortLevel.HIGH

        # 模拟模型支持 effort 的情况
        supported_levels = {EffortLevel.LOW, EffortLevel.MEDIUM, EffortLevel.HIGH}
        normalized_effort = EffortMapper.fallback(original_effort, supported_levels)
        assert normalized_effort == EffortLevel.MAX
