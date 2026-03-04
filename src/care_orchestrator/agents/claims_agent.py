"""
Claims Agent — assembles and validates healthcare claims.

Generates CMS-1500 claim data from the pipeline context,
validates claim structure, and routes denials to the appeal generator.
"""

from __future__ import annotations

from care_orchestrator.agents import BaseAgent
from care_orchestrator.models import (
    AgentResult,
    AgentTask,
    ClaimData,
    ClaimLine,
    RCMStage,
)

# Simplified charge schedule (real systems use fee schedules)
CHARGE_SCHEDULE: dict[str, float] = {
    "99213": 150.00,
    "99214": 225.00,
    "99215": 350.00,
    "73221": 1200.00,
    "72148": 1400.00,
    "27447": 45000.00,
}


class ClaimsAgent(BaseAgent):
    """Assembles and validates CMS-1500 claims."""

    def __init__(self) -> None:
        super().__init__(name="claims_agent", stage=RCMStage.CLAIMS)

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == RCMStage.CLAIMS

    def _execute(self, task: AgentTask) -> AgentResult:
        payer_id = task.context.get("payer_id", "")
        cpt_codes = task.context.get("cpt_codes", [])
        icd10_codes = task.context.get("icd10_codes", [])
        pa_status = task.context.get("pa_status", "")
        pa_number = task.context.get("pa_number", "")
        is_eligible = task.context.get("is_eligible", False)

        # Validate pre-conditions
        errors: list[str] = []
        recommendations: list[str] = []

        if not is_eligible:
            errors.append("Patient not eligible — cannot submit claim")

        if pa_status == "denied":
            errors.append("Prior auth denied — claim will likely be rejected")
            recommendations.append("Generate appeal letter before claim submission")

        if pa_status == "pending_additional_info":
            errors.append("Prior auth pending — await approval before claiming")

        # Build claim lines
        claim_lines: list[ClaimLine] = []
        for cpt in cpt_codes:
            charge = CHARGE_SCHEDULE.get(cpt, 100.00)
            line = ClaimLine(
                cpt_code=cpt,
                icd10_codes=icd10_codes,
                units=1,
                charge_amount=charge,
            )
            claim_lines.append(line)

        total_charges = sum(line.charge_amount for line in claim_lines)

        # Validate claim
        validation_errors: list[str] = []
        if not cpt_codes:
            validation_errors.append("No CPT codes on claim")
        if not icd10_codes:
            validation_errors.append("No ICD-10 codes on claim")
        if not payer_id:
            validation_errors.append("No payer specified")

        is_valid = len(validation_errors) == 0 and len(errors) == 0

        claim = ClaimData(
            claim_type="professional",
            payer_id=payer_id,
            lines=claim_lines,
            total_charges=total_charges,
            authorization_number=pa_number,
            is_valid=is_valid,
            validation_errors=validation_errors,
        )

        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=is_valid,
            output_data={
                "claim": claim.model_dump(),
                "total_charges": total_charges,
                "line_count": len(claim_lines),
                "is_valid": is_valid,
            },
            errors=errors + validation_errors,
            recommendations=recommendations,
        )
