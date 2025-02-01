from typing import Iterator, Mapping, Optional, Dict, Any, Union, cast
from langchain_ollama import ChatOllama as BaseChatOllama, OllamaEmbeddings as BaseOllamaEmbeddings
from jet.logger import logger
from langchain_core.language_models import LanguageModelInput
from langchain_core.runnables import RunnableConfig
from langchain_core.messages import BaseMessage
from langchain_core.runnables.config import ensure_config
from langchain_core.outputs import ChatGeneration
from jet.decorators.error import wrap_retry
from ollama import AsyncClient, Client, Message, Options

from shared.events import EventSettings

DETERMINISTIC_LLM_SETTINGS = {
    "seed": 42,
    "temperature": 0,
    "num_keep": 0,
    "num_predict": -1,
}


class ChatOllama(BaseChatOllama):
    def __init__(
        self,
        model: str = "llama3.1",
        base_url: str = "http://localhost:11434",
        client_kwargs: Optional[Dict[str, Any]] = None,
        **kwargs,
    ):
        # Generate headers dynamically
        event = EventSettings.call_ollama_chat_langchain()
        pre_start_hook_start_time = EventSettings.event_data["pre_start_hook"]["start_time"]
        log_filename = event["filename"].split(".")[0]
        logger.log("Log-Filename:", log_filename, colors=["WHITE", "DEBUG"])
        token_count = token_counter(kwargs.get(
            "messages", []), model=model) if kwargs.get("messages") else 0
        headers = {
            "Tokens": str(token_count),
            "Log-Filename": log_filename,
            "Event-Start-Time": pre_start_hook_start_time,
        }

        # Combine provided `client_kwargs` with default headers
        client_kwargs = client_kwargs or {}
        client_kwargs.setdefault("headers", headers)

        options = {**DETERMINISTIC_LLM_SETTINGS, **kwargs}

        # Call the parent class initializer with updated parameters
        super().__init__(model=model, base_url=base_url,
                         client_kwargs=client_kwargs, **options)

    def _chat_params(
        self,
        messages: list[BaseMessage],
        stop: Optional[list[str]] = None,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        from jet.llm.ollama.models import OLLAMA_MODEL_EMBEDDING_TOKENS, OLLAMA_MODEL_NAMES
        from jet.token.token_utils import token_counter

        max_token = 0.4

        params = super()._chat_params(
            messages,
            stop,
            **kwargs
        )
        options: Options = params["options"]
        model: OLLAMA_MODEL_NAMES = params["model"]
        messages = params["messages"]

        model_max_length = OLLAMA_MODEL_EMBEDDING_TOKENS[model]
        max_length = int(model_max_length * max_token)
        token_count = token_counter(messages, model)

        if token_count > max_length:
            raise ValueError(
                f"token_count ({token_count}) must be less than max_length ({max_length})")

        options.num_ctx = model_max_length
        return params

    # def _create_chat_stream(
    #     self,
    #     messages: list[BaseMessage],
    #     stop: Optional[list[str]] = None,
    #     **kwargs: Any,
    # ) -> Iterator[Union[Mapping[str, Any], str]]:
    #     chat_params = self._chat_params(messages, stop, **kwargs)

    #     def run():
    #         if chat_params["stream"]:
    #             yield from self._client.chat(**chat_params)
    #         else:
    #             yield self._client.chat(**chat_params)

    #     yield from wrap_retry(run)

    # def invoke(
    #     self,
    #     input: LanguageModelInput,
    #     config: Optional[RunnableConfig] = None,
    #     *,
    #     stop: Optional[list[str]] = None,
    #     **kwargs: Any,
    # ) -> BaseMessage:
    #     config = ensure_config(config)
    #     result = cast(
    #         ChatGeneration,
    #         self.generate_prompt(
    #             [self._convert_input(input)],
    #             stop=stop,
    #             callbacks=config.get("callbacks"),
    #             tags=config.get("tags"),
    #             metadata=config.get("metadata"),
    #             run_name=config.get("run_name"),
    #             run_id=config.pop("run_id", None),
    #             **kwargs,
    #         ).generations[0][0],
    #     ).message

    #     return result


Ollama = ChatOllama


class OllamaEmbeddings(BaseOllamaEmbeddings):
    pass
