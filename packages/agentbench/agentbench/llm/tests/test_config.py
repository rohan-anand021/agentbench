"""Unit tests for LLM config module.

Tests cover:
1. Default values for LLMConfig and related models
2. Field validation (temperature, max_tokens bounds)
3. SecretStr behavior (no exposure in repr)
4. to_safe_dict() redaction behavior
5. Settings loading from environment variables
6. Settings env prefix behavior
"""

import os
import pytest
from pydantic import SecretStr, ValidationError

from agentbench.llm.config import (
    LLMProvider,
    SamplingParams,
    RetryPolicy,
    ProviderConfig,
    LLMConfig,
)
from agentbench.config import (
    AgentBenchSettings,
    load_settings,
    get_api_key_for_provider,
)


class TestLLMConfigDefaults:
    """Tests for default value population."""

    def test_llm_config_defaults(self) -> None:
        """Default values are populated correctly."""
        provider_config = ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="anthropic/claude-3.5-sonnet",
        )
        config = LLMConfig(provider_config=provider_config)

        # Check SamplingParams defaults
        assert config.sampling.temperature == 0.0
        assert config.sampling.top_p == 1.0
        assert config.sampling.max_tokens == 4096
        assert config.sampling.stop_sequences is None

        # Check RetryPolicy defaults
        assert config.retry_policy.max_retries == 3
        assert config.retry_policy.initial_delay_sec == 1.0
        assert config.retry_policy.max_delay_sec == 60.0
        assert config.retry_policy.exponential_base == 2.0

        # Check ProviderConfig defaults
        assert config.provider_config.api_key is None
        assert config.provider_config.base_url is None
        assert config.provider_config.timeout_sec == 120

        # Check LLMConfig defaults
        assert config.prompt_version is None

    def test_sampling_params_defaults(self) -> None:
        """SamplingParams has correct defaults."""
        params = SamplingParams()
        assert params.temperature == 0.0
        assert params.top_p == 1.0
        assert params.max_tokens == 4096
        assert params.stop_sequences is None

    def test_retry_policy_defaults(self) -> None:
        """RetryPolicy has correct defaults."""
        policy = RetryPolicy()
        assert policy.max_retries == 3
        assert policy.initial_delay_sec == 1.0
        assert policy.max_delay_sec == 60.0
        assert policy.exponential_base == 2.0


class TestTemperatureBounds:
    """Tests for temperature validation."""

    def test_llm_config_temperature_bounds(self) -> None:
        """Temperature outside 0.0-2.0 raises ValidationError."""
        # Valid temperature at boundaries
        params_low = SamplingParams(temperature=0.0)
        assert params_low.temperature == 0.0

        params_high = SamplingParams(temperature=2.0)
        assert params_high.temperature == 2.0

        params_mid = SamplingParams(temperature=1.0)
        assert params_mid.temperature == 1.0

        # Invalid temperature below 0
        with pytest.raises(ValidationError) as exc_info:
            SamplingParams(temperature=-0.1)
        assert "temperature" in str(exc_info.value).lower()

        # Invalid temperature above 2.0
        with pytest.raises(ValidationError) as exc_info:
            SamplingParams(temperature=2.1)
        assert "temperature" in str(exc_info.value).lower()


class TestMaxTokensBounds:
    """Tests for max_tokens validation."""

    def test_llm_config_max_tokens_bounds(self) -> None:
        """Max tokens outside 1-128000 raises ValidationError."""
        # Valid max_tokens at boundaries
        params_low = SamplingParams(max_tokens=1)
        assert params_low.max_tokens == 1

        params_high = SamplingParams(max_tokens=128000)
        assert params_high.max_tokens == 128000

        # Invalid max_tokens below 1
        with pytest.raises(ValidationError) as exc_info:
            SamplingParams(max_tokens=0)
        assert "max_tokens" in str(exc_info.value).lower()

        # Invalid max_tokens above 128000
        with pytest.raises(ValidationError) as exc_info:
            SamplingParams(max_tokens=128001)
        assert "max_tokens" in str(exc_info.value).lower()


class TestSecretStrBehavior:
    """Tests for SecretStr handling."""

    def test_provider_config_api_key_is_secret(self) -> None:
        """SecretStr doesn't expose value in repr."""
        secret_key = SecretStr("sk-super-secret-key-12345")
        provider_config = ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="anthropic/claude-3.5-sonnet",
            api_key=secret_key,
        )

        # The secret value should not appear in repr or str
        config_repr = repr(provider_config)
        config_str = str(provider_config)

        assert "sk-super-secret-key-12345" not in config_repr
        assert "sk-super-secret-key-12345" not in config_str

        # But we can still get the value when needed
        assert provider_config.api_key is not None
        assert provider_config.api_key.get_secret_value() == "sk-super-secret-key-12345"


class TestToSafeDict:
    """Tests for to_safe_dict() redaction."""

    def test_to_safe_dict_redacts_api_key(self) -> None:
        """to_safe_dict() returns '[REDACTED]' for api_key."""
        secret_key = SecretStr("sk-super-secret-key-12345")
        provider_config = ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="anthropic/claude-3.5-sonnet",
            api_key=secret_key,
        )
        config = LLMConfig(provider_config=provider_config)

        safe_dict = config.to_safe_dict()

        # API key should be redacted
        assert safe_dict["provider_config"]["api_key"] == "[REDACTED]"

        # Other values should be present
        assert safe_dict["provider_config"]["provider"] == "openrouter"
        assert safe_dict["provider_config"]["model_name"] == "anthropic/claude-3.5-sonnet"
        assert safe_dict["sampling"]["temperature"] == 0.0
        assert safe_dict["retry_policy"]["max_retries"] == 3

    def test_to_safe_dict_without_api_key(self) -> None:
        """to_safe_dict() works when api_key is None."""
        provider_config = ProviderConfig(
            provider=LLMProvider.OPENROUTER,
            model_name="anthropic/claude-3.5-sonnet",
        )
        config = LLMConfig(provider_config=provider_config)

        safe_dict = config.to_safe_dict()

        # API key should still be redacted (None becomes "[REDACTED]")
        assert safe_dict["provider_config"]["api_key"] == "[REDACTED]"


class TestSettingsFromEnv:
    """Tests for settings loading from environment."""

    def test_settings_from_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings load from environment variables."""
        # Set environment variables with AGENTBENCH_ prefix
        monkeypatch.setenv("AGENTBENCH_OPENROUTER_API_KEY", "test-api-key-123")
        monkeypatch.setenv("AGENTBENCH_DEFAULT_MODEL", "openai/gpt-4")
        monkeypatch.setenv("AGENTBENCH_DEFAULT_PROVIDER", "openrouter")

        settings = AgentBenchSettings()

        assert settings.openrouter_api_key is not None
        assert settings.openrouter_api_key.get_secret_value() == "test-api-key-123"
        assert settings.default_model == "openai/gpt-4"
        assert settings.default_provider == LLMProvider.OPENROUTER

    def test_settings_defaults_when_no_env(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Settings use defaults when env vars are not set."""
        # Clear any existing env vars
        monkeypatch.delenv("AGENTBENCH_OPENROUTER_API_KEY", raising=False)
        monkeypatch.delenv("AGENTBENCH_DEFAULT_MODEL", raising=False)
        monkeypatch.delenv("AGENTBENCH_DEFAULT_PROVIDER", raising=False)

        settings = AgentBenchSettings()

        assert settings.openrouter_api_key is None
        assert settings.default_model == "mistralai/devstral-2512:free"
        assert settings.default_provider == LLMProvider.OPENROUTER


class TestSettingsEnvPrefix:
    """Tests for AGENTBENCH_ env prefix behavior."""

    def test_settings_env_prefix(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Only AGENTBENCH_ prefixed vars are loaded."""
        # Set a var WITHOUT the prefix - should be ignored
        monkeypatch.setenv("OPENROUTER_API_KEY", "wrong-key-no-prefix")
        # Set a var WITH the prefix - should be loaded
        monkeypatch.setenv("AGENTBENCH_OPENROUTER_API_KEY", "correct-key-with-prefix")

        settings = AgentBenchSettings()

        assert settings.openrouter_api_key is not None
        assert settings.openrouter_api_key.get_secret_value() == "correct-key-with-prefix"

    def test_settings_prefix_isolation(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """Vars without AGENTBENCH_ prefix don't affect settings."""
        # Clear the prefixed var
        monkeypatch.delenv("AGENTBENCH_OPENROUTER_API_KEY", raising=False)
        # Set only the non-prefixed var
        monkeypatch.setenv("OPENROUTER_API_KEY", "should-be-ignored")

        settings = AgentBenchSettings()

        # Should be None because we only look for AGENTBENCH_ prefixed vars
        assert settings.openrouter_api_key is None


class TestGetApiKeyForProvider:
    """Tests for get_api_key_for_provider function."""

    def test_get_api_key_for_openrouter(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_api_key_for_provider returns OpenRouter API key."""
        monkeypatch.setenv("AGENTBENCH_OPENROUTER_API_KEY", "openrouter-key-123")

        settings = AgentBenchSettings()
        api_key = get_api_key_for_provider(settings, LLMProvider.OPENROUTER)

        assert api_key is not None
        assert api_key.get_secret_value() == "openrouter-key-123"

    def test_get_api_key_when_not_set(self, monkeypatch: pytest.MonkeyPatch) -> None:
        """get_api_key_for_provider returns None when not set."""
        monkeypatch.delenv("AGENTBENCH_OPENROUTER_API_KEY", raising=False)

        settings = AgentBenchSettings()
        api_key = get_api_key_for_provider(settings, LLMProvider.OPENROUTER)

        assert api_key is None


class TestLoadSettings:
    """Tests for load_settings function."""

    def test_load_settings_returns_instance(self) -> None:
        """load_settings returns an AgentBenchSettings instance."""
        settings = load_settings()
        assert isinstance(settings, AgentBenchSettings)
