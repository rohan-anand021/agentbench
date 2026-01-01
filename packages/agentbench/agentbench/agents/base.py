from __future__ import annotations
import logging
from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
from typing import TYPE_CHECKING
from agentbench.llm.client import LLMConfig
from agentbench.tasks.models import TaskSpec
from agentbench.schemas.attempt_record import AttemptRecord
from agentbench.agents.types import AgentState, AgentAction, AgentResult

if TYPE_CHECKING:
    from agentbench.sandbox.docker_sandbox import DockerSandbox

logger = logging.getLogger(__name__)

@dataclass
class AgentResult:
    success: bool
    steps_taken: int
    patch_files: list[str]
    duration_sec: float
    stopped_reason: str
    exit_code: int


class Agent(ABC):

    def __init__(
        self,
        config: LLMConfig | None = None
    ):
        self.config = config

    @property
    @abstractmethod
    def variant_name(self) -> str:
       """Unique identifier for this agent variant (e.g., 'llm_v0', 'scripted')."""
       pass

    @abstractmethod
    def run(
        self,
        task: TaskSpec,
        sandbox: "DockerSandbox",
        workspace_root: Path,
        artifacts_dir: Path,
        failing_output: str,
    ) -> AgentResult:
        """
        Attempt to fix a failing test.
        
        Args:
            task: The task specification
            workspace_root: Path to the sandbox workspace
            artifacts_dir: Path to store agent artifacts
            failing_output: stdout/stderr from the failing test run
        
        Returns:
            AgentResult with success/failure and metadata
        """
        pass

    @abstractmethod
    def decide(self, state: AgentState) -> AgentAction:
        """
        Given the current state, decide what to do next.
        
        This is the core decision function. It should:
        - Analyze the current state (test output, history, budget)
        - Return either a tool call or a stop decision
        
        Args:
            state: Current agent state with all context
        
        Returns:
            AgentAction specifying the next action
        """
        # TODO: Implement decision logic
        pass
    
    @abstractmethod
    def format_observation(self, state: AgentState) -> str:
        """
        Format the current state as an observation string for the LLM.
        
        This converts the structured state into a prompt-friendly format.
        
        Args:
            state: Current agent state
        
        Returns:
            Formatted observation string
        """
        # TODO: Format state for LLM consumption
        pass

