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


class TestI18nIndentedUsage:
    """i18n 缩进行用法翻译测试"""

    def test_indented_usage_line_translated(self):
        """测试带 14 个空格缩进的 /effort usage 行被翻译且保留缩进"""
        result = translate_command_message(
            "              Usage: /effort [show|low|medium|high|xhigh|max]",
            locale="zh-CN",
        )
        assert result == "              用法：/effort [show|low|medium|high|xhigh|max]"
        # en locale 原样返回
        en_result = translate_command_message(
            "              Usage: /effort [show|low|medium|high|xhigh|max]",
            locale="en",
        )
        assert en_result == "              Usage: /effort [show|low|medium|high|xhigh|max]"

    def test_indented_usage_context_translated(self):
        """测试带 14 个空格缩进的 /context usage 行被翻译且保留缩进"""
        result = translate_command_message(
            "              Usage: /context [usage|show|window|set N]",
            locale="zh-CN",
        )
        assert result == "              用法：/context [usage|show|window|set N]"
        en_result = translate_command_message(
            "              Usage: /context [usage|show|window|set N]",
            locale="en",
        )
        assert en_result == "              Usage: /context [usage|show|window|set N]"

    def test_non_indented_usage_still_works(self):
        """测试非缩进的 usage 行仍能正确翻译"""
        result = translate_command_message(
            "Usage: /effort [show|low|medium|high|xhigh|max]",
            locale="zh-CN",
        )
        assert result == "用法：/effort [show|low|medium|high|xhigh|max]"
        en_result = translate_command_message(
            "Usage: /effort [show|low|medium|high|xhigh|max]",
            locale="en",
        )
        assert en_result == "Usage: /effort [show|low|medium|high|xhigh|max]"

    def test_indented_non_usage_line_preserved(self):
        """测试无可翻译内容的缩进行原样返回（保留缩进）"""
        result = translate_command_message(
            "              some random text",
            locale="zh-CN",
        )
        assert result == "              some random text"
        en_result = translate_command_message(
            "              some random text",
            locale="en",
        )
        assert en_result == "              some random text"

    def test_tab_indented_line_translated(self):
        """测试 Tab 缩进的 usage 行被翻译且保留 Tab 缩进"""
        result = translate_command_message(
            "\t\tUsage: /effort [show|low|medium|high|xhigh|max]",
            locale="zh-CN",
        )
        assert result == "\t\t用法：/effort [show|low|medium|high|xhigh|max]"
        en_result = translate_command_message(
            "\t\tUsage: /effort [show|low|medium|high|xhigh|max]",
            locale="en",
        )
        assert en_result == "\t\tUsage: /effort [show|low|medium|high|xhigh|max]"
