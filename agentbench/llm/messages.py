"""Message types for OpenRouter Responses API Beta.
API Reference: https://openrouter.ai/docs/api/reference/responses/basic-usage
"""

from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, Field, model_validator
from typing import Any, Literal

class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
class InputTextContent(BaseModel):
    type: Literal["input_text"] = "input_text"
    text: str
class OutputTextContent(BaseModel):
    type: Literal["output_text", "text"] = "output_text"
    text: str
    annotations: list[Any] = Field(default_factory=list)
class InputMessage(BaseModel):
    type: Literal["message"] = "message"
    role: MessageRole
    content: list[InputTextContent] | str
    id: str | None = None
    status: str | None = None
class FunctionCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str
    call_id: str
    name: str
    arguments: str
class FunctionCallOutput(BaseModel):
    type: Literal["function_call_output"] = "function_call_output"
    id: str
    call_id: str
    output: str

InputItem = InputMessage | FunctionCall | FunctionCallOutput

class ToolDefinition(BaseModel):
    type: Literal["function"] = "function"
    name: str
    description: str
    parameters: dict[str, Any]
    strict: bool | None = None
OutputContent = OutputTextContent | dict[str, Any] | str

class OutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str | None = None
    role: Literal["assistant"] = "assistant"
    status: str | None = None  # "completed", "in_progress", etc.
    content: list[OutputContent] | str | None = None
class OutputFunctionCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str | None = None
    call_id: str | None = None
    name: str | None = None
    arguments: str | dict[str, Any] | None = None
    function: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        updated = dict(data)
        func = updated.get("function")
        if isinstance(func, dict):
            updated.setdefault("name", func.get("name"))
            updated.setdefault("arguments", func.get("arguments"))
        if "tool_name" in updated and "name" not in updated:
            updated["name"] = updated.get("tool_name")
        if "args" in updated and "arguments" not in updated:
            updated["arguments"] = updated.get("args")
        if updated.get("id") and not updated.get("call_id"):
            updated["call_id"] = updated["id"]
        return updated

class OutputToolCall(BaseModel):
    type: Literal["tool_call"] = "tool_call"
    id: str | None = None
    call_id: str | None = None
    name: str | None = None
    arguments: str | dict[str, Any] | None = None
    function: dict[str, Any] | None = None

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data
        updated = dict(data)
        func = updated.get("function")
        if isinstance(func, dict):
            updated.setdefault("name", func.get("name"))
            updated.setdefault("arguments", func.get("arguments"))
        if "tool_name" in updated and "name" not in updated:
            updated["name"] = updated.get("tool_name")
        if "args" in updated and "arguments" not in updated:
            updated["arguments"] = updated.get("args")
        if updated.get("id") and not updated.get("call_id"):
            updated["call_id"] = updated["id"]
        return updated

class OutputReasoning(BaseModel):
    """Reasoning/chain-of-thought output from models like o3, grok, deepseek."""
    type: Literal["reasoning"] = "reasoning"
    id: str | None = None
    content: list[Any] | str | None = None  # Can be text or structured content


OutputItem = OutputMessage | OutputFunctionCall | OutputToolCall | OutputReasoning | dict[str, Any]

class InputTokensDetails(BaseModel):
    cached_tokens: int = 0


class OutputTokensDetails(BaseModel):
    reasoning_tokens: int = 0


class TokenUsage(BaseModel):
    input_tokens: int = 0
    output_tokens: int = 0
    total_tokens: int = 0
    input_tokens_details: InputTokensDetails | None = None
    output_tokens_details: OutputTokensDetails | None = None
class LLMResponse(BaseModel):
    id: str | None = None
    object: str = "response"
    created_at: int = 0
    model: str = ""
    status: str = "completed"
    output: list[OutputItem] = Field(default_factory=list)
    usage: TokenUsage | None = None
    error: dict[str, Any] | str | None = None
    latency_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)

    @model_validator(mode="before")
    @classmethod
    def _normalize_payload(cls, data: Any) -> Any:
        if not isinstance(data, dict):
            return data

        if "created_at" not in data and "created" in data:
            data["created_at"] = data["created"]

        if "output" not in data and "choices" in data:
            data = cls._from_chat_completions(data)

        output = data.get("output")
        if output is None:
            data["output"] = []
        elif isinstance(output, dict):
            data["output"] = [output]
        elif isinstance(output, str):
            data["output"] = [
                {"type": "message", "role": "assistant", "content": output}
            ]

        usage = data.get("usage")
        if isinstance(usage, dict) and "input_tokens" not in usage:
            if "prompt_tokens" in usage or "completion_tokens" in usage:
                data["usage"] = {
                    "input_tokens": usage.get("prompt_tokens", 0) or 0,
                    "output_tokens": usage.get("completion_tokens", 0) or 0,
                    "total_tokens": usage.get("total_tokens", 0) or 0,
                }

        data.setdefault("object", "response")
        data.setdefault("status", "completed")
        return data

    @classmethod
    def _from_chat_completions(cls, data: dict[str, Any]) -> dict[str, Any]:
        choices = data.get("choices") or []
        output: list[dict[str, Any]] = []

        for index, choice in enumerate(choices):
            message = {}
            if isinstance(choice, dict):
                message = choice.get("message") or {}

            content = message.get("content")
            if isinstance(content, list):
                content_value = content
            elif content is not None:
                content_value = [{"type": "output_text", "text": content}]
            else:
                content_value = None

            if content_value is not None:
                output.append(
                    {
                        "type": "message",
                        "id": message.get("id") or f"msg_{index}",
                        "role": "assistant",
                        "status": "completed",
                        "content": content_value,
                    }
                )

            tool_calls = message.get("tool_calls")
            if tool_calls is None and "function_call" in message:
                tool_calls = [message.get("function_call")]
            if isinstance(tool_calls, dict):
                tool_calls = [tool_calls]
            if isinstance(tool_calls, list):
                for call in tool_calls:
                    if not isinstance(call, dict):
                        continue
                    function = call.get("function") or {}
                    name = call.get("name") or function.get("name") or ""
                    arguments = call.get("arguments") or function.get("arguments") or ""
                    call_id = call.get("id") or f"call_{index}"
                    output.append(
                        {
                            "type": "function_call",
                            "id": call_id,
                            "call_id": call_id,
                            "name": name,
                            "arguments": arguments,
                        }
                    )

        if output:
            data["output"] = output
        data.setdefault("object", "response")
        data.setdefault("status", "completed")
        return data

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains any function calls."""
        return any(
            isinstance(item, (OutputFunctionCall, OutputToolCall)) or
            (isinstance(item, dict) and item.get("type") in {"function_call", "tool_call"})
            for item in self.output
        )

    @property
    def text_content(self) -> str | None:
        """Extract the text content from the first message output."""
        for item in self.output:
            if isinstance(item, OutputMessage):
                content = item.content
                if isinstance(content, str):
                    return content
                if isinstance(content, list):
                    for part in content:
                        if isinstance(part, OutputTextContent):
                            return part.text
                        if isinstance(part, str):
                            return part
                        if isinstance(part, dict):
                            text = part.get("text")
                            if text:
                                return text
            elif isinstance(item, dict):
                if item.get("type") == "message":
                    content = item.get("content")
                    if isinstance(content, str):
                        return content
                    if isinstance(content, list):
                        for part in content:
                            if isinstance(part, str):
                                return part
                            if isinstance(part, dict):
                                text = part.get("text")
                                if text:
                                    return text
                if item.get("type") in {"output_text", "text"}:
                    text = item.get("text")
                    if isinstance(text, str):
                        return text
        return None

    @property
    def tool_calls(self) -> list[OutputFunctionCall | OutputToolCall | dict[str, Any]]:
        """Extract all function calls from the output."""
        return [
            item for item in self.output
            if isinstance(item, (OutputFunctionCall, OutputToolCall)) or
            (isinstance(item, dict) and item.get("type") in {"function_call", "tool_call"})
        ]
