from agentbench.agents.prompts.system_v1 import (
    SYSTEM_PROMPT_V1,
    get_system_prompt,
    get_system_prompt_version,
)


def test_get_system_prompt_returns_constant():
    assert get_system_prompt() == SYSTEM_PROMPT_V1


def test_get_system_prompt_version_format():
    version = get_system_prompt_version()
    assert version.startswith("system_v1@")
    suffix = version.split("@", 1)[1]
    assert len(suffix) == 12
