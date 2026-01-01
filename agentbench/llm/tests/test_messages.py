"""Unit tests for LLM message types (Responses API format).

Tests cover:
1. Message serialization (InputMessage, OutputMessage)
2. ToolCall/FunctionCall arguments validation
3. LLMResponse.has_tool_calls property
4. LLMResponse round-trip serialization
5. TokenUsage fields
"""

import json
import pytest
from datetime import datetime, timezone

from agentbench.llm.messages import (
    MessageRole,
    InputTextContent,
    OutputTextContent,
    InputMessage,
    OutputMessage,
    FunctionCall,
    FunctionCallOutput,
    OutputFunctionCall,
    ToolDefinition,
    TokenUsage,
    InputTokensDetails,
    OutputTokensDetails,
    LLMResponse,
)


class TestInputMessageSerialization:
    """Tests for InputMessage serialization."""

    def test_input_message_serialization(self) -> None:
        """InputMessage.model_dump(mode='json') works correctly."""
        message = InputMessage(
            role=MessageRole.USER,
            content=[InputTextContent(text="Hello, how are you?")]
        )

        serialized = message.model_dump(mode="json")

        assert serialized["type"] == "message"
        assert serialized["role"] == "user"
        assert serialized["content"][0]["type"] == "input_text"
        assert serialized["content"][0]["text"] == "Hello, how are you?"

    def test_input_message_with_string_content(self) -> None:
        """InputMessage can accept string content."""
        message = InputMessage(
            role=MessageRole.USER,
            content="Simple string content"
        )

        assert message.content == "Simple string content"

    def test_all_message_roles(self) -> None:
        """All MessageRole values can be used."""
        roles = [MessageRole.USER, MessageRole.ASSISTANT, MessageRole.SYSTEM]

        for role in roles:
            message = InputMessage(
                role=role,
                content=[InputTextContent(text="test")]
            )
            assert message.role == role


class TestFunctionCallTypes:
    """Tests for FunctionCall and FunctionCallOutput."""

    def test_function_call_serialization(self) -> None:
        """FunctionCall serializes correctly for conversation history."""
        fc = FunctionCall(
            id="fc_123",
            call_id="call_abc",
            name="get_weather",
            arguments=json.dumps({"location": "San Francisco, CA"})
        )

        serialized = fc.model_dump(mode="json")

        assert serialized["type"] == "function_call"
        assert serialized["id"] == "fc_123"
        assert serialized["call_id"] == "call_abc"
        assert serialized["name"] == "get_weather"
        assert json.loads(serialized["arguments"]) == {"location": "San Francisco, CA"}

    def test_function_call_output_serialization(self) -> None:
        """FunctionCallOutput serializes correctly."""
        fco = FunctionCallOutput(
            id="fco_123",
            call_id="call_abc",
            output=json.dumps({"temperature": "72°F", "condition": "Sunny"})
        )

        serialized = fco.model_dump(mode="json")

        assert serialized["type"] == "function_call_output"
        assert serialized["call_id"] == "call_abc"


class TestOutputTypes:
    """Tests for OutputMessage and OutputFunctionCall."""

    def test_output_message_serialization(self) -> None:
        """OutputMessage serializes correctly."""
        msg = OutputMessage(
            id="msg_123",
            status="completed",
            content=[OutputTextContent(text="Hello! How can I help?")]
        )

        serialized = msg.model_dump(mode="json")

        assert serialized["type"] == "message"
        assert serialized["role"] == "assistant"
        assert serialized["status"] == "completed"
        assert serialized["content"][0]["type"] == "output_text"
        assert serialized["content"][0]["text"] == "Hello! How can I help?"

    def test_output_function_call_serialization(self) -> None:
        """OutputFunctionCall serializes correctly."""
        fc = OutputFunctionCall(
            id="fc_456",
            call_id="call_xyz",
            name="search",
            arguments=json.dumps({"query": "python"})
        )

        serialized = fc.model_dump(mode="json")

        assert serialized["type"] == "function_call"
        assert serialized["call_id"] == "call_xyz"
        assert serialized["name"] == "search"


class TestLLMResponseHasToolCalls:
    """Tests for LLMResponse.has_tool_calls property."""

    def test_llm_response_has_tool_calls_true(self) -> None:
        """has_tool_calls returns True when output contains function_call."""
        response = LLMResponse(
            id="resp_123",
            created_at=1704067200,
            model="openai/gpt-4",
            status="completed",
            output=[
                OutputFunctionCall(
                    id="fc_1",
                    call_id="call_1",
                    name="search",
                    arguments='{"query": "test"}'
                )
            ],
        )

        assert response.has_tool_calls is True

    def test_llm_response_has_tool_calls_false(self) -> None:
        """has_tool_calls returns False when output only has messages."""
        response = LLMResponse(
            id="resp_456",
            created_at=1704067200,
            model="openai/gpt-4",
            status="completed",
            output=[
                OutputMessage(
                    id="msg_1",
                    status="completed",
                    content=[OutputTextContent(text="Hello there!")]
                )
            ],
        )

        assert response.has_tool_calls is False


class TestLLMResponseSerialization:
    """Tests for LLMResponse serialization round-trip."""

    def test_llm_response_serialization(self) -> None:
        """LLMResponse can round-trip through JSON serialization."""
        original = LLMResponse(
            id="resp_roundtrip",
            created_at=1704067200,
            model="anthropic/claude-3.5-sonnet",
            status="completed",
            output=[
                OutputMessage(
                    id="msg_1",
                    status="completed",
                    content=[OutputTextContent(text="Test response")]
                )
            ],
            usage=TokenUsage(
                input_tokens=50,
                output_tokens=25,
                total_tokens=75,
            ),
            latency_ms=200,
        )

        json_dict = original.model_dump(mode="json")
        restored = LLMResponse.model_validate(json_dict)

        assert restored.id == original.id
        assert restored.model == original.model
        assert restored.status == original.status
        assert restored.latency_ms == original.latency_ms

    def test_llm_response_text_content_property(self) -> None:
        """text_content property extracts text from first message."""
        response = LLMResponse(
            id="resp_text",
            created_at=1704067200,
            model="openai/gpt-4",
            status="completed",
            output=[
                OutputMessage(
                    id="msg_1",
                    status="completed",
                    content=[OutputTextContent(text="This is the response text")]
                )
            ],
        )

        assert response.text_content == "This is the response text"


class TestTokenUsage:
    """Tests for TokenUsage with Responses API fields."""

    def test_token_usage_fields(self) -> None:
        """TokenUsage uses Responses API field names."""
        usage = TokenUsage(
            input_tokens=100,
            output_tokens=50,
            total_tokens=150,
        )

        assert usage.input_tokens == 100
        assert usage.output_tokens == 50
        assert usage.total_tokens == 150

    def test_token_usage_with_details(self) -> None:
        """TokenUsage with nested details objects."""
        usage = TokenUsage(
            input_tokens=200,
            output_tokens=100,
            total_tokens=300,
            input_tokens_details=InputTokensDetails(cached_tokens=50),
            output_tokens_details=OutputTokensDetails(reasoning_tokens=20),
        )

        assert usage.input_tokens_details is not None
        assert usage.input_tokens_details.cached_tokens == 50
        assert usage.output_tokens_details is not None
        assert usage.output_tokens_details.reasoning_tokens == 20

    def test_token_usage_details_optional(self) -> None:
        """Token details are optional and default to None."""
        usage = TokenUsage(
            input_tokens=50,
            output_tokens=25,
            total_tokens=75,
        )

        assert usage.input_tokens_details is None
        assert usage.output_tokens_details is None


class TestToolDefinition:
    """Tests for ToolDefinition model."""

    def test_tool_definition_serialization(self) -> None:
        """ToolDefinition serializes correctly for Responses API."""
        tool_def = ToolDefinition(
            name="read_file",
            description="Read the contents of a file",
            parameters={
                "type": "object",
                "properties": {
                    "path": {"type": "string", "description": "File path to read"},
                },
                "required": ["path"],
            },
        )

        serialized = tool_def.model_dump(mode="json")

        assert serialized["type"] == "function"
        assert serialized["name"] == "read_file"
        assert serialized["description"] == "Read the contents of a file"
        assert "properties" in serialized["parameters"]
