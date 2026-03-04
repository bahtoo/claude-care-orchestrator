"""
Prior Auth Agent — wraps Phase 2's PriorAuthGenerator as a pipeline agent.

Receives context from Eligibility Agent, runs PA only for codes
that require it, and hands off to Claims Agent.
"""

from __future__ import annotations

from care_orchestrator.agents import BaseAgent
from care_orchestrator.models import AgentResult, AgentTask, RCMStage
from care_orchestrator.prior_auth import PriorAuthGenerator


class PriorAuthAgent(BaseAgent):
    """Runs prior authorization for procedures that require it."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        policies_dir: str = "config/policies",
    ) -> None:
        super().__init__(name="prior_auth_agent", stage=RCMStage.PRIOR_AUTH)
        self._pa_generator = PriorAuthGenerator(
            api_key=api_key, model=model, policies_dir=policies_dir
        )

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == RCMStage.PRIOR_AUTH

    def _execute(self, task: AgentTask) -> AgentResult:
        pa_required = task.context.get("pa_required_codes", [])
        payer_id = task.context.get("payer_id", "")
        clinical_text = task.input_data.get("clinical_text", "")
        redacted_text = task.context.get("redacted_text", clinical_text)

        # If no PA is required, pass through
        if not pa_required:
            return AgentResult(
                agent_name=self.name,
                stage=self.stage,
                success=True,
                output_data={
                    "pa_status": "not_required",
                    "pa_number": "",
                },
                recommendations=["No prior auth required"],
            )

        # Run PA for the clinical text
        result = self._pa_generator.submit(
            clinical_text=redacted_text,
            payer_id=payer_id,
        )

        pa_status = result.status.value
        pa_number = f"PA-{payer_id[:3].upper()}-001" if pa_status == "approved" else ""

        recommendations: list[str] = []
        if pa_status == "denied" and result.request:
            unmet = result.request.necessity_decision.criteria_unmet
            if unmet:
                recommendations.append(f"Consider appeal — unmet: {', '.join(unmet)}")
        if pa_status == "pending_additional_info" and result.request:
            missing = result.request.necessity_decision.missing_documentation
            if missing:
                recommendations.append(f"Gather: {', '.join(missing)}")

        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=True,
            output_data={
                "pa_status": pa_status,
                "pa_number": pa_number,
                "pa_summary": result.summary,
            },
            recommendations=recommendations,
        )
