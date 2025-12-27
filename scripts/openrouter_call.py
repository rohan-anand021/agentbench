from agentbench.llm.messages import InputMessage, MessageRole
from agentbench.llm.openrouter import OpenRouterClient
from agentbench.llm.config import LLMConfig, ProviderConfig, LLMProvider
from dotenv import load_dotenv
import os
import asyncio

load_dotenv()

OPENROUTER_API_URL = "https://openrouter.ai/api/v1/responses"

llm_provider = LLMProvider.OPENROUTER

provider_config = ProviderConfig(
    provider = llm_provider,
    model_name = "mistralai/devstral-2512:free",
    api_key = os.getenv("OPENROUTER_API_KEY"),
    base_url=OPENROUTER_API_URL,
    timeout_sec = 30
)

llm_config = LLMConfig(
    provider_config = provider_config
)

client = OpenRouterClient(
    config = llm_config
)

async def main():
    response = await client.complete(
        [InputMessage(
            role = MessageRole.USER,
            content = "hello"
        )]
    )

    print(response.model_dump_json(
        indent = 2
    ))

asyncio.run(main())

