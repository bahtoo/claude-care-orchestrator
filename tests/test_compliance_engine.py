"""
Tests for the compliance engine (two-pass audit).

Uses mocked Anthropic client to test without API calls.
"""


import pytest

from care_orchestrator.compliance_engine import ComplianceEngine
from care_orchestrator.models import ClinicalNote

# ---------------------------------------------------------------------------
# Engine Initialization
# ---------------------------------------------------------------------------


class TestEngineInit:
    """Tests for engine initialization and configuration."""

    def test_engine_requires_api_key(self):
        """Engine should raise ValueError if no API key is available."""
        engine = ComplianceEngine(api_key="")
        with pytest.raises(ValueError, match="ANTHROPIC_API_KEY"):
            _ = engine.client

    def test_engine_with_explicit_key(self):
        """Engine should accept an explicit API key."""
        engine = ComplianceEngine(api_key="test-key-123")
        assert engine._api_key == "test-key-123"

    def test_engine_with_custom_model(self):
        """Engine should accept a custom model name."""
        engine = ComplianceEngine(api_key="test", model="claude-3-opus-20240229")
        assert engine._model == "claude-3-opus-20240229"


# ---------------------------------------------------------------------------
# Two-Pass Audit Flow
# ---------------------------------------------------------------------------


class TestAuditFlow:
    """Tests for the full two-pass audit flow."""

    def test_audit_detects_phi_in_pass1(self, phi_note, mock_anthropic_client):
        """Pass 1 (regex) should detect PHI before LLM is called."""
        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        report = engine.audit_text(phi_note)

        assert report.phi_status == "REDACTED"
        assert report.phi_detection.entity_count >= 4
        assert "[REDACTED_SSN]" in report.redacted_text
        assert "[REDACTED_PHONE]" in report.redacted_text
        assert "[REDACTED_EMAIL]" in report.redacted_text

    def test_audit_clean_text(self, clean_note, mock_anthropic_client):
        """Clean text should pass through with CLEAN status."""
        # Override mock to return CLEAN status
        mock_anthropic_client.messages.create.return_value.content[0].text = """
<audit_report>
    <phi_status>CLEAN</phi_status>
    <missed_phi_count>0</missed_phi_count>
    <admin_metadata>
        <cpt_codes>NONE</cpt_codes>
        <icd10_codes>NONE</icd10_codes>
        <workflow_type>general</workflow_type>
    </admin_metadata>
</audit_report>
"""

        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        report = engine.audit_text(clean_note)

        assert report.phi_status == "CLEAN"
        assert report.phi_detection.is_clean

    def test_audit_extracts_cpt_codes(self, phi_note, mock_anthropic_client):
        """Audit should extract CPT codes from LLM response."""
        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        report = engine.audit_text(phi_note)

        assert "73221" in report.admin_metadata.cpt_codes

    def test_audit_extracts_icd10_codes(self, phi_note, mock_anthropic_client):
        """Audit should extract ICD-10 codes from LLM response."""
        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        report = engine.audit_text(phi_note)

        assert "M23.5" in report.admin_metadata.icd10_codes

    def test_audit_detects_workflow_type(self, phi_note, mock_anthropic_client):
        """Audit should classify workflow type from LLM response."""
        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        report = engine.audit_text(phi_note)

        assert report.admin_metadata.workflow_type == "prior_auth"

    def test_audit_with_clinical_note_model(self, mock_anthropic_client):
        """Audit should work with a ClinicalNote model input."""
        engine = ComplianceEngine(api_key="test-key")
        engine._client = mock_anthropic_client

        note = ClinicalNote(
            text="Patient SSN 123-45-6789 needs CPT 99213",
            source="epic",
            note_type="progress",
        )

        report = engine.audit(note)

        assert report.phi_status == "REDACTED"
        assert report.phi_detection.entity_count >= 1


# ---------------------------------------------------------------------------
# Admin Metadata Parsing
# ---------------------------------------------------------------------------


class TestMetadataParsing:
    """Tests for LLM response parsing."""

    def test_parse_multiple_codes(self):
        """Parser should handle comma-separated code lists."""
        engine = ComplianceEngine(api_key="test-key")

        llm_response = """
<audit_report>
    <admin_metadata>
        <cpt_codes>99214, 72148</cpt_codes>
        <icd10_codes>E11.9, I10, M54.5</icd10_codes>
        <workflow_type>coding</workflow_type>
    </admin_metadata>
</audit_report>
"""
        metadata = engine._parse_admin_metadata(llm_response)

        assert metadata.cpt_codes == ["99214", "72148"]
        assert metadata.icd10_codes == ["E11.9", "I10", "M54.5"]
        assert metadata.workflow_type == "coding"

    def test_parse_none_codes(self):
        """Parser should handle NONE as empty list."""
        engine = ComplianceEngine(api_key="test-key")

        llm_response = """
<audit_report>
    <admin_metadata>
        <cpt_codes>NONE</cpt_codes>
        <icd10_codes>NONE</icd10_codes>
        <workflow_type>general</workflow_type>
    </admin_metadata>
</audit_report>
"""
        metadata = engine._parse_admin_metadata(llm_response)

        assert metadata.cpt_codes == []
        assert metadata.icd10_codes == []

    def test_parse_malformed_response(self):
        """Parser should gracefully handle malformed LLM responses."""
        engine = ComplianceEngine(api_key="test-key")

        metadata = engine._parse_admin_metadata("This is not XML at all")

        assert metadata.cpt_codes == []
        assert metadata.icd10_codes == []
        assert metadata.workflow_type == "general"
