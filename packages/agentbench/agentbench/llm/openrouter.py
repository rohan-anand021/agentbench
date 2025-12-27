import httpx
from agentbench.llm.client import LLMClient
from agentbench.llm.config import LLMConfig
from agentbench.llm.messages import (
    InputItem,
    ToolDefinition,
    LLMResponse,
)
from agentbench.llm.errors import AuthenticationError, LLMError, LLMErrorType, TimeoutError

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
        if self._client is None:
            self._client = httpx.AsyncClient(
                timeout=self.config.provider_config.timeout_sec,
                headers=self._get_headers(),
            )
        return self._client

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
            "input": [item.model_dump(
                mode = "json") for item in input_items],
            "max_output_tokens": self.config.sampling.max_tokens,
            "temperature": self.config.sampling.temperature,
            "top_p": self.config.sampling.top_p,
        }

        if tools:
            body["tools"] = [tool.model_dump(
                mode = "json") for tool in tools]
            body["tool_choice"] = "auto"
        
        return body
    
    def _parse_response(
        self,
        response_data: dict
    ) -> LLMResponse:
        """
        {
            "id": "gen-1766734030-5BA0srfclPVIFEk1Zb7P",
            "object": "response",
            "created_at": 1766734030,
            "model": "mistralai/devstral-2512:free",
            "status": "completed",
            "output": [
                {
                "type": "message",
                "id": "msg_tmp_6vcv7htmlkp",
                "role": "assistant",
                "status": "completed",
                "content": [
                    {
                    "type": "output_text",
                    "text": "Hello!",
                    "annotations": []
                    }
                ]
                }
            ],
            "usage": {
                "input_tokens": 4,
                "output_tokens": 72,
                "total_tokens": 76,
                "input_tokens_details": {
                "cached_tokens": 0
                },
                "output_tokens_details": {
                "reasoning_tokens": 0
                }
            },
            "error": null,
            "latency_ms": 42056,
            "timestamp": "2025-12-26T02:27:52.372581"
        }
        """

        return LLMResponse(
            id = response_data.get("id"),
            object = response_data.get("object"),
            created_at = response_data.get("created_at"),
            model = response_data.get("model"),
            status = response_data.get("status"),
            output = response_data.get("output"),
            usage = response_data.get("usage"),
            error = response_data.get("error"),
            latency_ms = response_data.get("latency_ms"),
            timestamp = response_data.get("timestamp")
        )

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

        return LLMError(error_type, message, retryable = retryable)

    async def complete(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None = None
    ) -> LLMResponse:
        client = await self._get_client()
        try:
            response = await client.post(
                OPENROUTER_API_URL,
                json=self._build_request_body(input_items, tools)
            )
            
            if response.status_code != 200:
                raise self._classify_error(response.status_code, response.json())

            return LLMResponse.model_validate(response.json())
        
        except httpx.TimeoutException as e:
            raise TimeoutError(f"Request timed out after {self.config.provider_config.timeout_sec} seconds") from e
        except httpx.HTTPStatusError as e:
            raise self._classify_error(e.response.status_code, e.response.json()) from e
        except httpx.RequestError as e:
            raise LLMError(LLMErrorType.NETWORK_ERROR, str(e), retryable=True) from e
        except Exception as e:
            raise LLMError(LLMErrorType.PROVIDER_ERROR, str(e)) from e