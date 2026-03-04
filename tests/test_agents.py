"""
Tests for BaseAgent and AgentRegistry.

Tests agent interface, error handling, task routing, and chain execution.
"""

from care_orchestrator.agents import BaseAgent
from care_orchestrator.agents.registry import AgentRegistry
from care_orchestrator.models import AgentResult, AgentTask

# ---------------------------------------------------------------------------
# Test Agent Implementation
# ---------------------------------------------------------------------------


class SuccessAgent(BaseAgent):
    """Test agent that always succeeds."""

    def __init__(self, stage: str = "test") -> None:
        super().__init__(name=f"success_agent_{stage}", stage=stage)

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == self.stage

    def _execute(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=True,
            output_data={"key": "value", "from": self.stage},
        )


class FailAgent(BaseAgent):
    """Test agent that always fails."""

    def __init__(self) -> None:
        super().__init__(name="fail_agent", stage="fail")

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == "fail"

    def _execute(self, task: AgentTask) -> AgentResult:
        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=False,
            errors=["Simulated failure"],
        )


class ErrorAgent(BaseAgent):
    """Test agent that raises an exception."""

    def __init__(self) -> None:
        super().__init__(name="error_agent", stage="error")

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == "error"

    def _execute(self, task: AgentTask) -> AgentResult:
        msg = "Boom!"
        raise ValueError(msg)


# ---------------------------------------------------------------------------
# BaseAgent Tests
# ---------------------------------------------------------------------------


class TestBaseAgent:
    """Tests for the BaseAgent interface."""

    def test_process_returns_result(self):
        agent = SuccessAgent()
        task = AgentTask(task_type="test")
        result = agent.process(task)
        assert result.success is True
        assert result.agent_name == "success_agent_test"

    def test_process_catches_exceptions(self):
        agent = ErrorAgent()
        task = AgentTask(task_type="error")
        result = agent.process(task)
        assert result.success is False
        assert "Boom!" in result.errors[0]

    def test_report_returns_last_result(self):
        agent = SuccessAgent()
        assert agent.report() is None
        task = AgentTask(task_type="test")
        agent.process(task)
        assert agent.report() is not None
        assert agent.report().success is True

    def test_can_handle(self):
        agent = SuccessAgent(stage="coding")
        task_yes = AgentTask(task_type="coding")
        task_no = AgentTask(task_type="claims")
        assert agent.can_handle(task_yes) is True
        assert agent.can_handle(task_no) is False


# ---------------------------------------------------------------------------
# AgentRegistry Tests
# ---------------------------------------------------------------------------


class TestAgentRegistry:
    """Tests for the AgentRegistry."""

    def test_register_and_get(self):
        reg = AgentRegistry()
        agent = SuccessAgent()
        reg.register(agent)
        assert reg.get("success_agent_test") is agent

    def test_get_unknown_returns_none(self):
        reg = AgentRegistry()
        assert reg.get("nonexistent") is None

    def test_available_agents(self):
        reg = AgentRegistry()
        reg.register(SuccessAgent())
        reg.register(FailAgent())
        assert len(reg.available_agents) == 2

    def test_get_for_stage(self):
        reg = AgentRegistry()
        agent = SuccessAgent(stage="coding")
        reg.register(agent)
        assert reg.get_for_stage("coding") is agent
        assert reg.get_for_stage("claims") is None

    def test_route_to_correct_agent(self):
        reg = AgentRegistry()
        reg.register(SuccessAgent(stage="test"))
        reg.register(FailAgent())
        task = AgentTask(task_type="test")
        result = reg.route(task)
        assert result.success is True
        assert result.agent_name == "success_agent_test"

    def test_route_unknown_task(self):
        reg = AgentRegistry()
        task = AgentTask(task_type="unknown")
        result = reg.route(task)
        assert result.success is False
        assert "No agent found" in result.errors[0]

    def test_run_chain_success(self):
        reg = AgentRegistry()
        reg.register(SuccessAgent(stage="stage1"))
        reg.register(SuccessAgent(stage="stage2"))
        task = AgentTask(task_type="stage1", input_data={"text": "hi"})
        results = reg.run_chain(["stage1", "stage2"], task)
        assert len(results) == 2
        assert all(r.success for r in results)

    def test_run_chain_breaks_on_failure(self):
        reg = AgentRegistry()
        reg.register(FailAgent())
        reg.register(SuccessAgent(stage="after"))
        task = AgentTask(task_type="fail")
        results = reg.run_chain(["fail", "after"], task)
        assert len(results) == 1
        assert results[0].success is False

    def test_run_chain_merges_context(self):
        reg = AgentRegistry()
        reg.register(SuccessAgent(stage="s1"))
        reg.register(SuccessAgent(stage="s2"))
        task = AgentTask(
            task_type="s1",
            input_data={},
            context={"initial": True},
        )
        results = reg.run_chain(["s1", "s2"], task)
        assert len(results) == 2

    def test_run_chain_missing_stage(self):
        reg = AgentRegistry()
        task = AgentTask(task_type="x")
        results = reg.run_chain(["missing"], task)
        assert len(results) == 1
        assert results[0].success is False
