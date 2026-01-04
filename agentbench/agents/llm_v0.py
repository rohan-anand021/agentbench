from __future__ import annotations

import asyncio
import json
import logging
from typing import Any

from agentbench.agents.base import Agent

logger = logging.getLogger(__name__)
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
from agentbench.util.events import EventLogger, NullEventLogger, NULL_EVENT_LOGGER


class LLMAgentV0(Agent):
    def __init__(
        self,
        config: LLMConfig,
        client: LLMClient,
        event_logger: EventLogger | NullEventLogger | None = None,
    ):
        super().__init__(config)
        self.client = client
        self.event_logger = event_logger or NULL_EVENT_LOGGER
        self._request_counter = 0

    @property
    def variant_name(self) -> str:
        return "llm_v0"

    def decide(self, state: AgentState) -> AgentAction:
        logger.debug("LLM decide called for step %d", state.step_number)
        observation = self.format_observation(state)
        logger.debug("Observation: %s", observation[:500])
        input_items = self._build_messages(observation)
        tools = self._get_tool_definitions()
        response = self._run_completion(input_items, tools)
        logger.debug("LLM response: has_tool_calls=%s, error=%s, text=%s", 
                     response.has_tool_calls, response.error, 
                     (response.text_content or "")[:200])
        action = self._parse_llm_response(response, state)
        logger.info("LLM action: decision=%s, tool=%s, stop_reason=%s",
                    action.decision, 
                    action.tool_request.tool if action.tool_request else None,
                    action.stop_reason)
        return action

    def format_observation(self, state: AgentState) -> str:
        lines = [
            f"Task: {state.task_id}",
            f"Step: {state.step_number}",
            f"Steps remaining: {state.budget_remaining_steps}",
            f"Time remaining (sec): {state.budget_remaining_sec:.1f}",
        ]

        if state.test_command:
            lines.append(f"Test command (use this to run tests): {state.test_command}")

        if state.last_test_exit_code is not None:
            lines.append(f"Last test exit code: {state.last_test_exit_code}")

        if state.last_test_output:
            lines.append("Last test output:")
            lines.append(state.last_test_output)

        # Include tool history so the LLM can see results of previous actions
        if state.tool_history:
            lines.append("\n--- Previous Actions ---")
            # Show recent tool calls (limit to last 10 to avoid context overflow)
            recent_history = state.tool_history[-10:]
            for request, result in recent_history:
                lines.append(f"\n[{request.tool.value}] {json.dumps(request.params)}")
                if result.data:
                    # Format the result data nicely
                    if "output" in result.data:
                        lines.append(f"Result: {result.data['output'][:2000]}")
                    elif "files" in result.data:
                        files = result.data["files"]
                        lines.append(f"Files: {files}")
                        if (
                            isinstance(files, list)
                            and "src" in files
                            and "tests" in files
                        ):
                            lines.append(
                                "Hint: repo uses src/ and tests/. Read the failing test, then the src module."
                            )
                    elif "matches" in result.data:
                        matches = result.data["matches"]
                        if isinstance(matches, list):
                            lines.append(f"Matches ({len(matches)} results):")
                            for match in matches[:5]:  # Limit matches shown
                                lines.append(f"  {match}")
                        else:
                            lines.append(f"Matches: {str(matches)[:1000]}")
                    elif "combined_output" in result.data:
                        lines.append(f"Output:\n{result.data['combined_output'][:2000]}")
                    elif "content" in result.data:
                        lines.append(f"Content:\n{result.data['content'][:3000]}")
                    else:
                        lines.append(f"Result: {str(result.data)[:1000]}")
                elif result.error:
                    lines.append(f"Error: {result.error.message}")

        if state.patches_applied:
            lines.append("\nPatches applied:")
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
                name = tool_call.get("name") or tool_call.get("tool_name")
                args_text = tool_call.get("arguments") or tool_call.get("args")
                call_id = (
                    tool_call.get("call_id")
                    or tool_call.get("tool_call_id")
                    or tool_call.get("id")
                )
                function = tool_call.get("function")
                if not name and isinstance(function, dict):
                    name = function.get("name")
                    args_text = args_text or function.get("arguments")
            else:
                name = tool_call.name
                args_text = tool_call.arguments
                call_id = tool_call.call_id or tool_call.id
                function = getattr(tool_call, "function", None)
                if not name and isinstance(function, dict):
                    name = function.get("name")
                    args_text = args_text or function.get("arguments")

            if isinstance(args_text, dict):
                params = args_text
            elif isinstance(args_text, str):
                try:
                    params = json.loads(args_text) if args_text else {}
                except json.JSONDecodeError:
                    return AgentAction(
                        decision=AgentDecision.STOP,
                        stop_reason=StopReason.LLM_ERROR,
                        reasoning="Invalid tool arguments JSON.",
                    )
            elif args_text is None:
                params = {}
            else:
                return AgentAction(
                    decision=AgentDecision.STOP,
                    stop_reason=StopReason.LLM_ERROR,
                    reasoning="Unsupported tool arguments format.",
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
        diff_text = self._extract_unified_diff(text)
        if diff_text:
            request_id = self._next_request_id(state)
            return AgentAction(
                decision=AgentDecision.CALL_TOOL,
                tool_request=ToolRequest(
                    tool=ToolName.APPLY_PATCH,
                    params={"unified_diff": diff_text},
                    request_id=request_id,
                ),
            )
        # Fallback: if the model didn't call a tool, pick a file from the last list_files.
        read_paths = {
            req.params.get("path")
            for req, _ in state.tool_history
            if req.tool == ToolName.READ_FILE and isinstance(req.params, dict)
        }
        for req, result in reversed(state.tool_history):
            if req.tool != ToolName.LIST_FILES:
                continue
            if not result.data or not result.data.get("files"):
                continue
            files = result.data.get("files")
            if not isinstance(files, list):
                continue
            candidates = [f for f in files if isinstance(f, str) and f not in read_paths]
            if not candidates:
                candidates = [f for f in files if isinstance(f, str)]
            if candidates:
                request_id = self._next_request_id(state)
                return AgentAction(
                    decision=AgentDecision.CALL_TOOL,
                    tool_request=ToolRequest(
                        tool=ToolName.READ_FILE,
                        params={"path": candidates[0]},
                        request_id=request_id,
                    ),
                )
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
            return await self.client.complete(
                input_items=input_items,
                tools=tools,
                event_logger=self.event_logger,
            )

        # Always use asyncio.run() to get a fresh event loop for each call.
        # This avoids issues with closed/stale loops since we create a fresh
        # httpx client for each request anyway.
        return asyncio.run(_call())

    def _next_request_id(self, state: AgentState) -> str:
        self._request_counter += 1
        return f"{state.run_id}-{state.step_number:04d}-{self._request_counter:02d}"

    @staticmethod
    def _extract_unified_diff(text: str) -> str | None:
        if not text:
            return None

        lines = text.splitlines()
        in_diff = False
        diff_lines: list[str] = []

        for line in lines:
            if not in_diff and line.strip().startswith("```diff"):
                in_diff = True
                continue
            if in_diff:
                if line.strip().startswith("```"):
                    break
                diff_lines.append(line)

        if diff_lines and any(l.startswith("--- ") for l in diff_lines):
            return "\n".join(diff_lines).strip()

        start = None
        for i, line in enumerate(lines):
            if line.startswith("--- "):
                start = i
                break
        if start is not None:
            tail = lines[start:]
            if any(l.startswith("+++ ") for l in tail):
                return "\n".join(tail).strip()

        return None
