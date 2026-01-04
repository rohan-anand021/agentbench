from abc import ABC, abstractmethod
from agentbench.llm.config import LLMConfig
from agentbench.llm.messages import (
    InputItem,
    InputMessage,
    ToolDefinition,
    LLMResponse,
)
from agentbench.util.events import EventLogger, NullEventLogger


class LLMClient(ABC):
    """Abstract interface for LLM providers using Responses API."""

    def __init__(self, config: LLMConfig):
        self.config = config

    @abstractmethod
    async def complete(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None = None,
        event_logger: EventLogger | NullEventLogger | None = None,
    ) -> LLMResponse:
        """Send a completion request to the LLM.
        
        Args:
            input_items: List of input items (messages, function calls, etc.)
            tools: Optional tool definitions for function calling
        
        Returns:
            LLMResponse with output items and usage information
        
        Raises:
            LLMError: On any failure (rate limit, timeout, etc.)
        """
        pass

    @abstractmethod
    def count_tokens(self, input_items: list[InputItem]) -> int:
        """Estimate token count for input items."""
        pass

    @property
    def model_name(self) -> str:
        return self.config.provider_config.model_name

    @property
    def provider(self) -> str:
        return self.config.provider_config.provider.value
