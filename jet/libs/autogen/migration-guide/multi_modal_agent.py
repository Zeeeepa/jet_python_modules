"""Handle multi-modal inputs with an AssistantAgent in AutoGen v0.4.

This module shows how to use an `AssistantAgent` in AutoGen v0.4 to process multi-modal inputs (text and images) when the model client supports vision capabilities. It sends a `MultiModalMessage` with an image and text, demonstrating asynchronous message handling with cancellation support.
"""

import asyncio
from pathlib import Path
from autogen_agentchat.messages import MultiModalMessage
from autogen_agentchat.agents import AssistantAgent
from autogen_core import CancellationToken, Image
from jet.adapters.autogen.ollama_client import OllamaChatCompletionClient


async def main() -> None:
    model_client = OpenAIChatCompletionClient(
        model="gpt-4o", seed=42, temperature=0)
    assistant = AssistantAgent(
        name="assistant",
        system_message="You are a helpful assistant.",
        model_client=model_client,
    )
    cancellation_token = CancellationToken()
    message = MultiModalMessage(
        content=["Here is an image:", Image.from_file(Path("test.png"))],
        source="user",
    )
    response = await assistant.on_messages([message], cancellation_token)
    print(response)
    await model_client.close()

asyncio.run(main())
