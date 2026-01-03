from __future__ import annotations

import asyncio
import json
from typing import Any

from agentbench.agents.base import Agent
from agentbench.agents.prompts.system_v1 import get_system_prompt
from agentbench.agents.types import (
    AgentAction,
    AgentDecision,
    AgentState,
    StopReason,
)
from agentbench.llm.client import LLMClient
from agentbench.llm.config import LLMConfig
from agentbench.llm.messages import (
    InputItem,
    InputMessage,
    LLMResponse,
    MessageRole,
    ToolDefinition,
)
from agentbench.tools.contract import ToolName, ToolRequest


class LLMAgentV0(Agent):
    def __init__(self, config: LLMConfig, client: LLMClient):
        super().__init__(config)
        self.client = client
        self._request_counter = 0

    @property
    def variant_name(self) -> str:
        return "llm_v0"

    def decide(self, state: AgentState) -> AgentAction:
        observation = self.format_observation(state)
        input_items = self._build_messages(observation)
        tools = self._get_tool_definitions()
        response = self._run_completion(input_items, tools)
        return self._parse_llm_response(response, state)

    def format_observation(self, state: AgentState) -> str:
        lines = [
            f"Task: {state.task_id}",
            f"Step: {state.step_number}",
            f"Steps remaining: {state.budget_remaining_steps}",
            f"Time remaining (sec): {state.budget_remaining_sec:.1f}",
        ]

        if state.last_test_exit_code is not None:
            lines.append(f"Last test exit code: {state.last_test_exit_code}")

        if state.last_test_output:
            lines.append("Last test output:")
            lines.append(state.last_test_output)

        if state.patches_applied:
            lines.append("Patches applied:")
            lines.extend(state.patches_applied[-5:])

        return "\n".join(lines).strip()

    def _build_messages(self, observation: str) -> list[InputItem]:
        system = InputMessage(
            role=MessageRole.SYSTEM,
            content=get_system_prompt(),
        )
        user = InputMessage(
            role=MessageRole.USER,
            content=observation,
        )
        return [system, user]

    def _get_tool_definitions(self) -> list[ToolDefinition]:
        return [
            ToolDefinition(
                name=ToolName.LIST_FILES.value,
                description="List files in the workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "root": {"type": "string"},
                        "glob": {"type": "string"},
                    },
                },
            ),
            ToolDefinition(
                name=ToolName.READ_FILE.value,
                description="Read a file from the workspace.",
                parameters={
                    "type": "object",
                    "properties": {
                        "path": {"type": "string"},
                        "start_line": {"type": "integer"},
                        "end_line": {"type": "integer"},
                    },
                    "required": ["path"],
                },
            ),
            ToolDefinition(
                name=ToolName.SEARCH.value,
                description="Search for text in files.",
                parameters={
                    "type": "object",
                    "properties": {
                        "query": {"type": "string"},
                        "glob": {"type": "string"},
                        "max_results": {"type": "integer"},
                        "context_lines": {"type": "integer"},
                        "is_regex": {"type": "boolean"},
                    },
                    "required": ["query"],
                },
            ),
            ToolDefinition(
                name=ToolName.APPLY_PATCH.value,
                description="Apply a unified diff patch.",
                parameters={
                    "type": "object",
                    "properties": {
                        "unified_diff": {"type": "string"},
                    },
                    "required": ["unified_diff"],
                },
            ),
            ToolDefinition(
                name=ToolName.RUN.value,
                description="Run a shell command.",
                parameters={
                    "type": "object",
                    "properties": {
                        "command": {"type": "string"},
                        "timeout_sec": {"type": "integer"},
                        "env": {"type": "object"},
                    },
                    "required": ["command"],
                },
            ),
        ]

    def _parse_llm_response(
        self,
        response: LLMResponse,
        state: AgentState,
    ) -> AgentAction:
        if response.error:
            return AgentAction(
                decision=AgentDecision.STOP,
                stop_reason=StopReason.LLM_ERROR,
                reasoning=str(response.error),
            )

        if response.has_tool_calls:
            tool_call = response.tool_calls[0]
            if isinstance(tool_call, dict):
                name = tool_call.get("name")
                args_text = tool_call.get("arguments", "{}")
                call_id = tool_call.get("call_id") or tool_call.get("id")
            else:
                name = tool_call.name
                args_text = tool_call.arguments
                call_id = tool_call.call_id or tool_call.id

            try:
                params: dict[str, Any] = json.loads(args_text) if args_text else {}
            except json.JSONDecodeError:
                return AgentAction(
                    decision=AgentDecision.STOP,
                    stop_reason=StopReason.LLM_ERROR,
                    reasoning="Invalid tool arguments JSON.",
                )

            try:
                tool_enum = ToolName(name)
            except Exception:
                return AgentAction(
                    decision=AgentDecision.STOP,
                    stop_reason=StopReason.LLM_ERROR,
                    reasoning=f"Unknown tool: {name}",
                )

            request_id = call_id or self._next_request_id(state)
            return AgentAction(
                decision=AgentDecision.CALL_TOOL,
                tool_request=ToolRequest(
                    tool=tool_enum,
                    params=params,
                    request_id=request_id,
                ),
            )

        text = (response.text_content or "").strip()
        reason = text or "No tool call returned."
        return AgentAction(
            decision=AgentDecision.STOP,
            stop_reason=StopReason.AGENT_GAVE_UP,
            reasoning=reason,
        )

    def _run_completion(
        self,
        input_items: list[InputItem],
        tools: list[ToolDefinition] | None,
    ) -> LLMResponse:
        async def _call() -> LLMResponse:
            return await self.client.complete(input_items=input_items, tools=tools)

        try:
            loop = asyncio.get_running_loop()
        except RuntimeError:
            return asyncio.run(_call())

        if loop.is_running():
            raise RuntimeError("LLM client called from running event loop.")
        return loop.run_until_complete(_call())

    def _next_request_id(self, state: AgentState) -> str:
        self._request_counter += 1
        return f"{state.run_id}-{state.step_number:04d}-{self._request_counter:02d}"
