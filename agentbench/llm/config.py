from enum import StrEnum
from pydantic import BaseModel, Field, SecretStr
from typing import Any

class LLMProvider(StrEnum):
    OPENROUTER = "openrouter"

class SamplingParams(BaseModel):
    temperature: float = Field(
        default = 0.0,
        ge = 0.0,
        le = 2.0
    )
    top_p: float = Field(
        default = 1.0,
        ge = 0.0,
        le = 1.0
    )
    max_tokens: int = Field(
        default = 4096,
        ge = 1,
        le = 128000
    )
    stop_sequences: list[str] | None = None

class RetryPolicy(BaseModel):
    max_retries: int = Field(
        default = 3,
        ge = 0,
        le = 10
    )
    initial_delay_sec: float = Field(
        default = 1.0,
        ge = 0.1,
    )
    max_delay_sec: float = Field(
        default = 60.0,
        ge = 1.0,
    )
    exponential_base: float = Field(
        default = 2.0,
        ge = 1.0,
    )

class ProviderConfig(BaseModel):
    provider: LLMProvider
    model_name: str
    api_key: SecretStr | None = None
    base_url: str | None = None
    timeout_sec: float = Field(
        default = 120,
        ge = 10,
        le = 600
    )

class LLMConfig(BaseModel):
    provider_config: ProviderConfig
    sampling: SamplingParams = Field(
        default_factory = SamplingParams
    )
    retry_policy: RetryPolicy = Field(
        default_factory = RetryPolicy
    )
    prompt_version: str | None = None

    def to_safe_dict(self) -> dict[str, Any]:
        data = self.model_dump(
            mode = "json"
        )

        if "provider_config" in data and "api_key" in data["provider_config"]:
            data["provider_config"]["api_key"] = "[REDACTED]"

        return data

