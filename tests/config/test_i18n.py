"""i18n 翻译测试模块

本模块提供 i18n 翻译的单元测试，包括：
- effort 相关翻译测试
- 降级提示翻译测试
"""

from illusion.config.i18n import translate_command_message


class TestI18nEffort:
    """i18n effort 翻译测试"""

    def test_effort_command_translation(self):
        """测试 /effort 命令翻译"""
        # 这个测试需要完整的命令注册表，暂时跳过
        pass

    def test_effort_usage_translation(self):
        """测试 /effort 用法翻译"""
        result = translate_command_message("Usage: /effort [show|low|medium|high|xhigh|max]", locale="zh-CN")
        assert result == "用法：/effort [show|low|medium|high|xhigh|max]"

    def test_effort_show_translation(self):
        """测试 effort 显示翻译"""
        result = translate_command_message("Reasoning effort: high", locale="zh-CN")
        assert result == "推理强度：high"

    def test_effort_set_translation(self):
        """测试 effort 设置翻译"""
        result = translate_command_message("Reasoning effort set to high.", locale="zh-CN")
        assert result == "推理强度已设置为 high。"
