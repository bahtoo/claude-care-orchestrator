"""
Tests for the RCM Orchestrator — end-to-end pipeline.

All LLM calls are mocked. Tests cover full and partial pipelines.
"""

from unittest.mock import patch

import pytest

from care_orchestrator.models import (
    AdminMetadata,
    AuditReport,
    PHIDetectionResult,
    RCMStage,
)
from care_orchestrator.rcm_orchestrator import RCMOrchestrator


@pytest.fixture
def mock_audit():
    return AuditReport(
        phi_status="REDACTED",
        phi_detection=PHIDetectionResult(
            is_clean=False,
            redacted_text="Patient presents with knee pain...",
            entity_count=1,
        ),
        redacted_text="Patient presents with knee pain...",
        admin_metadata=AdminMetadata(
            cpt_codes=["73221"],
            icd10_codes=["M23.5"],
            workflow_type="prior_auth",
        ),
    )


@pytest.fixture
def mock_audit_office():
    return AuditReport(
        phi_status="CLEAN",
        phi_detection=PHIDetectionResult(
            is_clean=True,
            redacted_text="Routine visit.",
            entity_count=0,
        ),
        redacted_text="Routine visit.",
        admin_metadata=AdminMetadata(
            cpt_codes=["99213"],
            icd10_codes=["E11.9"],
            workflow_type="coding",
        ),
    )


@pytest.fixture
def orchestrator():
    return RCMOrchestrator(
        api_key="test-key",
        model="test-model",
        policies_dir="config/policies",
    )


class TestFullPipeline:
    """Tests for the full RCM pipeline."""

    def test_all_stages_run(self, orchestrator, mock_audit):
        with patch.object(orchestrator._compliance, "audit", return_value=mock_audit):
            # Mock PA generator to avoid LLM calls
            with patch.object(
                orchestrator._registry.get_for_stage("prior_auth")._pa_generator,
                "submit",
            ) as mock_pa:
                from care_orchestrator.models import PriorAuthResult, PriorAuthStatus

                mock_pa.return_value = PriorAuthResult(
                    status=PriorAuthStatus.NOT_REQUIRED,
                    summary="Not required",
                )
                result = orchestrator.run("text", "commercial_generic")

        assert len(result.stages_completed) == 4
        assert result.stages_completed[0] == RCMStage.CODING

    def test_result_has_summary(self, orchestrator, mock_audit):
        with patch.object(orchestrator._compliance, "audit", return_value=mock_audit):
            with patch.object(
                orchestrator._registry.get_for_stage("prior_auth")._pa_generator,
                "submit",
            ) as mock_pa:
                from care_orchestrator.models import PriorAuthResult, PriorAuthStatus

                mock_pa.return_value = PriorAuthResult(
                    status=PriorAuthStatus.NOT_REQUIRED,
                    summary="Not required",
                )
                result = orchestrator.run("text", "commercial_generic")

        assert len(result.summary) > 0
        assert "pipeline" in result.summary.lower()

    def test_turnaround_tracked(self, orchestrator, mock_audit):
        with patch.object(orchestrator._compliance, "audit", return_value=mock_audit):
            with patch.object(
                orchestrator._registry.get_for_stage("prior_auth")._pa_generator,
                "submit",
            ) as mock_pa:
                from care_orchestrator.models import PriorAuthResult, PriorAuthStatus

                mock_pa.return_value = PriorAuthResult(
                    status=PriorAuthStatus.NOT_REQUIRED,
                    summary="Not required",
                )
                result = orchestrator.run("text", "commercial_generic")

        assert result.turnaround_minutes >= 0


class TestPartialPipeline:
    """Tests for running subset of stages."""

    def test_coding_only(self, orchestrator, mock_audit):
        with patch.object(orchestrator._compliance, "audit", return_value=mock_audit):
            result = orchestrator.run(
                "text",
                "commercial_generic",
                stages=[RCMStage.CODING],
            )
        assert len(result.stages_completed) == 1
        assert result.stages_completed[0] == RCMStage.CODING

    def test_office_visit_no_pa(self, orchestrator, mock_audit_office):
        with patch.object(
            orchestrator._compliance,
            "audit",
            return_value=mock_audit_office,
        ):
            result = orchestrator.run(
                "text",
                "commercial_generic",
                stages=[RCMStage.CODING, RCMStage.ELIGIBILITY],
            )
        assert len(result.stages_completed) == 2

    def test_context_preserved(self, orchestrator, mock_audit):
        with patch.object(orchestrator._compliance, "audit", return_value=mock_audit):
            result = orchestrator.run(
                "text",
                "commercial_generic",
                stages=[RCMStage.CODING],
            )
        assert result.context.payer_id == "commercial_generic"
        assert "73221" in result.context.cpt_codes
