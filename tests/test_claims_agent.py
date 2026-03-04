"""
Tests for the Claims Agent.

Tests claim assembly, validation, and denial routing.
"""

import pytest

from care_orchestrator.agents.claims_agent import ClaimsAgent
from care_orchestrator.models import AgentTask


@pytest.fixture
def agent():
    return ClaimsAgent()


def _make_task(
    payer="commercial_generic",
    cpt=None,
    icd=None,
    eligible=True,
    pa_status="approved",
    pa_number="PA-COM-001",
):
    return AgentTask(
        task_type="claims",
        input_data={},
        context={
            "payer_id": payer,
            "cpt_codes": cpt or [],
            "icd10_codes": icd or [],
            "is_eligible": eligible,
            "pa_status": pa_status,
            "pa_number": pa_number,
        },
    )


class TestClaimAssembly:
    """Tests for claim generation."""

    def test_valid_claim(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.success is True
        assert result.output_data["is_valid"] is True
        assert result.output_data["line_count"] == 1

    def test_total_charges_calculated(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.output_data["total_charges"] == 1200.00

    def test_multi_line_claim(self, agent):
        task = _make_task(cpt=["99214", "73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.output_data["line_count"] == 2
        assert result.output_data["total_charges"] == 225.0 + 1200.0

    def test_claim_has_auth_number(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        claim = result.output_data["claim"]
        assert claim["authorization_number"] == "PA-COM-001"


class TestClaimValidation:
    """Tests for claim validation rules."""

    def test_not_eligible_fails(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"], eligible=False)
        result = agent.process(task)
        assert result.success is False
        assert any("not eligible" in e.lower() for e in result.errors)

    def test_denied_pa_fails(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"], pa_status="denied")
        result = agent.process(task)
        assert result.success is False
        assert any("denied" in e.lower() for e in result.errors)

    def test_denied_pa_recommends_appeal(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"], pa_status="denied")
        result = agent.process(task)
        assert any("appeal" in r.lower() for r in result.recommendations)

    def test_pending_pa_fails(self, agent):
        task = _make_task(
            cpt=["73221"],
            icd=["M23.5"],
            pa_status="pending_additional_info",
        )
        result = agent.process(task)
        assert result.success is False

    def test_no_cpt_validation_error(self, agent):
        task = _make_task(cpt=[], icd=["M23.5"])
        result = agent.process(task)
        assert any("No CPT" in e for e in result.errors)

    def test_no_icd_validation_error(self, agent):
        task = _make_task(cpt=["73221"], icd=[])
        result = agent.process(task)
        assert any("No ICD" in e for e in result.errors)

    def test_can_handle_claims(self, agent):
        task = AgentTask(task_type="claims")
        assert agent.can_handle(task) is True
