"""
Compliance Triage Engine — two-pass PHI audit and admin workflow extraction.

Architecture:
  Pass 1 (Deterministic): Regex-based PHI detection via phi_detector.py
  Pass 2 (LLM):           Claude audits for contextual PHI + extracts CPT/ICD-10 codes

This dual-pass approach ensures:
  - Deterministic safety (regex catches obvious PHI regardless of LLM behavior)
  - Contextual intelligence (LLM catches nuanced PHI like names in context)
  - Administrative metadata extraction (CPT/ICD-10 codes, workflow classification)
"""

import re

from anthropic import Anthropic, APIConnectionError, APIStatusError

from care_orchestrator.config import settings
from care_orchestrator.logging_config import logger
from care_orchestrator.models import AdminMetadata, AuditReport, ClinicalNote
from care_orchestrator.phi_detector import phi_detector


class ComplianceEngine:
    """Two-pass compliance triage engine for healthcare administrative workflows."""

    def __init__(self, api_key: str | None = None, model: str | None = None) -> None:
        """
        Initialize the compliance engine.

        Args:
            api_key: Anthropic API key. Falls back to settings if not provided.
            model: Model name to use. Falls back to settings if not provided.
        """
        self._api_key = api_key or settings.anthropic_api_key
        self._model = model or settings.model_name
        self._client: Anthropic | None = None

    @property
    def client(self) -> Anthropic:
        """Lazy-initialize the Anthropic client."""
        if self._client is None:
            if not self._api_key:
                msg = (
                    "ANTHROPIC_API_KEY is not set. "
                    "Set it in .env or pass it to ComplianceEngine(api_key=...)"
                )
                raise ValueError(msg)
            self._client = Anthropic(api_key=self._api_key)
        return self._client

    def audit(self, note: ClinicalNote) -> AuditReport:
        """
        Run the full two-pass compliance audit on a clinical note.

        Pass 1: Deterministic regex PHI scan
        Pass 2: LLM-powered contextual audit + metadata extraction

        Args:
            note: The clinical note to audit.

        Returns:
            Complete AuditReport with PHI status, redacted text, and admin metadata.

        Raises:
            ValueError: If API key is missing.
            APIConnectionError: If cannot connect to Anthropic API.
            APIStatusError: If API returns an error status.
        """
        logger.info(f"Starting compliance audit (source: {note.source}, type: {note.note_type})")

        # ── Pass 1: Deterministic PHI Detection ───────────────────────────
        phi_result = phi_detector.detect(note.text)
        logger.info(
            f"Pass 1 complete: {'CLEAN' if phi_result.is_clean else 'PHI DETECTED'} "
            f"({phi_result.entity_count} entities)"
        )

        # ── Pass 2: LLM Audit ────────────────────────────────────────────
        llm_response = self._llm_audit(phi_result.redacted_text)

        # ── Parse LLM response for admin metadata ────────────────────────
        admin_metadata = self._parse_admin_metadata(llm_response)

        # ── Build final report ────────────────────────────────────────────
        phi_status = "CLEAN" if phi_result.is_clean else "REDACTED"

        report = AuditReport(
            phi_status=phi_status,
            phi_detection=phi_result,
            redacted_text=phi_result.redacted_text,
            admin_metadata=admin_metadata,
            raw_llm_response=llm_response,
        )

        logger.info(
            f"Audit complete: status={phi_status}, "
            f"CPT codes={admin_metadata.cpt_codes}, "
            f"ICD-10 codes={admin_metadata.icd10_codes}, "
            f"workflow={admin_metadata.workflow_type}"
        )

        return report

    def audit_text(self, text: str) -> AuditReport:
        """
        Convenience method: audit raw text without creating a ClinicalNote first.

        Args:
            text: Raw clinical text to audit.

        Returns:
            Complete AuditReport.
        """
        note = ClinicalNote(text=text)
        return self.audit(note)

    def _llm_audit(self, pre_redacted_text: str) -> str:
        """
        Run the LLM audit pass on (already regex-redacted) text.

        Args:
            pre_redacted_text: Text after deterministic PHI redaction.

        Returns:
            Raw LLM response string.
        """
        audit_prompt = f"""
<system>
You are the Regulatory Readiness Agent for the claude-care-orchestrator.
Your task is to audit clinical text for any remaining PII/PHI that may have
been missed by the first-pass redaction, and extract administrative metadata.
</system>

<task>
1. Check for any remaining PHI (names, locations, identifiers) not yet redacted.
2. If found, note what was missed but do NOT include the actual PHI in your response.
3. Extract CPT (Procedure) and ICD-10 (Diagnosis) codes if present.
4. Classify the workflow type: prior_auth, appeal, coding, or general.
5. Format the output strictly as shown below.
</task>

<input_data>
{pre_redacted_text}
</input_data>

Respond strictly in the following XML format:
<audit_report>
    <phi_status>CLEAN or REDACTED</phi_status>
    <missed_phi_count>0</missed_phi_count>
    <admin_metadata>
        <cpt_codes>comma-separated list or NONE</cpt_codes>
        <icd10_codes>comma-separated list or NONE</icd10_codes>
        <workflow_type>prior_auth|appeal|coding|general</workflow_type>
    </admin_metadata>
</audit_report>
"""

        try:
            response = self.client.messages.create(
                model=self._model,
                max_tokens=settings.max_tokens,
                messages=[{"role": "user", "content": audit_prompt}],
            )
            result = response.content[0].text
            logger.info("LLM audit pass completed successfully")
            return result

        except APIConnectionError:
            logger.error("Failed to connect to Anthropic API")
            raise
        except APIStatusError as e:
            logger.error(f"Anthropic API error: {e.status_code} - {e.message}")
            raise

    def _parse_admin_metadata(self, llm_response: str) -> AdminMetadata:
        """
        Parse administrative metadata from the LLM response XML.

        Args:
            llm_response: Raw XML response from the LLM audit.

        Returns:
            Parsed AdminMetadata.
        """
        cpt_codes: list[str] = []
        icd10_codes: list[str] = []
        workflow_type = "general"

        # Extract CPT codes
        cpt_match = re.search(r"<cpt_codes>(.*?)</cpt_codes>", llm_response, re.DOTALL)
        if cpt_match:
            raw = cpt_match.group(1).strip()
            if raw and raw.upper() != "NONE":
                cpt_codes = [code.strip() for code in raw.split(",") if code.strip()]

        # Extract ICD-10 codes
        icd_match = re.search(r"<icd10_codes>(.*?)</icd10_codes>", llm_response, re.DOTALL)
        if icd_match:
            raw = icd_match.group(1).strip()
            if raw and raw.upper() != "NONE":
                icd10_codes = [code.strip() for code in raw.split(",") if code.strip()]

        # Extract workflow type
        wf_match = re.search(r"<workflow_type>(.*?)</workflow_type>", llm_response, re.DOTALL)
        if wf_match:
            workflow_type = wf_match.group(1).strip().lower()

        return AdminMetadata(
            cpt_codes=cpt_codes,
            icd10_codes=icd10_codes,
            workflow_type=workflow_type,
        )


# ---------------------------------------------------------------------------
# CLI entry point
# ---------------------------------------------------------------------------

if __name__ == "__main__":
    sample_input = """
    Patient John Doe (DOB 05/12/1980) visited for a follow-up.
    He requires a Knee MRI (CPT 73221) due to chronic ACL pain (ICD-10 M23.5).
    Contact: john.doe@email.com, Phone: (555) 123-4567
    SSN: 123-45-6789
    """

    print("━" * 60)
    print("  COMPLIANCE TRIAGE ENGINE — Two-Pass Audit")
    print("━" * 60)

    engine = ComplianceEngine()
    report = engine.audit_text(sample_input)

    print(f"\n📋 PHI Status: {report.phi_status}")
    print(f"🔍 Entities Found: {report.phi_detection.entity_count}")
    for entity in report.phi_detection.entities:
        print(f"   • {entity.phi_type.value}: '{entity.value}'")
    print(f"\n📝 Redacted Text:\n{report.redacted_text}")
    print(f"\n📊 CPT Codes: {report.admin_metadata.cpt_codes}")
    print(f"📊 ICD-10 Codes: {report.admin_metadata.icd10_codes}")
    print(f"📊 Workflow Type: {report.admin_metadata.workflow_type}")
    print("━" * 60)
