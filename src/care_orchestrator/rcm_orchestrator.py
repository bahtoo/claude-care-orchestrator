"""
RCM Pipeline Orchestrator — end-to-end Revenue Cycle Management.

Chains all agents: Coding → Eligibility → Prior Auth → Claims.
Supports partial workflows (start at any stage).
"""

from __future__ import annotations

import time

from care_orchestrator.agents.claims_agent import ClaimsAgent
from care_orchestrator.agents.coding_agent import CodingAgent
from care_orchestrator.agents.eligibility_agent import EligibilityAgent
from care_orchestrator.agents.prior_auth_agent import PriorAuthAgent
from care_orchestrator.agents.registry import AgentRegistry
from care_orchestrator.compliance_engine import ComplianceEngine
from care_orchestrator.logging_config import logger
from care_orchestrator.models import (
    AgentTask,
    ClinicalNote,
    RCMContext,
    RCMResult,
    RCMStage,
)


class RCMOrchestrator:
    """Orchestrates the full Revenue Cycle Management pipeline."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        policies_dir: str = "config/policies",
    ) -> None:
        self._compliance = ComplianceEngine(api_key=api_key, model=model)
        self._registry = AgentRegistry()

        # Register all agents
        self._registry.register(CodingAgent())
        self._registry.register(EligibilityAgent(policies_dir=policies_dir))
        self._registry.register(
            PriorAuthAgent(api_key=api_key, model=model, policies_dir=policies_dir)
        )
        self._registry.register(ClaimsAgent())

    def run(
        self,
        clinical_text: str,
        payer_id: str,
        stages: list[str] | None = None,
    ) -> RCMResult:
        """
        Run the RCM pipeline.

        Args:
            clinical_text: Raw clinical note text.
            payer_id: Target payer identifier.
            stages: Optional list of stages to run. Defaults to all.

        Returns:
            RCMResult with full audit trail.
        """
        start = time.monotonic()
        logger.info(f"Starting RCM pipeline: payer={payer_id}")

        if stages is None:
            stages = [
                RCMStage.CODING,
                RCMStage.ELIGIBILITY,
                RCMStage.PRIOR_AUTH,
                RCMStage.CLAIMS,
            ]

        # Step 0: Compliance audit to get codes and redacted text
        note = ClinicalNote(text=clinical_text)
        audit = self._compliance.audit(note)

        # Build initial context
        context = RCMContext(
            clinical_text=clinical_text,
            payer_id=payer_id,
            redacted_text=audit.redacted_text,
            cpt_codes=audit.admin_metadata.cpt_codes,
            icd10_codes=audit.admin_metadata.icd10_codes,
        )

        # Build initial task
        initial_task = AgentTask(
            task_type=stages[0],
            input_data={
                "clinical_text": clinical_text,
                "payer_id": payer_id,
            },
            context={
                "cpt_codes": context.cpt_codes,
                "icd10_codes": context.icd10_codes,
                "redacted_text": context.redacted_text,
                "payer_id": payer_id,
            },
        )

        # Run agent chain
        results = self._registry.run_chain(stages, initial_task)

        # Update context from results
        stages_completed = []
        for result in results:
            context.agent_results.append(result)
            stages_completed.append(result.stage)

            # Merge key outputs into context
            if result.stage == RCMStage.ELIGIBILITY:
                context.is_eligible = result.output_data.get("is_eligible", False)
            elif result.stage == RCMStage.PRIOR_AUTH:
                context.pa_status = result.output_data.get("pa_status", "")
                context.pa_number = result.output_data.get("pa_number", "")

        # Build summary
        elapsed = (time.monotonic() - start) / 60
        all_success = all(r.success for r in results)
        summary_parts = [
            f"RCM pipeline {'completed' if all_success else 'partial'}: "
            f"{len(stages_completed)}/{len(stages)} stages.",
        ]

        for result in results:
            status = "✓" if result.success else "✗"
            summary_parts.append(f"  {status} {result.stage}: {result.agent_name}")
            if result.errors:
                summary_parts.append(f"    Issues: {'; '.join(result.errors[:2])}")
            if result.recommendations:
                summary_parts.append(f"    Rec: {'; '.join(result.recommendations[:2])}")

        summary_parts.append(f"Processed in {elapsed:.1f} minutes.")

        rcm_result = RCMResult(
            success=all_success,
            stages_completed=stages_completed,
            context=context,
            summary="\n".join(summary_parts),
            turnaround_minutes=elapsed,
        )

        logger.info(f"RCM pipeline done: {len(stages_completed)} stages, success={all_success}")
        return rcm_result
