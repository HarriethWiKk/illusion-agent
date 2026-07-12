"""Tests for the OpenAI-compatible API client."""

from __future__ import annotations

import json

from illusion.api.openai_client import (
    _convert_messages_to_openai,
    _convert_tools_to_openai,
    _extract_extra_content,
    _model_consumes_thought_signature,
)
from illusion.engine.messages import (
    ConversationMessage,
    ThinkingBlock,
    TextBlock,
    ToolResultBlock,
    ToolUseBlock,
)


class TestConvertToolsToOpenai:
    """Test Anthropic → OpenAI tool schema conversion."""

    def test_basic_tool(self):
        anthropic_tools = [
            {
                "name": "read_file",
                "description": "Read a file",
                "input_schema": {
                    "type": "object",
                    "properties": {
                        "path": {"type": "string", "description": "File path"},
                    },
                    "required": ["path"],
                },
            }
        ]
        result = _convert_tools_to_openai(anthropic_tools)
        assert len(result) == 1
        assert result[0]["type"] == "function"
        assert result[0]["function"]["name"] == "read_file"
        assert result[0]["function"]["description"] == "Read a file"
        assert result[0]["function"]["parameters"]["properties"]["path"]["type"] == "string"

    def test_empty_tools(self):
        assert _convert_tools_to_openai([]) == []

    def test_multiple_tools(self):
        tools = [
            {"name": "tool_a", "description": "A", "input_schema": {}},
            {"name": "tool_b", "description": "B", "input_schema": {}},
        ]
        result = _convert_tools_to_openai(tools)
        assert len(result) == 2
        assert result[0]["function"]["name"] == "tool_a"
        assert result[1]["function"]["name"] == "tool_b"


class TestConvertMessagesToOpenai:
    """Test Anthropic → OpenAI message format conversion."""

    def test_system_prompt(self):
        messages: list[ConversationMessage] = []
        result = _convert_messages_to_openai(messages, "You are helpful.")
        assert len(result) == 1
        assert result[0]["role"] == "system"
        assert result[0]["content"] == "You are helpful."

    def test_no_system_prompt(self):
        messages = [ConversationMessage.from_user_text("hi")]
        result = _convert_messages_to_openai(messages, None)
        assert result[0]["role"] == "user"
        assert result[0]["content"] == "hi"

    def test_user_text_message(self):
        messages = [ConversationMessage.from_user_text("hello")]
        result = _convert_messages_to_openai(messages, None)
        assert len(result) == 1
        assert result[0] == {"role": "user", "content": "hello"}

    def test_assistant_text_message(self):
        msg = ConversationMessage(
            role="assistant", content=[TextBlock(text="I'll help you.")]
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "I'll help you."
        assert "tool_calls" not in result[0]

    def test_assistant_with_tool_calls(self):
        msg = ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="Let me read that file."),
                ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"}),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["content"] == "Let me read that file."
        assert len(result[0]["tool_calls"]) == 1
        tc = result[0]["tool_calls"][0]
        assert tc["id"] == "call_1"
        assert tc["type"] == "function"
        assert tc["function"]["name"] == "read_file"
        assert json.loads(tc["function"]["arguments"]) == {"path": "/tmp/x"}
        assert result[0]["reasoning_content"] == ""

    def test_assistant_with_thinking_and_tool_calls(self):
        msg = ConversationMessage(
            role="assistant",
            content=[
                ThinkingBlock(thinking="先确认路径"),
                TextBlock(text="Let me read that file."),
                ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"}),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["role"] == "assistant"
        assert result[0]["reasoning_content"] == "先确认路径"
        assert len(result[0]["tool_calls"]) == 1

    def test_assistant_with_inline_think_tags(self):
        msg = ConversationMessage(
            role="assistant",
            content=[
                TextBlock(text="<think>先确认路径</think>Answer"),
                ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"}),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert result[0]["content"] == "Answer"
        assert result[0]["reasoning_content"] == "先确认路径"

    def test_tool_result_messages(self):
        # User message containing tool results
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(
                    tool_use_id="call_1", content="file contents here", is_error=False
                ),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 1
        assert result[0]["role"] == "tool"
        assert result[0]["tool_call_id"] == "call_1"
        assert result[0]["content"] == "file contents here"

    def test_full_conversation_round_trip(self):
        """Test a complete user → assistant(tool_call) → user(tool_result) → assistant flow."""
        messages = [
            ConversationMessage.from_user_text("Read /tmp/test.txt"),
            ConversationMessage(
                role="assistant",
                content=[
                    TextBlock(text="I'll read that."),
                    ToolUseBlock(
                        id="call_abc", name="read_file", input={"path": "/tmp/test.txt"}
                    ),
                ],
            ),
            ConversationMessage(
                role="user",
                content=[
                    ToolResultBlock(
                        tool_use_id="call_abc", content="hello world", is_error=False
                    )
                ],
            ),
            ConversationMessage(
                role="assistant",
                content=[TextBlock(text="The file contains: hello world")],
            ),
        ]
        result = _convert_messages_to_openai(messages, "Be helpful")
        assert result[0] == {"role": "system", "content": "Be helpful"}
        assert result[1] == {"role": "user", "content": "Read /tmp/test.txt"}
        assert result[2]["role"] == "assistant"
        assert len(result[2]["tool_calls"]) == 1
        assert result[3]["role"] == "tool"
        assert result[3]["tool_call_id"] == "call_abc"
        assert result[4]["role"] == "assistant"
        assert result[4]["content"] == "The file contains: hello world"

    def test_multiple_tool_results(self):
        msg = ConversationMessage(
            role="user",
            content=[
                ToolResultBlock(tool_use_id="c1", content="result1", is_error=False),
                ToolResultBlock(tool_use_id="c2", content="result2", is_error=True),
            ],
        )
        result = _convert_messages_to_openai([msg], None)
        assert len(result) == 2
        assert result[0]["tool_call_id"] == "c1"
        assert result[1]["tool_call_id"] == "c2"


class TestModelConsumesThoughtSignature:
    """Test the Gemini thought_signature model gating predicate."""

    def test_gemini_models_return_true(self):
        for model in ("gemini-3-pro", "gemini-3.5-flash", "gemini-flash-latest", "google/gemini-3-pro"):
            assert _model_consumes_thought_signature(model), model

    def test_gemma_models_return_true(self):
        # Gemma is served through the same Gemini API and shares the thought_signature contract
        assert _model_consumes_thought_signature("gemma-4-31b-it")

    def test_non_gemini_models_return_false(self):
        for model in ("deepseek-chat", "claude-sonnet-4", "glm-5.2", "qwen-plus", "", "llama-v3"):
            assert not _model_consumes_thought_signature(model), model


class TestExtractExtraContent:
    """Test extraction of extra_content (thought_signature carrier) from SDK objects."""

    def test_attribute_access(self):
        class FakeDelta:
            extra_content = {"google": {"thought_signature": "sig_123"}}

        assert _extract_extra_content(FakeDelta()) == {"google": {"thought_signature": "sig_123"}}

    def test_model_extra_fallback(self):
        class FakeDelta:
            model_extra = {"extra_content": {"google": {"thought_signature": "sig_abc"}}}

        assert _extract_extra_content(FakeDelta()) == {"google": {"thought_signature": "sig_abc"}}

    def test_returns_none_when_absent(self):
        class FakeDelta:
            pass

        assert _extract_extra_content(FakeDelta()) is None

    def test_pydantic_model_dump(self):
        from pydantic import BaseModel

        class ExtraModel(BaseModel):
            thought_signature: str = "sig_xyz"

        class FakeDelta:
            extra_content = ExtraModel()

        result = _extract_extra_content(FakeDelta())
        assert result == {"thought_signature": "sig_xyz"}


class TestThoughtSignatureReplay:
    """Test that Gemini thought_signature (extra_content) round-trips correctly.

    Gemini 3 thinking models attach a thought_signature to every functionCall.
    This signature MUST be replayed on subsequent requests or the API returns
    HTTP 400 "missing thought_signature". Strict providers (Fireworks, Mistral)
    reject the extra_content field, so it must be model-gated.
    """

    def _msg_with_signature(self) -> ConversationMessage:
        return ConversationMessage(
            role="assistant",
            content=[
                ToolUseBlock(
                    id="call_1",
                    name="write_file",
                    input={"file_path": "/tmp/x"},
                    provider_data={
                        "extra_content": {"google": {"thought_signature": "SIG_GEMINI_123"}}
                    },
                ),
            ],
        )

    def test_preserves_extra_content_for_gemini(self):
        """Gemini targets keep extra_content so the signature round-trips."""
        msg = self._msg_with_signature()
        result = _convert_messages_to_openai([msg], None, model="gemini-3.5-flash")
        tc = result[0]["tool_calls"][0]
        assert tc["extra_content"] == {"google": {"thought_signature": "SIG_GEMINI_123"}}

    def test_preserves_extra_content_for_gemma(self):
        msg = self._msg_with_signature()
        result = _convert_messages_to_openai([msg], None, model="gemma-4-31b-it")
        assert result[0]["tool_calls"][0]["extra_content"] == {
            "google": {"thought_signature": "SIG_GEMINI_123"}
        }

    def test_strips_extra_content_for_strict_provider(self):
        """Non-Gemini providers reject extra_content with 400 — must be stripped."""
        msg = self._msg_with_signature()
        result = _convert_messages_to_openai([msg], None, model="deepseek-chat")
        assert "extra_content" not in result[0]["tool_calls"][0]

    def test_strips_extra_content_when_no_model(self):
        """Default (no model) is to strip — safe for strict providers."""
        msg = self._msg_with_signature()
        result = _convert_messages_to_openai([msg], None)
        assert "extra_content" not in result[0]["tool_calls"][0]

    def test_no_extra_content_key_when_provider_data_empty(self):
        """When provider_data has no extra_content, the tool call must not carry the key."""
        msg = ConversationMessage(
            role="assistant",
            content=[ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"})],
        )
        result = _convert_messages_to_openai([msg], None, model="gemini-3-pro")
        assert "extra_content" not in result[0]["tool_calls"][0]

    def test_multiple_tool_calls_each_keep_their_signature(self):
        """Each tool call carries its own thought_signature — must be preserved independently."""
        msg = ConversationMessage(
            role="assistant",
            content=[
                ToolUseBlock(
                    id="call_1", name="read_file", input={"path": "/a"},
                    provider_data={"extra_content": {"google": {"thought_signature": "SIG_A"}}},
                ),
                ToolUseBlock(
                    id="call_2", name="write_file", input={"path": "/b"},
                    provider_data={"extra_content": {"google": {"thought_signature": "SIG_B"}}},
                ),
            ],
        )
        result = _convert_messages_to_openai([msg], None, model="gemini-3-pro")
        tcs = result[0]["tool_calls"]
        assert tcs[0]["extra_content"] == {"google": {"thought_signature": "SIG_A"}}
        assert tcs[1]["extra_content"] == {"google": {"thought_signature": "SIG_B"}}

    def test_backward_compat_tooluseblock_without_provider_data(self):
        """Existing ToolUseBlock construction (no provider_data arg) must still work."""
        tu = ToolUseBlock(id="call_1", name="read_file", input={"path": "/tmp/x"})
        assert tu.provider_data == {}
        msg = ConversationMessage(role="assistant", content=[tu])
        # Gemini target, empty provider_data → no extra_content key
        result = _convert_messages_to_openai([msg], None, model="gemini-3-pro")
        assert "extra_content" not in result[0]["tool_calls"][0]
