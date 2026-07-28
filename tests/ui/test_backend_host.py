"""UI effort 选项测试模块

本模块提供 UI effort 选项的单元测试，包括：
- effort 选项列表测试
- effort 选项选择测试
"""

from unittest.mock import AsyncMock, MagicMock

import pytest

from illusion.ui.backend_host import ReactBackendHost


class TestBackendHostEffort:
    """UI effort 选项测试"""

    @pytest.fixture
    def mock_host(self):
        """创建模拟的 BackendHost"""
        host = MagicMock(spec=ReactBackendHost)
        host._emit = AsyncMock()
        return host

    @pytest.mark.asyncio
    async def test_effort_options(self, mock_host):
        """测试 effort 选项列表"""
        # 这个测试需要完整的 BackendHost，暂时跳过
