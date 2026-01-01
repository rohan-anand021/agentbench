import os
from pathlib import Path
from pydantic import Secret, SecretStr
from pydantic_settings import BaseSettings
from agentbench.llm.config import LLMConfig, ProviderConfig, LLMProvider

class AgentBenchSettings(BaseSettings):
    openrouter_api_key: SecretStr | None = None
    
    default_model: str = "mistralai/devstral-2512:free"
    default_provider: LLMProvider = LLMProvider.OPENROUTER

    artifacts_dir: Path = Path("artifacts")
    tasks_dir: Path = Path("tasks")
    prompts_dir: Path = Path("agentbench/llm/prompts")

    model_config = {
        "env_prefix": "AGENTBENCH_",
        "env_file": ".env",
        "extra": "ignore",
    }

def load_settings() -> AgentBenchSettings:
    return AgentBenchSettings()

def get_api_key_for_provider(
    settings: AgentBenchSettings,
    provider: LLMProvider
) -> SecretStr | None:
    return settings.openrouter_api_key
