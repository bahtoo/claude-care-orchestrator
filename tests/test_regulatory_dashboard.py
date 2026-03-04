"""
Tests for the Regulatory Dashboard.

Tests metrics aggregation, report generation, and edge cases.
"""

import pytest

from care_orchestrator.models import (
    AgentResult,
    RCMContext,
    RCMResult,
)
from care_orchestrator.regulatory_dashboard import RegulatoryDashboard


@pytest.fixture
def dashboard():
    return RegulatoryDashboard()


def _make_result(
    pa_status="approved",
    has_coding_issues=False,
    claim_valid=True,
    turnaround=0.5,
):
    """Build a mock RCM result."""
    agents = [
        AgentResult(
            agent_name="coding_agent",
            stage="coding",
            success=True,
            output_data={
                "has_coding_issues": has_coding_issues,
                "redacted_text": "redacted",
            },
        ),
        AgentResult(
            agent_name="eligibility_agent",
            stage="eligibility",
            success=True,
            output_data={"is_eligible": True},
        ),
        AgentResult(
            agent_name="prior_auth_agent",
            stage="prior_auth",
            success=True,
            output_data={"pa_status": pa_status},
        ),
        AgentResult(
            agent_name="claims_agent",
            stage="claims",
            success=claim_valid,
            output_data={"is_valid": claim_valid},
        ),
    ]

    context = RCMContext(
        clinical_text="Patient text with SSN 123-45-6789",
        payer_id="commercial_generic",
        agent_results=agents,
    )

    return RCMResult(
        success=claim_valid,
        stages_completed=["coding", "eligibility", "prior_auth", "claims"],
        context=context,
        turnaround_minutes=turnaround,
    )


class TestMetricsAggregation:
    """Tests for metrics computation."""

    def test_empty_dashboard(self, dashboard):
        metrics = dashboard.get_metrics()
        assert metrics.total_encounters == 0

    def test_single_encounter(self, dashboard):
        dashboard.record(_make_result())
        metrics = dashboard.get_metrics()
        assert metrics.total_encounters == 1

    def test_multiple_encounters(self, dashboard):
        dashboard.record(_make_result())
        dashboard.record(_make_result())
        dashboard.record(_make_result())
        metrics = dashboard.get_metrics()
        assert metrics.total_encounters == 3

    def test_phi_redaction_rate(self, dashboard):
        dashboard.record(_make_result())
        metrics = dashboard.get_metrics()
        assert metrics.phi_redaction_rate == 100.0

    def test_pa_approval_rate(self, dashboard):
        dashboard.record(_make_result(pa_status="approved"))
        dashboard.record(_make_result(pa_status="denied"))
        metrics = dashboard.get_metrics()
        assert metrics.pa_approval_rate == 50.0
        assert metrics.pa_denial_rate == 50.0

    def test_coding_error_rate(self, dashboard):
        dashboard.record(_make_result(has_coding_issues=True))
        dashboard.record(_make_result(has_coding_issues=False))
        metrics = dashboard.get_metrics()
        assert metrics.coding_error_rate == 50.0

    def test_claims_submitted(self, dashboard):
        dashboard.record(_make_result(claim_valid=True))
        dashboard.record(_make_result(claim_valid=False))
        metrics = dashboard.get_metrics()
        assert metrics.claims_submitted == 1

    def test_avg_turnaround(self, dashboard):
        dashboard.record(_make_result(turnaround=1.0))
        dashboard.record(_make_result(turnaround=3.0))
        metrics = dashboard.get_metrics()
        assert metrics.avg_turnaround_minutes == 2.0

    def test_appeals_counted_on_denial(self, dashboard):
        dashboard.record(_make_result(pa_status="denied"))
        metrics = dashboard.get_metrics()
        assert metrics.appeals_generated == 1


class TestReportGeneration:
    """Tests for CMS-ready report generation."""

    def test_report_structure(self, dashboard):
        dashboard.record(_make_result())
        report = dashboard.generate_report()
        assert report["report_type"] == "CMS Compliance Summary"
        assert "phi_compliance" in report
        assert "prior_authorization" in report
        assert "coding_quality" in report
        assert "claims" in report
        assert "performance" in report

    def test_empty_report(self, dashboard):
        report = dashboard.generate_report()
        assert report["total_encounters"] == 0

    def test_coding_status_acceptable(self, dashboard):
        dashboard.record(_make_result(has_coding_issues=False))
        report = dashboard.generate_report()
        assert report["coding_quality"]["status"] == "ACCEPTABLE"


class TestReset:
    """Tests for dashboard reset."""

    def test_reset_clears_data(self, dashboard):
        dashboard.record(_make_result())
        dashboard.reset()
        assert dashboard.get_metrics().total_encounters == 0
