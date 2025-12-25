import httpx
from datetime import datetime, timezone
from agentbench.llm.client import LLMClient
from agentbench.llm.config import LLMConfig
from agentbench.llm.messages import (
    InputItem,
    MessageRole,
    ToolDefinition,
    LLMResponse
)
from agentbench.llm.errors import AuthenticationError

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/responses"

class OpenRouterClient(LLMClient):

    def __init__(self, config: LLMConfig):
        super().__init__(config)
        self._client: httpx.AsyncClient | None = None

    def _get_headers(self) -> dict[str, str]:
        api_key = self.config.provider_config.api_key

        if not api_key:
            raise AuthenticationError("API key is required")

        return {
            "Authorization": f"Bearer {api_key.get_secret_value()}",
            "Content-Type": "application/json",
            "HTTP-Referer": "https://github.com/agentbench",
            "X-Title": "AgentBench"
        }

    def _build_request_body(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None = None
    ) -> dict:
        body = {
            "model": self.model_name,
            "input": [item.model_dump(
                mode = "json") for item in input_items],
            "max_output_tokens": self.config.sampling.max_tokens,
            "temperature": self.config.sampling.temperature,
            "top_p": self.config.sampling.top_p,
        }

        if tools:
            body["tools"] = [tool.model_dump(mode="json") for tool in tools]
            body["tool_choice"] = "auto"
        
        return body
    
    def _parse_response(
        self,
        response_data: dict,
        latency_ms: int
    ) -> LLMResponse:
        pass

        
    