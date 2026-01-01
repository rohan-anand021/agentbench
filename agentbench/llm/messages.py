"""Message types for OpenRouter Responses API Beta.
API Reference: https://openrouter.ai/docs/api/reference/responses/basic-usage
"""

from enum import StrEnum
from datetime import datetime
from pydantic import BaseModel, Field
from typing import Any, Literal

class MessageRole(StrEnum):
    USER = "user"
    ASSISTANT = "assistant"
    SYSTEM = "system"
class InputTextContent(BaseModel):
    type: Literal["input_text"] = "input_text"
    text: str
class OutputTextContent(BaseModel):
    type: Literal["output_text"] = "output_text"
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
class OutputMessage(BaseModel):
    type: Literal["message"] = "message"
    id: str
    role: Literal["assistant"] = "assistant"
    status: str  # "completed", "in_progress", etc.
    content: list[OutputTextContent]
class OutputFunctionCall(BaseModel):
    type: Literal["function_call"] = "function_call"
    id: str
    call_id: str
    name: str
    arguments: str

OutputItem = OutputMessage | OutputFunctionCall

class InputTokensDetails(BaseModel):
    cached_tokens: int = 0


class OutputTokensDetails(BaseModel):
    reasoning_tokens: int = 0


class TokenUsage(BaseModel):
    input_tokens: int
    output_tokens: int
    total_tokens: int
    input_tokens_details: InputTokensDetails | None = None
    output_tokens_details: OutputTokensDetails | None = None
class LLMResponse(BaseModel):
    id: str
    object: Literal["response"] = "response"
    created_at: int
    model: str
    status: str = "completed"
    output: list[OutputMessage | OutputFunctionCall]
    usage: TokenUsage | None = None
    error: dict[str, Any] | None = None
    latency_ms: int = 0
    timestamp: datetime = Field(default_factory=datetime.now)

    @property
    def has_tool_calls(self) -> bool:
        """Check if the response contains any function calls."""
        return any(
            isinstance(item, OutputFunctionCall) or
            (isinstance(item, dict) and item.get("type") == "function_call")
            for item in self.output
        )

    @property
    def text_content(self) -> str | None:
        """Extract the text content from the first message output."""
        for item in self.output:
            if isinstance(item, OutputMessage):
                if item.content:
                    return item.content[0].text
            elif isinstance(item, dict) and item.get("type") == "message":
                content = item.get("content", [])
                if content:
                    return content[0].get("text")
        return None

    @property
    def tool_calls(self) -> list[OutputFunctionCall]:
        """Extract all function calls from the output."""
        return [
            item for item in self.output
            if isinstance(item, OutputFunctionCall) or
            (isinstance(item, dict) and item.get("type") == "function_call")
        ]
