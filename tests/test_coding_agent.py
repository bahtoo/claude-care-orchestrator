"""
Tests for the Coding Agent.

Tests code validation, bundling conflicts, modifier recs, and pairings.
"""

import pytest

from care_orchestrator.agents.coding_agent import CodingAgent
from care_orchestrator.models import AgentTask


@pytest.fixture
def agent():
    return CodingAgent()


def _make_task(cpt=None, icd=None, text=""):
    return AgentTask(
        task_type="coding",
        input_data={"clinical_text": text},
        context={
            "cpt_codes": cpt or [],
            "icd10_codes": icd or [],
        },
    )


class TestCodingValidation:
    """Tests for code validation logic."""

    def test_valid_codes_no_errors(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.success is True
        assert len(result.errors) == 0

    def test_bundling_conflict_detected(self, agent):
        task = _make_task(cpt=["99215", "99213"], icd=["M23.5"])
        result = agent.process(task)
        assert any("Bundling" in e for e in result.errors)

    def test_no_bundling_conflict_different_codes(self, agent):
        task = _make_task(cpt=["73221", "72148"], icd=["M23.5"])
        result = agent.process(task)
        assert not any("Bundling" in e for e in result.errors)

    def test_modifier_recommendation(self, agent):
        task = _make_task(cpt=["99213", "73221"], icd=["M23.5"])
        result = agent.process(task)
        assert any("modifier" in r for r in result.recommendations)

    def test_no_modifier_for_single_em(self, agent):
        task = _make_task(cpt=["99213"], icd=["M23.5"])
        result = agent.process(task)
        assert not any("modifier" in r for r in result.recommendations)

    def test_pairing_warning(self, agent):
        task = _make_task(cpt=["27447"], icd=["Z00.00"])
        result = agent.process(task)
        assert any("qualifying" in r.lower() for r in result.recommendations)

    def test_valid_pairing_no_warning(self, agent):
        task = _make_task(cpt=["27447"], icd=["M17.11"])
        result = agent.process(task)
        assert not any("qualifying" in r.lower() for r in result.recommendations)

    def test_empty_codes(self, agent):
        task = _make_task(cpt=[], icd=[])
        result = agent.process(task)
        assert result.success is True

    def test_output_contains_codes(self, agent):
        task = _make_task(cpt=["73221"], icd=["M23.5"])
        result = agent.process(task)
        assert result.output_data["cpt_codes"] == ["73221"]
        assert result.output_data["icd10_codes"] == ["M23.5"]

    def test_can_handle_coding_task(self, agent):
        task = AgentTask(task_type="coding")
        assert agent.can_handle(task) is True
        task2 = AgentTask(task_type="claims")
        assert agent.can_handle(task2) is False
