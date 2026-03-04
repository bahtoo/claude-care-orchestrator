"""
Tests for the Prior Auth Generator — end-to-end PA workflow.

All LLM calls and API dependencies are mocked.
Tests cover PA-required, PA-not-required, auto-approve, and missing-payer paths.
"""

from unittest.mock import patch

import pytest

from care_orchestrator.models import (
    AdminMetadata,
    AuditReport,
    NecessityDecision,
    NecessityDetermination,
    PHIDetectionResult,
    PriorAuthStatus,
)
from care_orchestrator.prior_auth import PriorAuthGenerator

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def mock_audit_report():
    """An audit report with MRI CPT + knee diagnosis."""
    return AuditReport(
        phi_status="REDACTED",
        phi_detection=PHIDetectionResult(
            is_clean=False, redacted_text="redacted text", entity_count=1
        ),
        redacted_text="Patient presents with knee instability...",
        admin_metadata=AdminMetadata(
            cpt_codes=["73221"],
            icd10_codes=["M23.5"],
            workflow_type="prior_auth",
        ),
    )


@pytest.fixture
def mock_audit_report_no_cpt():
    """An audit report with no CPT codes."""
    return AuditReport(
        phi_status="CLEAN",
        phi_detection=PHIDetectionResult(
            is_clean=True, redacted_text="clean text", entity_count=0
        ),
        redacted_text="General wellness visit.",
        admin_metadata=AdminMetadata(
            cpt_codes=[],
            icd10_codes=["Z00.00"],
            workflow_type="coding",
        ),
    )


@pytest.fixture
def mock_audit_report_office_visit():
    """An audit report with an office visit (no PA needed)."""
    return AuditReport(
        phi_status="CLEAN",
        phi_detection=PHIDetectionResult(
            is_clean=True, redacted_text="clean text", entity_count=0
        ),
        redacted_text="Routine office visit.",
        admin_metadata=AdminMetadata(
            cpt_codes=["99213"],
            icd10_codes=["E11.9"],
            workflow_type="coding",
        ),
    )


@pytest.fixture
def mock_audit_report_auto_approve():
    """An audit report with auto-approve qualifying diagnosis."""
    return AuditReport(
        phi_status="REDACTED",
        phi_detection=PHIDetectionResult(
            is_clean=False, redacted_text="redacted text", entity_count=1
        ),
        redacted_text="Acute knee injury...",
        admin_metadata=AdminMetadata(
            cpt_codes=["73221"],
            icd10_codes=["S83.5"],
            workflow_type="prior_auth",
        ),
    )


@pytest.fixture
def mock_necessity_approved():
    return NecessityDecision(
        determination=NecessityDetermination.APPROVED,
        rationale="Clinical documentation supports necessity.",
        criteria_met=["Clinical exam findings", "Failed initial treatment"],
        confidence_score=0.9,
    )


@pytest.fixture
def pa_generator():
    return PriorAuthGenerator(
        api_key="test-key",
        model="test-model",
        policies_dir="config/policies",
    )


# ---------------------------------------------------------------------------
# Workflow Tests
# ---------------------------------------------------------------------------


class TestPANotRequired:
    """Tests where prior authorization is NOT required."""

    def test_no_cpt_codes(self, pa_generator, mock_audit_report_no_cpt):
        with patch.object(
            pa_generator._compliance, "audit", return_value=mock_audit_report_no_cpt
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.NOT_REQUIRED
            assert "No CPT" in result.summary

    def test_office_visit_no_auth(self, pa_generator, mock_audit_report_office_visit):
        with patch.object(
            pa_generator._compliance, "audit", return_value=mock_audit_report_office_visit
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.NOT_REQUIRED

    def test_unknown_payer(self, pa_generator, mock_audit_report):
        with patch.object(
            pa_generator._compliance, "audit", return_value=mock_audit_report
        ):
            result = pa_generator.submit("text", "nonexistent_payer")
            assert result.status == PriorAuthStatus.NOT_REQUIRED
            assert "not found" in result.summary


class TestAutoApprove:
    """Tests for auto-approve path."""

    def test_auto_approve_with_qualifying_dx(self, pa_generator, mock_audit_report_auto_approve):
        with patch.object(
            pa_generator._compliance, "audit", return_value=mock_audit_report_auto_approve
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.APPROVED
            assert "AUTO-APPROVED" in result.summary
            assert result.request is not None
            assert result.request.necessity_decision.confidence_score == 1.0


class TestPARequired:
    """Tests for full PA workflow with necessity evaluation."""

    def test_approved_necessity(
        self, pa_generator, mock_audit_report, mock_necessity_approved
    ):
        with (
            patch.object(
                pa_generator._compliance, "audit", return_value=mock_audit_report
            ),
            patch.object(
                pa_generator._necessity, "evaluate", return_value=mock_necessity_approved
            ),
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.APPROVED
            assert result.request is not None
            assert result.request.procedure_code == "73221"

    def test_denied_necessity(self, pa_generator, mock_audit_report):
        denied = NecessityDecision(
            determination=NecessityDetermination.DENIED,
            rationale="Insufficient documentation.",
            criteria_unmet=["Failed initial treatment"],
            missing_documentation=["PT records"],
            confidence_score=0.8,
        )
        with (
            patch.object(
                pa_generator._compliance, "audit", return_value=mock_audit_report
            ),
            patch.object(pa_generator._necessity, "evaluate", return_value=denied),
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.DENIED
            assert "Unmet criteria" in result.summary

    def test_pending_info_necessity(self, pa_generator, mock_audit_report):
        needs = NecessityDecision(
            determination=NecessityDetermination.NEEDS_INFO,
            rationale="Need more documentation.",
            missing_documentation=["Treatment history"],
            confidence_score=0.5,
        )
        with (
            patch.object(
                pa_generator._compliance, "audit", return_value=mock_audit_report
            ),
            patch.object(pa_generator._necessity, "evaluate", return_value=needs),
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.status == PriorAuthStatus.PENDING_INFO

    def test_fhir_resources_generated(
        self, pa_generator, mock_audit_report, mock_necessity_approved
    ):
        with (
            patch.object(
                pa_generator._compliance, "audit", return_value=mock_audit_report
            ),
            patch.object(
                pa_generator._necessity, "evaluate", return_value=mock_necessity_approved
            ),
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.request is not None
            assert result.request.fhir_resources is not None
            assert result.request.fhir_resources.total_resources > 0

    def test_turnaround_time_tracked(
        self, pa_generator, mock_audit_report, mock_necessity_approved
    ):
        with (
            patch.object(
                pa_generator._compliance, "audit", return_value=mock_audit_report
            ),
            patch.object(
                pa_generator._necessity, "evaluate", return_value=mock_necessity_approved
            ),
        ):
            result = pa_generator.submit("text", "commercial_generic")
            assert result.turnaround_estimate_minutes >= 0

    def test_available_payers(self, pa_generator):
        assert "commercial_generic" in pa_generator.available_payers
