"""
Tests for the Eligibility Agent.

Tests coverage verification, PA requirement detection, and payer lookup.
"""

import pytest

from care_orchestrator.agents.eligibility_agent import EligibilityAgent
from care_orchestrator.models import AgentTask


@pytest.fixture
def agent():
    return EligibilityAgent(policies_dir="config/policies")


def _make_task(payer_id="commercial_generic", cpt=None, icd=None):
    return AgentTask(
        task_type="eligibility",
        input_data={"payer_id": payer_id},
        context={
            "cpt_codes": cpt or [],
            "icd10_codes": icd or [],
            "payer_id": payer_id,
        },
    )


class TestEligibilityCheck:
    """Tests for eligibility verification."""

    def test_eligible_with_covered_codes(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.success is True
        assert result.output_data["is_eligible"] is True

    def test_unknown_payer_fails(self, agent):
        task = _make_task(payer_id="nonexistent", cpt=["73221"])
        result = agent.process(task)
        assert result.success is False
        assert "not found" in result.errors[0]

    def test_pa_required_flagged(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert "73221" in result.output_data["pa_required_codes"]

    def test_no_pa_for_office_visit(self, agent):
        task = _make_task(cpt=["99213"], icd=["M23.5"])
        result = agent.process(task)
        assert "99213" not in result.output_data.get("pa_required_codes", [])

    def test_payer_name_returned(self, agent):
        task = _make_task(cpt=["73221"])
        result = agent.process(task)
        assert result.output_data["payer_name"] == "Generic Commercial Payer"

    def test_empty_codes_eligible(self, agent):
        task = _make_task(cpt=[], icd=[])
        result = agent.process(task)
        assert result.output_data["is_eligible"] is True

    def test_can_handle_eligibility(self, agent):
        task = AgentTask(task_type="eligibility")
        assert agent.can_handle(task) is True
        task2 = AgentTask(task_type="coding")
        assert agent.can_handle(task2) is False

    def test_medicare_payer(self):
        agent = EligibilityAgent(policies_dir="config/policies")
        task = _make_task(payer_id="medicare", cpt=["73221"])
        result = agent.process(task)
        assert result.success is True
        assert result.output_data["payer_name"] == "Medicare (CMS)"
