"""
Eligibility Agent — verifies patient insurance coverage.

Checks payer policy for coverage status, benefit limits,
and returns structured eligibility determination.
"""

from __future__ import annotations

from care_orchestrator.agents import BaseAgent
from care_orchestrator.models import AgentResult, AgentTask, RCMStage
from care_orchestrator.policy_engine import PolicyEngine


class EligibilityAgent(BaseAgent):
    """Verifies patient insurance eligibility and coverage."""

    def __init__(self, policies_dir: str = "config/policies") -> None:
        super().__init__(name="eligibility_agent", stage=RCMStage.ELIGIBILITY)
        self._policy_engine = PolicyEngine(policies_dir=policies_dir)

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == RCMStage.ELIGIBILITY

    def _execute(self, task: AgentTask) -> AgentResult:
        payer_id = task.input_data.get("payer_id", task.context.get("payer_id", ""))
        cpt_codes = task.context.get("cpt_codes", [])
        icd10_codes = task.context.get("icd10_codes", [])

        # Check if payer exists
        policy = self._policy_engine.get_policy(payer_id)
        if policy is None:
            return AgentResult(
                agent_name=self.name,
                stage=self.stage,
                success=False,
                output_data={
                    "is_eligible": False,
                    "payer_id": payer_id,
                },
                errors=[f"Payer '{payer_id}' not found in policy database"],
            )

        # Check coverage for each CPT code
        pa_required_codes: list[str] = []
        covered_codes: list[str] = []
        not_covered_codes: list[str] = []

        for cpt in cpt_codes:
            req = self._policy_engine.check_requirements(cpt, icd10_codes, payer_id)
            if req is not None:
                covered_codes.append(cpt)
                if req.requires_auth:
                    pa_required_codes.append(cpt)
            else:
                not_covered_codes.append(cpt)

        is_eligible = len(covered_codes) > 0 or len(cpt_codes) == 0
        recommendations: list[str] = []

        if pa_required_codes:
            recommendations.append(f"Prior auth required for: {', '.join(pa_required_codes)}")
        if not_covered_codes:
            recommendations.append(f"Coverage unclear for: {', '.join(not_covered_codes)}")

        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=True,
            output_data={
                "is_eligible": is_eligible,
                "payer_id": payer_id,
                "payer_name": policy.payer_name,
                "covered_codes": covered_codes,
                "pa_required_codes": pa_required_codes,
                "not_covered_codes": not_covered_codes,
            },
            recommendations=recommendations,
        )
