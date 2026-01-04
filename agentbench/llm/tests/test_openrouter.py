import asyncio
import httpx
import pytest
from pydantic import SecretStr
from agentbench.llm import openrouter as openrouter_module
from agentbench.llm.openrouter import OpenRouterClient, OPENROUTER_API_URL
from agentbench.llm.config import LLMConfig, ProviderConfig, LLMProvider, SamplingParams
from agentbench.llm.messages import (
    InputMessage,
    MessageRole,
    ToolDefinition,
)
from agentbench.llm.errors import LLMError, LLMErrorType


def make_config(api_key: str = "test-key") -> LLMConfig:
    return LLMConfig(
        provider_config=ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="anthropic/claude-3.5-sonnet",
            api_key=SecretStr(api_key),
        ),
        sampling=SamplingParams(
            temperature=0.5,
            top_p=0.9,
            max_tokens=1000,
        ),
    )


class TestBuildRequestBody:
    def test_build_request_body_messages(self):
        client = OpenRouterClient(make_config())
        input_items = [
            InputMessage(role=MessageRole.USER, content="Hello"),
            InputMessage(role=MessageRole.SYSTEM, content="You are helpful"),
        ]
        
        body = client._build_request_body(input_items)
        
        assert body["model"] == "anthropic/claude-3.5-sonnet"
        assert body["temperature"] == 0.5
        assert body["top_p"] == 0.9
        assert body["max_output_tokens"] == 1000
        assert len(body["input"]) == 2
        assert body["input"][0]["role"] == "user"
        assert body["input"][0]["content"] == "Hello"
        assert "tools" not in body
        assert "tool_choice" not in body

    def test_build_request_body_with_tools(self):
        client = OpenRouterClient(make_config())
        input_items = [InputMessage(role=MessageRole.USER, content="List files")]
        tools = [
            ToolDefinition(
                name="list_files",
                description="List files in a directory",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"}
                    },
                    "required": ["path"]
                },
            )
        ]
        
        body = client._build_request_body(input_items, tools)
        
        assert "tools" in body
        assert len(body["tools"]) == 1
        assert body["tools"][0]["name"] == "list_files"
        assert body["tools"][0]["type"] == "function"
        assert body["tool_choice"] == "auto"


class TestCountTokens:
    def test_count_tokens_uses_chars_heuristic(self):
        client = OpenRouterClient(make_config())
        items = [
            InputMessage(role=MessageRole.USER, content="hello"),
            InputMessage(role=MessageRole.USER, content="world"),
        ]
        count = client.count_tokens(items)
        assert isinstance(count, int)
        assert count >= 0


class TestClassifyError:
    def test_error_401_auth_failed(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(401, {"error": {"message": "Invalid API key"}})
        
        assert error.error_type == LLMErrorType.AUTH_FAILED
        assert error.retryable is False
        assert "Invalid API key" in str(error)

    def test_error_402_payment_required(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(402, {"error": {"message": "Insufficient credits"}})
        
        assert error.error_type == LLMErrorType.AUTH_FAILED
        assert error.retryable is False

    def test_error_429_rate_limited(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(429, {"error": {"message": "Rate limit exceeded"}})
        
        assert error.error_type == LLMErrorType.RATE_LIMITED
        assert error.retryable is True

    def test_error_500_server_error(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(500, {"error": {"message": "Internal server error"}})
        
        assert error.error_type == LLMErrorType.PROVIDER_ERROR
        assert error.retryable is True

    def test_error_502_bad_gateway(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(502, None)
        
        assert error.error_type == LLMErrorType.PROVIDER_ERROR
        assert error.retryable is True
        assert "HTTP 502" in str(error)

    def test_error_unknown_status_defaults_to_provider_error(self):
        client = OpenRouterClient(make_config())
        error = client._classify_error(418, {"error": {"message": "I'm a teapot"}})
        
        assert error.error_type == LLMErrorType.PROVIDER_ERROR
        assert error.retryable is True


class TestGetHeaders:
    def test_get_headers_includes_auth(self):
        client = OpenRouterClient(make_config("my-secret-key"))
        headers = client._get_headers()
        
        assert headers["Authorization"] == "Bearer my-secret-key"
        assert headers["Content-Type"] == "application/json"
        assert "HTTP-Referer" in headers
        assert "X-Title" in headers

    def test_get_headers_raises_without_api_key(self):
        config = LLMConfig(
            provider_config=ProviderConfig(
                provider=LLMProvider.OPENROUTER,
                model_name="test-model",
                api_key=None,
            )
        )
        client = OpenRouterClient(config)
        
        from agentbench.llm.errors import AuthenticationError
        with pytest.raises(AuthenticationError):
            client._get_headers()


class TestClientProperties:
    def test_model_name_property(self):
        client = OpenRouterClient(make_config())
        assert client.model_name == "anthropic/claude-3.5-sonnet"

    def test_provider_property(self):
        client = OpenRouterClient(make_config())
        assert client.provider == "openrouter"

    def test_api_url_constant(self):
        assert OPENROUTER_API_URL == "https://openrouter.ai/api/v1/responses"


class FakeResponse:
    def __init__(self, status_code: int, body: dict):
        self.status_code = status_code
        self._body = body

    def json(self):
        return self._body


class FakeClient:
    def __init__(self, responses: list[object], state: dict[str, int]):
        self._responses = responses
        self._state = state

    async def post(self, _url: str, json: dict):
        index = self._state["index"]
        self._state["index"] += 1
        response = self._responses[index]
        if isinstance(response, Exception):
            raise response
        return response

    async def aclose(self):
        return None


def test_complete_retries_on_network_error(monkeypatch: pytest.MonkeyPatch):
    config = make_config()
    config.retry_policy.max_retries = 1
    config.retry_policy.initial_delay_sec = 1.0
    config.retry_policy.max_delay_sec = 1.0
    config.retry_policy.exponential_base = 1.0
    client = OpenRouterClient(config)

    state = {"index": 0}
    response_body = {
        "id": "resp_123",
        "model": "test-model",
        "status": "completed",
        "output": [
            {
                "type": "message",
                "role": "assistant",
                "content": [{"type": "output_text", "text": "ok"}],
            }
        ],
        "usage": {"input_tokens": 1, "output_tokens": 1, "total_tokens": 2},
    }
    responses: list[object] = [
        httpx.RequestError("boom", request=httpx.Request("POST", OPENROUTER_API_URL)),
        FakeResponse(200, response_body),
    ]

    async def fake_get_client(self):
        return FakeClient(responses, state)

    async def fake_sleep(_delay: float):
        return None

    monkeypatch.setattr(OpenRouterClient, "_get_client", fake_get_client)
    monkeypatch.setattr(openrouter_module.asyncio, "sleep", fake_sleep)

    result = asyncio.run(
        client.complete(
            [InputMessage(role=MessageRole.USER, content="hello")],
            tools=None,
        )
    )

    assert result.status == "completed"
    assert state["index"] == 2
