"""
Medical Necessity Evaluator — LLM-powered clinical documentation assessment.

Uses Claude's context window to evaluate whether clinical documentation
supports medical necessity based on payer-specific criteria.

This is the intelligence layer that replaces manual chart review.
"""

from __future__ import annotations

import re

from anthropic import Anthropic, APIConnectionError, APIStatusError

from care_orchestrator.config import settings
from care_orchestrator.logging_config import logger
from care_orchestrator.models import (
    CoverageCriteria,
    NecessityDecision,
    NecessityDetermination,
)


class MedicalNecessityEvaluator:
    """Evaluates medical necessity using payer criteria + LLM reasoning."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.model_name
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        """Lazy-initialize the Anthropic client."""
        if self._client is None:
            if not self._api_key:
                msg = "ANTHROPIC_API_KEY is not set."
                raise ValueError(msg)
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def evaluate(
        self,
        clinical_text: str,
        procedure_code: str,
        diagnosis_codes: list[str],
        criteria: CoverageCriteria,
        payer_name: str = "Unknown Payer",
    ) -> NecessityDecision:
        """
        Evaluate whether clinical documentation supports medical necessity.

        Args:
            clinical_text: PHI-redacted clinical note text.
            procedure_code: The CPT code being requested.
            diagnosis_codes: Supporting ICD-10 diagnosis codes.
            criteria: Payer-specific coverage criteria to evaluate against.
            payer_name: Name of the payer (for prompt context).

        Returns:
            NecessityDecision with determination, rationale, and gaps.
        """
        logger.info(
            f"Evaluating medical necessity: CPT {procedure_code} "
            f"for {payer_name} ({len(criteria.required_documentation)} criteria)"
        )

        llm_response = self._run_evaluation(
            clinical_text, procedure_code, diagnosis_codes, criteria, payer_name
        )

        decision = self._parse_decision(llm_response, criteria)

        logger.info(
            f"Necessity decision: {decision.determination.value} "
            f"(confidence: {decision.confidence_score:.2f})"
        )

        return decision

    def _run_evaluation(
        self,
        clinical_text: str,
        procedure_code: str,
        diagnosis_codes: list[str],
        criteria: CoverageCriteria,
        payer_name: str,
    ) -> str:
        """Run the LLM evaluation with dynamically constructed prompt."""
        criteria_list = "\n".join(
            f"  {i + 1}. {doc}" for i, doc in enumerate(criteria.required_documentation)
        )
        qualifying_dx = ", ".join(criteria.required_diagnoses) or "Any"
        patient_dx = ", ".join(diagnosis_codes) or "None provided"

        prompt = f"""
<system>
You are a Medical Necessity Reviewer for the claude-care-orchestrator.
You evaluate clinical documentation against payer-specific criteria to
determine if a procedure is medically necessary. You are NOT providing
clinical advice — you are performing an administrative documentation review.
</system>

<context>
Payer: {payer_name}
Procedure: CPT {procedure_code}
Patient Diagnoses: {patient_dx}
Qualifying Diagnoses (per payer policy): {qualifying_dx}
Age Restrictions: {criteria.age_restrictions}
</context>

<payer_criteria>
The payer requires ALL of the following documentation to approve:
{criteria_list}
</payer_criteria>

<clinical_documentation>
{clinical_text}
</clinical_documentation>

<task>
Evaluate the clinical documentation against each payer criterion.
For each criterion, determine if it is MET, UNMET, or PARTIALLY_MET.

Respond STRICTLY in this XML format:
<necessity_evaluation>
    <determination>APPROVED|DENIED|NEEDS_ADDITIONAL_INFO</determination>
    <confidence>0.0-1.0</confidence>
    <rationale>Brief explanation of the overall determination</rationale>
    <criteria_met>comma-separated list of met criteria, or NONE</criteria_met>
    <criteria_unmet>comma-separated list of unmet criteria, or NONE</criteria_unmet>
    <missing_docs>comma-separated list of missing documentation, or NONE</missing_docs>
</necessity_evaluation>
</task>
"""

        try:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=settings.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except (APIConnectionError, APIStatusError):
            logger.error("LLM evaluation failed")
            raise

    def _parse_decision(
        self, llm_response: str, criteria: CoverageCriteria
    ) -> NecessityDecision:
        """Parse the LLM response into a NecessityDecision."""
        # Default values
        determination = NecessityDetermination.NEEDS_INFO
        rationale = "Unable to parse evaluation response"
        confidence = 0.0
        criteria_met: list[str] = []
        criteria_unmet: list[str] = []
        missing_docs: list[str] = []

        # Parse determination
        det_match = re.search(
            r"<determination>(.*?)</determination>", llm_response, re.DOTALL
        )
        if det_match:
            raw_det = det_match.group(1).strip().upper()
            if raw_det == "APPROVED":
                determination = NecessityDetermination.APPROVED
            elif raw_det == "DENIED":
                determination = NecessityDetermination.DENIED
            else:
                determination = NecessityDetermination.NEEDS_INFO

        # Parse confidence
        conf_match = re.search(
            r"<confidence>(.*?)</confidence>", llm_response, re.DOTALL
        )
        if conf_match:
            try:
                confidence = float(conf_match.group(1).strip())
                confidence = max(0.0, min(1.0, confidence))
            except ValueError:
                confidence = 0.5

        # Parse rationale
        rat_match = re.search(
            r"<rationale>(.*?)</rationale>", llm_response, re.DOTALL
        )
        if rat_match:
            rationale = rat_match.group(1).strip()

        # Parse criteria met/unmet
        met_match = re.search(
            r"<criteria_met>(.*?)</criteria_met>", llm_response, re.DOTALL
        )
        if met_match:
            raw = met_match.group(1).strip()
            if raw.upper() != "NONE" and raw:
                criteria_met = [c.strip() for c in raw.split(",") if c.strip()]

        unmet_match = re.search(
            r"<criteria_unmet>(.*?)</criteria_unmet>", llm_response, re.DOTALL
        )
        if unmet_match:
            raw = unmet_match.group(1).strip()
            if raw.upper() != "NONE" and raw:
                criteria_unmet = [c.strip() for c in raw.split(",") if c.strip()]

        # Parse missing docs
        docs_match = re.search(
            r"<missing_docs>(.*?)</missing_docs>", llm_response, re.DOTALL
        )
        if docs_match:
            raw = docs_match.group(1).strip()
            if raw.upper() != "NONE" and raw:
                missing_docs = [d.strip() for d in raw.split(",") if d.strip()]

        return NecessityDecision(
            determination=determination,
            rationale=rationale,
            criteria_met=criteria_met,
            criteria_unmet=criteria_unmet,
            missing_documentation=missing_docs,
            confidence_score=confidence,
        )
