"""Unit tests for LLM error types.

Tests cover:
1. LLMError base class behavior
2. RateLimitedError is retryable
3. AuthenticationError is not retryable
4. Error to FailureReason mapping
5. Error details capture
6. New error types: InvalidRequestError, ProviderError, ContentFilterError
"""

import pytest

from agentbench.llm.errors import (
    LLMError,
    LLMErrorType,
    RateLimitedError,
    AuthenticationError,
    TimeoutError,
    ContextLengthError,
    InvalidRequestError,
    ProviderError,
    ContentFilterError,
)
from agentbench.scoring.taxonomy import FailureReason


class TestLLMErrorBase:
    """Tests for LLMError base class."""

    def test_llm_error_base(self) -> None:
        """Error captures type and message correctly."""
        error = LLMError(
            error_type=LLMErrorType.NETWORK_ERROR,
            message="Connection refused",
        )

        assert error.error_type == LLMErrorType.NETWORK_ERROR
        assert str(error) == "Connection refused"
        assert error.provider_code is None
        assert error.retryable is False
        assert error.details == {}

    def test_llm_error_with_all_fields(self) -> None:
        """LLMError captures all provided fields."""
        error = LLMError(
            error_type=LLMErrorType.PROVIDER_ERROR,
            message="Internal server error",
            provider_code="500",
            retryable=True,
            details={"response_body": "Server overloaded"},
        )

        assert error.error_type == LLMErrorType.PROVIDER_ERROR
        assert error.provider_code == "500"
        assert error.retryable is True
        assert error.details["response_body"] == "Server overloaded"


class TestRateLimitIsRetryable:
    """Tests for RateLimitedError retryable behavior."""

    def test_rate_limit_is_retryable(self) -> None:
        """RateLimitedError.retryable is True."""
        error = RateLimitedError(
            message="Rate limit exceeded",
            retry_after_sec=30,
        )

        assert error.retryable is True
        assert error.error_type == LLMErrorType.RATE_LIMITED

    def test_rate_limit_captures_retry_after(self) -> None:
        """RateLimitedError captures retry_after_sec in details."""
        error = RateLimitedError(
            message="Too many requests",
            retry_after_sec=60,
        )

        assert error.details["retry_after_sec"] == 60


class TestAuthErrorNotRetryable:
    """Tests for AuthenticationError non-retryable behavior."""

    def test_auth_error_not_retryable(self) -> None:
        """AuthenticationError.retryable is False."""
        error = AuthenticationError(
            message="Invalid API key",
        )

        assert error.retryable is False
        assert error.error_type == LLMErrorType.AUTH_FAILED

    def test_auth_error_message(self) -> None:
        """AuthenticationError captures message correctly."""
        error = AuthenticationError(
            message="API key expired",
        )

        assert str(error) == "API key expired"


class TestErrorToFailureReason:
    """Tests for error to FailureReason mapping."""

    def test_error_to_failure_reason(self) -> None:
        """All LLM errors map to FailureReason.LLM_ERROR."""
        errors = [
            LLMError(LLMErrorType.NETWORK_ERROR, "Network error"),
            RateLimitedError("Rate limited"),
            AuthenticationError("Auth failed"),
            TimeoutError("Timeout"),
            ContextLengthError("Context too long"),
            InvalidRequestError("Invalid request"),
            ProviderError("Provider error"),
            ContentFilterError("Content blocked"),
        ]

        for error in errors:
            assert error.to_failure_reason() == FailureReason.LLM_ERROR


class TestErrorDetails:
    """Tests for error details capture."""

    def test_error_details(self) -> None:
        """Extra details are captured in the details dict."""
        error = LLMError(
            error_type=LLMErrorType.INVALID_RESPONSE,
            message="Failed to parse response",
            details={
                "raw_response": '{"malformed": json}',
                "status_code": 200,
            },
        )

        assert "raw_response" in error.details
        assert error.details["status_code"] == 200

    def test_context_length_error_captures_tokens(self) -> None:
        """ContextLengthError captures tokens_used in details."""
        error = ContextLengthError(
            message="Context length exceeded",
            tokens_used=150000,
        )

        assert error.details["tokens_used"] == 150000
        assert error.error_type == LLMErrorType.CONTEXT_LENGTH
        assert error.retryable is False


class TestTimeoutError:
    """Tests for TimeoutError behavior."""

    def test_timeout_is_retryable(self) -> None:
        """TimeoutError is retryable per the error mapping."""
        error = TimeoutError(message="Request timed out after 120s")

        assert error.retryable is True
        assert error.error_type == LLMErrorType.TIMEOUT


class TestInvalidRequestError:
    """Tests for InvalidRequestError (HTTP 400)."""

    def test_invalid_request_not_retryable(self) -> None:
        """InvalidRequestError is not retryable."""
        error = InvalidRequestError(message="Malformed JSON in request body")

        assert error.retryable is False
        assert error.error_type == LLMErrorType.INVALID_REQUEST

    def test_invalid_request_with_details(self) -> None:
        """InvalidRequestError can capture extra details."""
        error = InvalidRequestError(
            message="Invalid model name",
            details={"model": "nonexistent/model"}
        )

        assert error.details["model"] == "nonexistent/model"


class TestProviderError:
    """Tests for ProviderError (HTTP 5xx)."""

    def test_provider_error_is_retryable(self) -> None:
        """ProviderError is retryable."""
        error = ProviderError(
            message="Internal server error",
            status_code=500
        )

        assert error.retryable is True
        assert error.error_type == LLMErrorType.PROVIDER_ERROR
        assert error.details["status_code"] == 500

    def test_provider_error_various_codes(self) -> None:
        """ProviderError captures various status codes."""
        for code in [500, 502, 503]:
            error = ProviderError(
                message=f"Server error {code}",
                status_code=code
            )
            assert error.details["status_code"] == code


class TestContentFilterError:
    """Tests for ContentFilterError."""

    def test_content_filter_not_retryable(self) -> None:
        """ContentFilterError is not retryable."""
        error = ContentFilterError(message="Content blocked by safety filter")

        assert error.retryable is False
        assert error.error_type == LLMErrorType.CONTENT_FILTER


class TestAllErrorTypes:
    """Tests for all error types defined in the enum."""

    def test_all_error_types_exist(self) -> None:
        """All expected error types are defined in LLMErrorType."""
        expected_types = [
            "rate_limited",
            "timeout",
            "auth_failed",
            "invalid_request",
            "invalid_response",
            "context_length",
            "content_filter",
            "provider_error",
            "network_error",
        ]

        actual_types = [e.value for e in LLMErrorType]

        for expected in expected_types:
            assert expected in actual_types, f"Missing error type: {expected}"
