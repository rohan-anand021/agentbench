from __future__ import annotations

from abc import ABC, abstractmethod

from agentbench.agents.types import AgentAction, AgentState
from agentbench.llm.config import LLMConfig


class Agent(ABC):
    """Abstract interface for all agents."""

    def __init__(self, config: LLMConfig | None = None):
        """
        Initialize the agent.

        Args:
            config: LLM configuration (None for scripted agents)
        """
        self.config = config

    @property
    @abstractmethod
    def variant_name(self) -> str:
        """Unique identifier for this agent variant (e.g., 'llm_v0', 'scripted')."""
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
        pass
