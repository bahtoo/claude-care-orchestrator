"""
Tests for the Medical Necessity Evaluator.

All LLM calls are mocked — no API key needed.
Tests cover approved/denied/needs_info scenarios and XML parsing.
"""

from unittest.mock import MagicMock, PropertyMock

import pytest

from care_orchestrator.medical_necessity import MedicalNecessityEvaluator
from care_orchestrator.models import CoverageCriteria, NecessityDetermination

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def evaluator():
    return MedicalNecessityEvaluator(api_key="test-key", model="test-model")


@pytest.fixture
def sample_criteria():
    return CoverageCriteria(
        required_diagnoses=["M23.5", "S83.5"],
        required_documentation=[
            "Clinical exam findings",
            "Failed initial treatment",
        ],
        age_restrictions="none",
        review_timeline_hours=48,
    )


@pytest.fixture
def approved_response():
    return """
<necessity_evaluation>
    <determination>APPROVED</determination>
    <confidence>0.92</confidence>
    <rationale>Clinical documentation supports necessity.</rationale>
    <criteria_met>Clinical exam findings, Failed initial treatment</criteria_met>
    <criteria_unmet>NONE</criteria_unmet>
    <missing_docs>NONE</missing_docs>
</necessity_evaluation>
"""


@pytest.fixture
def denied_response():
    return """
<necessity_evaluation>
    <determination>DENIED</determination>
    <confidence>0.85</confidence>
    <rationale>Documentation lacks failed conservative treatment.</rationale>
    <criteria_met>Clinical exam findings</criteria_met>
    <criteria_unmet>Failed initial treatment</criteria_unmet>
    <missing_docs>Physical therapy records, Conservative treatment documentation</missing_docs>
</necessity_evaluation>
"""


@pytest.fixture
def needs_info_response():
    return """
<necessity_evaluation>
    <determination>NEEDS_ADDITIONAL_INFO</determination>
    <confidence>0.60</confidence>
    <rationale>Clinical exam findings are present but treatment history is incomplete.</rationale>
    <criteria_met>Clinical exam findings</criteria_met>
    <criteria_unmet>NONE</criteria_unmet>
    <missing_docs>Treatment history documentation</missing_docs>
</necessity_evaluation>
"""


def _mock_llm(evaluator, response_text):
    """Patch the evaluator's client to return a mocked LLM response."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    type(evaluator).client = PropertyMock(return_value=mock_client)
    return evaluator


# ---------------------------------------------------------------------------
# Evaluation Tests
# ---------------------------------------------------------------------------


class TestApprovedDecision:
    """Tests for approved medical necessity decisions."""

    def test_determination_is_approved(self, evaluator, sample_criteria, approved_response):
        _mock_llm(evaluator, approved_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert dec.determination == NecessityDetermination.APPROVED

    def test_confidence_parsed(self, evaluator, sample_criteria, approved_response):
        _mock_llm(evaluator, approved_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert dec.confidence_score == pytest.approx(0.92, abs=0.01)

    def test_criteria_met_populated(self, evaluator, sample_criteria, approved_response):
        _mock_llm(evaluator, approved_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.criteria_met) > 0

    def test_no_criteria_unmet(self, evaluator, sample_criteria, approved_response):
        _mock_llm(evaluator, approved_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.criteria_unmet) == 0

    def test_rationale_not_empty(self, evaluator, sample_criteria, approved_response):
        _mock_llm(evaluator, approved_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.rationale) > 0


class TestDeniedDecision:
    """Tests for denied medical necessity decisions."""

    def test_determination_is_denied(self, evaluator, sample_criteria, denied_response):
        _mock_llm(evaluator, denied_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert dec.determination == NecessityDetermination.DENIED

    def test_criteria_unmet_populated(self, evaluator, sample_criteria, denied_response):
        _mock_llm(evaluator, denied_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.criteria_unmet) > 0
        assert "Failed initial treatment" in dec.criteria_unmet

    def test_missing_docs_populated(self, evaluator, sample_criteria, denied_response):
        _mock_llm(evaluator, denied_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.missing_documentation) > 0


class TestNeedsInfoDecision:
    """Tests for needs-additional-info decisions."""

    def test_determination_is_needs_info(self, evaluator, sample_criteria, needs_info_response):
        _mock_llm(evaluator, needs_info_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert dec.determination == NecessityDetermination.NEEDS_INFO

    def test_has_missing_docs(self, evaluator, sample_criteria, needs_info_response):
        _mock_llm(evaluator, needs_info_response)
        dec = evaluator.evaluate("clinical text", "73221", ["M23.5"], sample_criteria)
        assert len(dec.missing_documentation) > 0


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestParsingEdgeCases:
    """Tests for XML parsing edge cases."""

    def test_malformed_response_returns_needs_info(self, evaluator, sample_criteria):
        _mock_llm(evaluator, "This is not valid XML at all.")
        dec = evaluator.evaluate("text", "73221", ["M23.5"], sample_criteria)
        assert dec.determination == NecessityDetermination.NEEDS_INFO

    def test_confidence_clamped_to_max(self, evaluator, sample_criteria):
        xml = """
<necessity_evaluation>
    <determination>APPROVED</determination>
    <confidence>1.5</confidence>
    <rationale>Test</rationale>
    <criteria_met>NONE</criteria_met>
    <criteria_unmet>NONE</criteria_unmet>
    <missing_docs>NONE</missing_docs>
</necessity_evaluation>
"""
        _mock_llm(evaluator, xml)
        dec = evaluator.evaluate("text", "73221", ["M23.5"], sample_criteria)
        assert dec.confidence_score <= 1.0

    def test_confidence_clamped_to_min(self, evaluator, sample_criteria):
        xml = """
<necessity_evaluation>
    <determination>DENIED</determination>
    <confidence>-0.5</confidence>
    <rationale>Test</rationale>
    <criteria_met>NONE</criteria_met>
    <criteria_unmet>NONE</criteria_unmet>
    <missing_docs>NONE</missing_docs>
</necessity_evaluation>
"""
        _mock_llm(evaluator, xml)
        dec = evaluator.evaluate("text", "73221", ["M23.5"], sample_criteria)
        assert dec.confidence_score >= 0.0
