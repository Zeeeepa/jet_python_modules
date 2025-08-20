import asyncio
import json
import mcp.types

from typing import Any, Dict, List, Optional, TypedDict


from jet.file.utils import save_file
from jet.llm.mlx.mlx_types import ChatTemplateArgs, Message
from jet.llm.mlx.mlx_utils import create_mlx_tools, create_tool_function, parse_tool_call
from jet.logger import logger
from jet.models.model_registry.transformers.mlx_model_registry import MLXModelRegistry
from jet.models.model_types import LLMModelType
from jet.servers.mcp.utils import parse_tool_requests
from jet.transformers.formatters import format_json
from jet.servers.mcp.mcp_classes import ToolRequest, ToolInfo, ExecutedToolResponse
from jet.servers.mcp.mcp_utils import discover_tools, execute_tool, validate_tool_arguments
from jet.servers.mcp.config import MCP_SERVER_PATH


async def validate_and_execute_tool(
    tool_request: Dict[str, Any],
    tools: List[ToolInfo],
    mcp_server_path: str = MCP_SERVER_PATH
) -> ExecutedToolResponse:
    """
    Validate and execute a tool request from a dictionary.

    Args:
        tool_request: Dictionary with 'tool' and 'arguments' keys.
        tools: List of ToolInfo containing tool metadata.
        mcp_server_path: Path to the MCP server for tool execution.

    Returns:
        ExecutedToolResponse: The result of the tool execution.

    Raises:
        RuntimeError: If the tool is not found or execution fails.
    """
    tool_name = tool_request["tool"]
    tool_info = next((t for t in tools if t["name"] == tool_name), None)
    if not tool_info:
        raise RuntimeError(f"Tool '{tool_name}' not found")
    validate_tool_arguments(
        tool_request["arguments"], tool_info["schema"], tool_name)

    tool_result = await execute_tool(tool_name, tool_request["arguments"], mcp_server_path)
    formatted_tool_result = ExecutedToolResponse(
        isError=tool_result.isError,
        meta=tool_result.meta or {},
        content=tool_result.structuredContent or {}
    )
    if not formatted_tool_result.isError:
        return formatted_tool_result
    raise RuntimeError(
        f"Error executing tool '{tool_name}':\n{formatted_tool_result.content}"
    )


async def query_tool_requests(llm_response_text: str) -> List[Dict[str, Any]]:
    """
    Parse tool requests from LLM response and return as a list of tool request dicts.

    Args:
        llm_response_text: The LLM response containing tool call(s).

    Returns:
        List[Dict[str, Any]]: List of parsed tool request dictionaries with 'tool' key.
    """
    tool_open = "<tool_call>"
    tool_close = "</tool_call>"
    tool_requests = []
    start_idx = 0

    while True:
        start_tool = llm_response_text.find(tool_open, start_idx)
        if start_tool == -1:
            break
        start_tool += len(tool_open)
        end_tool = llm_response_text.find(tool_close, start_tool)
        if end_tool == -1:
            break
        try:
            tool_call = json.loads(
                llm_response_text[start_tool:end_tool].strip())
            # Rename 'name' to 'tool' to match ToolRequest model
            if "name" in tool_call:
                tool_call["tool"] = tool_call.pop("name")
            tool_requests.append(tool_call)
        except json.JSONDecodeError:
            logger.error(
                f"Invalid JSON in tool call: {llm_response_text[start_tool:end_tool]}")
        start_idx = end_tool + len(tool_close)

    return tool_requests


async def query_tool_responses(
    tool_requests: List[Dict[str, Any]],
    tools: List[ToolInfo],
    mcp_server_path: str,
) -> List[Dict[str, Any]]:
    """
    Process tool requests and return their responses.

    Args:
        tool_requests: List of tool request dictionaries with 'tool' and 'arguments' keys.
        tools: List of ToolInfo containing tool metadata.
        mcp_server_path: Path to the MCP server for tool execution.

    Returns:
        List[Dict[str, Any]]: List of tool response dictionaries.
    """
    tool_responses = []
    for tool_request in tool_requests:
        response = await validate_and_execute_tool(tool_request, tools, mcp_server_path)
        tool_responses.append({
            "isError": response.isError,
            "meta": response.meta,
            "structuredContent": response.content
        })
    return tool_responses


def generate_response(
    messages: List[Message],
    model_path: LLMModelType,
    log_dir: str,
    tools: Optional[List[ToolInfo]] = None,
) -> str:
    # Load MLX model
    model = MLXModelRegistry.load_model(model_path, log_dir=log_dir)
    chat_template_args: ChatTemplateArgs = {
        "enable_thinking": False,
    }

    mlx_tools = None
    if tools:
        # Create sync tool functions for MLX compatibility
        mlx_tools = create_mlx_tools(tools)

    # Generate response
    llm_response = model.chat(
        messages,
        max_tokens=4000,
        temperature=0.7,
        verbose=True,
        chat_template_args=chat_template_args,
        tools=mlx_tools,
    )
    llm_response_text = llm_response["content"]
    return llm_response_text


def format_tool_request_messages(prompt: str, tools: List[ToolInfo], previous_messages: List[Message] = []) -> List[Message]:
    tool_descriptions = "\n\n".join(
        [f"Tool: {t['name']}\nDescription: {t['description']}\nInput Schema: {json.dumps(t['schema'], indent=2)}\nOutput Schema: {json.dumps(t['outputSchema'], indent=2)}" for t in tools])
    system_prompt = f"You are an AI assistant with MCP tools:\n{tool_descriptions}\nUse JSON for tool requests: {{'tool': 'name', 'arguments': {{'arg': 'value'}}}}."

    # Filter out existing system messages and keep only user/assistant messages
    filtered_messages = [m for m in previous_messages if m["role"] != "system"]
    # Add the new user prompt
    filtered_messages.append({"role": "user", "content": prompt})
    # Prepend the single system message
    all_messages: List[Message] = [
        {"role": "system", "content": system_prompt}] + filtered_messages
    return all_messages


def format_tool_response_messages(llm_response_text: str, tool_response: ExecutedToolResponse, previous_messages: List[Message] = []) -> List[Message]:
    # Start with previous messages, ensuring no duplicates
    messages = [m for m in previous_messages if m["content"] !=
                llm_response_text and m["content"] != f"Tool response: {tool_response}"]
    # Append the assistant's response and the tool response
    messages.append({"role": "assistant", "content": llm_response_text})
    messages.append(
        {"role": "user", "content": f"Tool response: {tool_response}"})
    return messages


async def query_llm(
    prompt: str,
    model: LLMModelType,
    tools: List[ToolInfo],
    output_dir: str,
    previous_messages: List[Message] = [],
    mcp_server_path: str = MCP_SERVER_PATH,
):
    # Initialize message history with tool request messages
    all_messages = format_tool_request_messages(
        prompt, tools, previous_messages=previous_messages)
    log_dir = f"{output_dir}/chats"
    llm_response_text = generate_response(
        all_messages, model, log_dir, tools=tools)
    tool_requests = await query_tool_requests(llm_response_text)
    logger.gray(f"\nTool Requests ({len(tool_requests)})")
    logger.success(format_json(tool_requests))
    save_file(tool_requests, f"{output_dir}/tool_requests.json")
    tool_responses = await query_tool_responses(tool_requests, tools, mcp_server_path)
    logger.gray(f"\nTool Responses ({len(tool_responses)})")
    logger.success(format_json(tool_responses))
    save_file(tool_responses, f"{output_dir}/tool_responses.json")
    tool_results = [response["structuredContent"]
                    for response in tool_responses]
    save_file(tool_results, f"{output_dir}/tool_results.json")
    llm_tool_response_texts = []
    llm_tool_response_tool_results = []
    current_messages = all_messages
    for tool_response in tool_responses:
        # Update message history with tool response messages
        current_messages = format_tool_response_messages(
            llm_response_text, tool_response, current_messages)
        tool_response_text = generate_response(
            current_messages, model, log_dir)
        llm_tool_response_texts.append(tool_response_text)
        save_file(llm_tool_response_texts,
                  f"{output_dir}/llm_tool_response_texts.json")
        tool_calls = parse_tool_call(tool_response_text)
        save_file(
            tool_calls, f"{output_dir}/llm_tool_response_tool_calls.json")
        if isinstance(tool_calls, list):
            for tool_call in tool_calls:
                sub_tool_response = await query_tool_responses([tool_call], tools, mcp_server_path)
                llm_tool_response_tool_results.extend(
                    [r["structuredContent"] for r in sub_tool_response])
        elif tool_calls:
            sub_tool_response = await query_tool_responses([tool_calls], tools, mcp_server_path)
            llm_tool_response_tool_results.extend(
                [r["structuredContent"] for r in sub_tool_response])
        save_file(llm_tool_response_tool_results,
                  f"{output_dir}/llm_tool_response_tool_results.json")
    return llm_response_text, current_messages


async def chat_session(model: LLMModelType, output_dir: str, mcp_server_path: str = MCP_SERVER_PATH):
    tools = await discover_tools(mcp_server_path)
    logger.gray(f"\nTools ({len(tools)})")
    logger.success(format_json(tools))
    save_file(tools, f"{output_dir}/tools.json")

    logger.debug(
        f"Discovered {len(tools)} tools: {[t['name'] for t in tools]}")
    messages = []
    while True:
        user_input = input("You: ")
        if user_input.lower() in ['exit', 'quit']:
            logger.debug("Ending chat session.")
            break
        response, messages = await query_llm(
            user_input,
            model=model,
            tools=tools,
            output_dir=output_dir,
            previous_messages=messages,
            mcp_server_path=mcp_server_path,
        )
        print(f"Assistant: {response}")

if __name__ == "__main__":
    import os
    import shutil
    from pathlib import Path

    output_dir = os.path.join(
        os.path.dirname(__file__), "generated", os.path.splitext(os.path.basename(__file__))[0])
    shutil.rmtree(output_dir, ignore_errors=True)

    mcp_server_path = str(Path(__file__).parent / "mcp_server.py")

    model_path: LLMModelType = "qwen3-1.7b-4bit"

    # sample_prompt = "Navigate to https://www.iana.org and summarize the text content in 100 words or less."
    asyncio.run(chat_session(model_path, output_dir))
