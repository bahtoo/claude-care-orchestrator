"""
Base Agent — abstract interface for all RCM agents.

Every agent in the multi-agent orchestration inherits from BaseAgent
and implements the standard process/can_handle/report interface.
All agent actions are audit-logged automatically.
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod

from care_orchestrator.logging_config import logger
from care_orchestrator.models import AgentResult, AgentTask


class BaseAgent(ABC):
    """Abstract base class for all RCM agents."""

    def __init__(self, name: str, stage: str) -> None:
        self.name = name
        self.stage = stage
        self._last_result: AgentResult | None = None

    @abstractmethod
    def can_handle(self, task: AgentTask) -> bool:
        """Return True if this agent can handle the given task."""

    @abstractmethod
    def _execute(self, task: AgentTask) -> AgentResult:
        """Internal execution logic — subclasses implement this."""

    def process(self, task: AgentTask) -> AgentResult:
        """
        Run the agent on a task with automatic logging and timing.

        Args:
            task: The agent task to process.

        Returns:
            AgentResult with output data and status.
        """
        start = time.monotonic()
        logger.info(f"[{self.name}] Starting task: {task.task_type}")

        try:
            result = self._execute(task)
        except Exception as e:
            elapsed = time.monotonic() - start
            logger.error(f"[{self.name}] Failed after {elapsed:.2f}s: {e}")
            result = AgentResult(
                agent_name=self.name,
                stage=self.stage,
                success=False,
                errors=[str(e)],
            )

        elapsed = time.monotonic() - start
        logger.info(f"[{self.name}] Completed: success={result.success} ({elapsed:.2f}s)")

        self._last_result = result
        return result

    def report(self) -> AgentResult | None:
        """Return the last execution result."""
        return self._last_result
