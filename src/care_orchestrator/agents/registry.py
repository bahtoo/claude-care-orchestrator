"""
Agent Registry — discovers, manages, and routes tasks to agents.

Supports agent chaining: the output of one agent becomes
the context input for the next agent in the pipeline.
"""

from __future__ import annotations

from care_orchestrator.agents import BaseAgent
from care_orchestrator.logging_config import logger
from care_orchestrator.models import AgentResult, AgentTask


class AgentRegistry:
    """Registry that manages available agents and routes tasks."""

    def __init__(self) -> None:
        self._agents: dict[str, BaseAgent] = {}

    def register(self, agent: BaseAgent) -> None:
        """Register an agent by name."""
        self._agents[agent.name] = agent
        logger.info(f"Registered agent: {agent.name} (stage: {agent.stage})")

    def get(self, name: str) -> BaseAgent | None:
        """Get an agent by name."""
        return self._agents.get(name)

    def get_for_stage(self, stage: str) -> BaseAgent | None:
        """Get the agent registered for a specific RCM stage."""
        for agent in self._agents.values():
            if agent.stage == stage:
                return agent
        return None

    @property
    def available_agents(self) -> list[str]:
        """List all registered agent names."""
        return list(self._agents.keys())

    def route(self, task: AgentTask) -> AgentResult:
        """
        Route a task to the appropriate agent.

        Finds the first agent that can handle the task and runs it.

        Args:
            task: The task to route.

        Returns:
            AgentResult from the handling agent.
        """
        for agent in self._agents.values():
            if agent.can_handle(task):
                logger.info(f"Routing task '{task.task_type}' → {agent.name}")
                return agent.process(task)

        logger.warning(f"No agent found for task type: {task.task_type}")
        return AgentResult(
            agent_name="registry",
            stage="unknown",
            success=False,
            errors=[f"No agent found for task type: {task.task_type}"],
        )

    def run_chain(self, stages: list[str], initial_task: AgentTask) -> list[AgentResult]:
        """
        Run a chain of agents in sequence.

        Each agent's output is merged into the context for the next agent.

        Args:
            stages: Ordered list of RCM stage names.
            initial_task: The starting task.

        Returns:
            List of AgentResults from each stage.
        """
        results: list[AgentResult] = []
        current_context = dict(initial_task.context)

        for stage in stages:
            agent = self.get_for_stage(stage)
            if agent is None:
                results.append(
                    AgentResult(
                        agent_name="registry",
                        stage=stage,
                        success=False,
                        errors=[f"No agent registered for stage: {stage}"],
                    )
                )
                break

            task = AgentTask(
                task_type=stage,
                input_data=initial_task.input_data,
                context=current_context,
            )

            result = agent.process(task)
            results.append(result)

            if not result.success:
                logger.warning(f"Chain broken at stage '{stage}': {result.errors}")
                break

            # Merge agent output into context for next agent
            current_context.update(result.output_data)

        return results
