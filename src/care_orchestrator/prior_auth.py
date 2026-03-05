"""
Prior Authorization Generator — end-to-end PA workflow orchestrator.

Ties together all Phase 1 and Phase 2 modules:
  1. Compliance audit (PHI redaction + code extraction)
  2. Policy lookup (check if PA is required)
  3. Medical necessity evaluation (does the clinical doc support it?)
  4. FHIR resource generation
  5. PA request document assembly

This is the "Payer-Provider Bridge" — the core value proposition.
"""

from __future__ import annotations

import time

from care_orchestrator.compliance_engine import ComplianceEngine
from care_orchestrator.fhir_mapper import fhir_mapper
from care_orchestrator.logging_config import logger
from care_orchestrator.medical_necessity import MedicalNecessityEvaluator
from care_orchestrator.models import (
    ClinicalNote,
    CoverageCriteria,
    NecessityDecision,
    NecessityDetermination,
    PriorAuthRequest,
    PriorAuthResult,
    PriorAuthStatus,
)
from care_orchestrator.policy_engine import PolicyEngine


class PriorAuthGenerator:
    """End-to-end Prior Authorization workflow orchestrator."""

    def __init__(
        self,
        api_key: str | None = None,
        model: str | None = None,
        policies_dir: str = "config/policies",
    ) -> None:
        self._compliance = ComplianceEngine(api_key=api_key, model=model)
        self._policy = PolicyEngine(policies_dir=policies_dir)
        self._necessity = MedicalNecessityEvaluator(api_key=api_key, model=model)

    @property
    def available_payers(self) -> list[str]:
        """Available payer IDs from loaded policies."""
        return self._policy.available_payers

    def submit(
        self,
        clinical_text: str,
        payer_id: str,
        source: str = "unknown",
    ) -> PriorAuthResult:
        """
        Run the full prior authorization workflow.

        Args:
            clinical_text: Raw clinical note text.
            payer_id: Target payer identifier.
            source: Source EHR system.

        Returns:
            PriorAuthResult with status, generated request, and timeline.
        """
        start_time = time.monotonic()
        logger.info(f"Starting PA workflow: payer={payer_id}, source={source}")

        # ── Step 1: Compliance Audit ──────────────────────────────────────
        note = ClinicalNote(text=clinical_text, source=source)
        audit_report = self._compliance.audit(note)

        cpt_codes = audit_report.admin_metadata.cpt_codes
        icd10_codes = audit_report.admin_metadata.icd10_codes

        if not cpt_codes:
            elapsed = (time.monotonic() - start_time) / 60
            return PriorAuthResult(
                status=PriorAuthStatus.NOT_REQUIRED,
                turnaround_estimate_minutes=elapsed,
                audit_report=audit_report,
                summary="No CPT procedure codes found in the clinical note.",
            )

        primary_cpt = cpt_codes[0]

        # ── Step 2: Policy Lookup ─────────────────────────────────────────
        requirement = self._policy.check_requirements(primary_cpt, icd10_codes, payer_id)

        if requirement is None:
            elapsed = (time.monotonic() - start_time) / 60
            return PriorAuthResult(
                status=PriorAuthStatus.NOT_REQUIRED,
                turnaround_estimate_minutes=elapsed,
                audit_report=audit_report,
                summary=f"Payer '{payer_id}' not found in policy database.",
            )

        if not requirement.requires_auth:
            elapsed = (time.monotonic() - start_time) / 60
            return PriorAuthResult(
                status=PriorAuthStatus.NOT_REQUIRED,
                turnaround_estimate_minutes=elapsed,
                audit_report=audit_report,
                summary=(
                    f"CPT {primary_cpt} does not require prior authorization "
                    f"with payer '{payer_id}'."
                ),
            )

        # ── Step 2b: Check Auto-Approve ───────────────────────────────────
        if self._policy.check_auto_approve(primary_cpt, icd10_codes, payer_id):
            fhir_output = fhir_mapper.map(
                admin_metadata=audit_report.admin_metadata,
                redacted_text=audit_report.redacted_text,
            )
            decision = NecessityDecision(
                determination=NecessityDetermination.APPROVED,
                rationale="Auto-approved: diagnosis qualifies for automatic approval.",
                criteria_met=["Auto-approve diagnosis match"],
                confidence_score=1.0,
            )
            request = PriorAuthRequest(
                payer_id=payer_id,
                procedure_code=primary_cpt,
                diagnosis_codes=icd10_codes,
                clinical_summary=audit_report.redacted_text,
                necessity_decision=decision,
                fhir_resources=fhir_output,
            )
            elapsed = (time.monotonic() - start_time) / 60
            return PriorAuthResult(
                status=PriorAuthStatus.APPROVED,
                request=request,
                turnaround_estimate_minutes=elapsed,
                audit_report=audit_report,
                summary=(
                    f"AUTO-APPROVED: CPT {primary_cpt} with qualifying diagnosis. "
                    f"Processed in {elapsed:.1f} minutes."
                ),
            )

        # ── Step 3: Medical Necessity Evaluation ──────────────────────────
        criteria = requirement.criteria or CoverageCriteria()
        policy = self._policy.get_policy(payer_id)
        payer_name = policy.payer_name if policy else payer_id

        decision = self._necessity.evaluate(
            clinical_text=audit_report.redacted_text,
            procedure_code=primary_cpt,
            diagnosis_codes=icd10_codes,
            criteria=criteria,
            payer_name=payer_name,
        )

        # ── Step 4: FHIR Resources ───────────────────────────────────────
        fhir_output = fhir_mapper.map(
            admin_metadata=audit_report.admin_metadata,
            redacted_text=audit_report.redacted_text,
        )

        # ── Step 5: Assemble Result ───────────────────────────────────────
        request = PriorAuthRequest(
            payer_id=payer_id,
            procedure_code=primary_cpt,
            diagnosis_codes=icd10_codes,
            clinical_summary=audit_report.redacted_text,
            necessity_decision=decision,
            fhir_resources=fhir_output,
        )

        # Map necessity determination to PA status
        status_map = {
            NecessityDetermination.APPROVED: PriorAuthStatus.APPROVED,
            NecessityDetermination.DENIED: PriorAuthStatus.DENIED,
            NecessityDetermination.NEEDS_INFO: PriorAuthStatus.PENDING_INFO,
        }
        pa_status = status_map.get(decision.determination) or PriorAuthStatus.SUBMITTED

        elapsed = (time.monotonic() - start_time) / 60

        summary_lines = [
            f"PA for CPT {primary_cpt} with {payer_name}: {pa_status.value}.",
            f"Medical necessity: {decision.determination.value} "
            f"(confidence: {decision.confidence_score:.0%}).",
        ]
        if decision.criteria_unmet:
            summary_lines.append(f"Unmet criteria: {', '.join(decision.criteria_unmet)}.")
        if decision.missing_documentation:
            summary_lines.append(f"Missing docs: {', '.join(decision.missing_documentation)}.")
        summary_lines.append(f"Processed in {elapsed:.1f} minutes.")

        result = PriorAuthResult(
            status=pa_status,
            request=request,
            turnaround_estimate_minutes=elapsed,
            audit_report=audit_report,
            summary=" ".join(summary_lines),
        )

        logger.info(f"PA workflow complete: {pa_status.value} in {elapsed:.1f}m")
        return result
