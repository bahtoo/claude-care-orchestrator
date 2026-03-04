"""
Appeal Letter Generator — creates appeal letters for denied prior authorizations.

Uses Claude to draft structured appeal letters with:
  - Clinical justification from the medical record
  - Payer policy citations
  - Supporting literature references
  - Template system for different appeal types
"""

from __future__ import annotations

import re

from anthropic import Anthropic, APIConnectionError, APIStatusError

from care_orchestrator.config import settings
from care_orchestrator.logging_config import logger
from care_orchestrator.models import (
    AppealLetter,
    AppealType,
    NecessityDecision,
)


class AppealGenerator:
    """Generates appeal letters for denied prior authorizations."""

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

    def generate(
        self,
        denial_reason: str,
        procedure_code: str,
        diagnosis_codes: list[str],
        clinical_text: str,
        necessity_decision: NecessityDecision,
        payer_name: str = "Unknown Payer",
        appeal_type: AppealType = AppealType.INITIAL,
    ) -> AppealLetter:
        """
        Generate an appeal letter for a denied prior authorization.

        Args:
            denial_reason: The payer's stated reason for denial.
            procedure_code: CPT code of the denied procedure.
            diagnosis_codes: Supporting ICD-10 codes.
            clinical_text: PHI-redacted clinical documentation.
            necessity_decision: The medical necessity evaluation result.
            payer_name: Name of the denying payer.
            appeal_type: Type of appeal to generate.

        Returns:
            AppealLetter with formatted content and justification.
        """
        logger.info(
            f"Generating {appeal_type.value} for CPT {procedure_code} "
            f"(denial: {denial_reason})"
        )

        llm_response = self._draft_appeal(
            denial_reason=denial_reason,
            procedure_code=procedure_code,
            diagnosis_codes=diagnosis_codes,
            clinical_text=clinical_text,
            necessity_decision=necessity_decision,
            payer_name=payer_name,
            appeal_type=appeal_type,
        )

        letter = self._parse_appeal(
            llm_response=llm_response,
            denial_reason=denial_reason,
            procedure_code=procedure_code,
            appeal_type=appeal_type,
        )

        logger.info(f"Appeal letter generated: {len(letter.letter_content)} chars")
        return letter

    def _draft_appeal(
        self,
        denial_reason: str,
        procedure_code: str,
        diagnosis_codes: list[str],
        clinical_text: str,
        necessity_decision: NecessityDecision,
        payer_name: str,
        appeal_type: AppealType,
    ) -> str:
        """Draft the appeal letter using Claude."""
        dx_list = ", ".join(diagnosis_codes) or "None"
        met_criteria = ", ".join(necessity_decision.criteria_met) or "None documented"
        unmet_criteria = ", ".join(necessity_decision.criteria_unmet) or "None"

        appeal_type_instructions = {
            AppealType.INITIAL: (
                "Write a formal first-level appeal letter. Be thorough and "
                "reference specific clinical findings from the documentation."
            ),
            AppealType.PEER_TO_PEER: (
                "Write talking points for a peer-to-peer review call. "
                "Be concise and focus on the strongest clinical arguments."
            ),
            AppealType.EXTERNAL: (
                "Write a formal external review appeal. Include references "
                "to clinical guidelines and standard of care."
            ),
        }

        prompt = f"""
<system>
You are a Healthcare Appeals Specialist for the claude-care-orchestrator.
You draft appeal letters for denied prior authorizations. You are performing
an ADMINISTRATIVE function — you do NOT provide clinical diagnoses or
treatment recommendations. You structure clinical evidence to support
the administrative appeal.
</system>

<context>
Payer: {payer_name}
Denied Procedure: CPT {procedure_code}
Denial Reason: {denial_reason}
Patient Diagnoses: {dx_list}
Criteria Met: {met_criteria}
Criteria Unmet: {unmet_criteria}
Appeal Type: {appeal_type.value}
</context>

<clinical_documentation>
{clinical_text}
</clinical_documentation>

<instructions>
{appeal_type_instructions.get(appeal_type, appeal_type_instructions[AppealType.INITIAL])}
</instructions>

Respond STRICTLY in this XML format:
<appeal>
    <letter>
    Write the full appeal letter in markdown format here.
    Include: date placeholder, provider/payer addresses, subject line,
    clinical arguments, policy references, and requested action.
    </letter>
    <justification>
    Key clinical arguments (1-3 sentences).
    </justification>
    <policy_citations>
    Comma-separated list of relevant policy sections or guidelines, or NONE.
    </policy_citations>
</appeal>
"""

        try:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=settings.max_tokens,
                messages=[{"role": "user", "content": prompt}],
            )
            return response.content[0].text
        except (APIConnectionError, APIStatusError):
            logger.error("Appeal letter generation failed")
            raise

    def _parse_appeal(
        self,
        llm_response: str,
        denial_reason: str,
        procedure_code: str,
        appeal_type: AppealType,
    ) -> AppealLetter:
        """Parse the LLM response into an AppealLetter."""
        letter_content = ""
        justification = ""
        policy_citations: list[str] = []

        # Parse letter content
        letter_match = re.search(
            r"<letter>(.*?)</letter>", llm_response, re.DOTALL
        )
        if letter_match:
            letter_content = letter_match.group(1).strip()

        # Parse justification
        just_match = re.search(
            r"<justification>(.*?)</justification>", llm_response, re.DOTALL
        )
        if just_match:
            justification = just_match.group(1).strip()

        # Parse policy citations
        cite_match = re.search(
            r"<policy_citations>(.*?)</policy_citations>", llm_response, re.DOTALL
        )
        if cite_match:
            raw = cite_match.group(1).strip()
            if raw.upper() != "NONE" and raw:
                policy_citations = [c.strip() for c in raw.split(",") if c.strip()]

        # Fallback if parsing fails
        if not letter_content:
            letter_content = llm_response

        return AppealLetter(
            appeal_type=appeal_type,
            letter_content=letter_content,
            clinical_justification=justification or "See attached documentation.",
            policy_citations=policy_citations,
            denial_reason=denial_reason,
            procedure_code=procedure_code,
        )
