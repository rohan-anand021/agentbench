import json
import httpx
from agentbench.llm.client import LLMClient
from agentbench.llm.config import LLMConfig
from agentbench.llm.messages import (
    InputItem,
    ToolDefinition,
    LLMResponse,
)
from agentbench.llm.errors import AuthenticationError, LLMError, LLMErrorType, TimeoutError
from agentbench.util.events import EventLogger, NullEventLogger, NULL_EVENT_LOGGER

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

    async def _get_client(self) -> httpx.AsyncClient:
        # Create a fresh client each time to avoid "Event loop is closed" errors
        # when asyncio.run() is called multiple times (each call creates/closes a new loop)
        return httpx.AsyncClient(
            timeout=self.config.provider_config.timeout_sec,
            headers=self._get_headers(),
        )

    async def close(self):
        if self._client:
            await self._client.aclose()
            self._client = None

    def _build_request_body(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None = None
    ) -> dict:
        body = {
            "model": self.model_name,
            "input": [json.loads(item.model_dump_json()) for item in input_items],
            "max_output_tokens": self.config.sampling.max_tokens,
            "temperature": self.config.sampling.temperature,
            "top_p": self.config.sampling.top_p,
        }

        if tools:
            body["tools"] = [json.loads(tool.model_dump_json()) for tool in tools]
            body["tool_choice"] = "auto"
        
        return body
    
    def _classify_error(
        self,
        status_code: int,
        response_body: dict | None
    ) -> LLMError:
        error_map = {
            401: (LLMErrorType.AUTH_FAILED, False),
            402: (LLMErrorType.AUTH_FAILED, False),
            403: (LLMErrorType.AUTH_FAILED, False),
            429: (LLMErrorType.RATE_LIMITED, True),
            500: (LLMErrorType.PROVIDER_ERROR, True),
            502: (LLMErrorType.PROVIDER_ERROR, True),
            503: (LLMErrorType.PROVIDER_ERROR, True),
        }

        error_type, retryable = error_map.get(status_code, (LLMErrorType.PROVIDER_ERROR, True))

        message = response_body.get("error", {}).get("message", f"HTTP {status_code}") if response_body else f"HTTP {status_code}"

        return LLMError(error_type, message, retryable=retryable)

    async def complete(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None = None,
        event_logger: EventLogger | NullEventLogger | None = None
    ) -> LLMResponse:
        logger = event_logger or NULL_EVENT_LOGGER
        client = await self._get_client()

        logger.log_llm_request_started(
            model=self.model_name,
            message_count=len(input_items),
            has_tools=tools is not None
        )

        try:
            response = await client.post(
                OPENROUTER_API_URL,
                json=self._build_request_body(input_items, tools)
            )
            
            if response.status_code != 200:
                raise self._classify_error(response.status_code, response.json())

            result = LLMResponse.model_validate(response.json())

            logger.log_llm_request_finished(
                request_id=result.id or "",
                status=result.status or "",
                latency_ms=result.latency_ms or 0,
                tokens_used=result.usage.total_tokens if result.usage else 0,
                has_tool_calls=result.has_tool_calls
            )

            return result
        
        except httpx.TimeoutException as e:
            logger.log_llm_request_failed(
                error_type=LLMErrorType.TIMEOUT.value,
                message=str(e),
                retryable=True
            )
            raise TimeoutError(f"Request timed out after {self.config.provider_config.timeout_sec} seconds") from e
        except httpx.HTTPStatusError as e:
            error = self._classify_error(e.response.status_code, e.response.json())
            logger.log_llm_request_failed(
                error_type=error.error_type.value,
                message=str(error),
                retryable=error.retryable
            )
            raise error from e
        except httpx.RequestError as e:
            logger.log_llm_request_failed(
                error_type=LLMErrorType.NETWORK_ERROR.value,
                message=str(e),
                retryable=True
            )
            raise LLMError(LLMErrorType.NETWORK_ERROR, str(e), retryable=True) from e
        except Exception as e:
            logger.log_llm_request_failed(
                error_type=LLMErrorType.PROVIDER_ERROR.value,
                message=str(e),
                retryable=False
            )
            raise LLMError(LLMErrorType.PROVIDER_ERROR, str(e)) from e
        finally:
            await client.aclose()

    def count_tokens(self, input_items: list[InputItem]) -> int:
        total_chars = sum(len(str(item.model_dump())) for item in input_items)
        return total_chars // 4
