from dataclasses import dataclass
from abc import ABC, abstractmethod
from pathlib import Path
from agentbench.tasks.models import TaskSpec
from agentbench.schemas.attempt_record import AttemptRecord

@dataclass
class AgentResult:
    success: bool
    steps_taken: int
    patch_files: list[str]
    duration_sec: float
    stopped_reason: str
class Agent(ABC):

    @abstractmethod
    def run(
        self,
        task: TaskSpec,
        workspace_root: Path,
        artifacts_dir: Path,
        failing_output: str
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

