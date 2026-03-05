"""
Tests for the Appeal Letter Generator.

All LLM calls are mocked — no API key needed.
Tests cover initial appeals, peer-to-peer, external review, and parsing.
"""

from unittest.mock import MagicMock

import pytest

from care_orchestrator.appeal_generator import AppealGenerator
from care_orchestrator.models import (
    AppealType,
    NecessityDecision,
    NecessityDetermination,
)

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def generator():
    return AppealGenerator(api_key="test-key", model="test-model")


@pytest.fixture
def denied_decision():
    return NecessityDecision(
        determination=NecessityDetermination.DENIED,
        rationale="Insufficient documentation of failed conservative treatment.",
        criteria_met=["Clinical exam findings"],
        criteria_unmet=["Failed initial treatment"],
        missing_documentation=["Physical therapy records"],
        confidence_score=0.8,
    )


@pytest.fixture
def sample_appeal_response():
    return """
<appeal>
    <letter>
# Appeal for Prior Authorization — CPT 73221

**Date:** [DATE]

**To:** Medical Director, Test Payer
**From:** Treating Physician
**Re:** Appeal of Prior Authorization Denial

## Summary

We are writing to appeal the denial of MRI authorization for our patient
who presents with chronic knee instability (ICD-10: M23.5).

## Clinical Justification

Physical examination reveals positive Lachman test and joint line tenderness.
The patient has undergone 8 weeks of conservative treatment including
physical therapy without improvement.

## Requested Action

We respectfully request reconsideration of this authorization.
    </letter>
    <justification>
    Physical exam confirms structural knee instability requiring imaging for surgical planning.
    Conservative treatment has been attempted and documented as failed.
    </justification>
    <policy_citations>
    Section 4.2 - Advanced Imaging Requirements, Section 7.1 - Appeal Procedures
    </policy_citations>
</appeal>
"""


@pytest.fixture
def peer_to_peer_response():
    return """
<appeal>
    <letter>
# Peer-to-Peer Review Talking Points — CPT 73221

1. Patient has M23.5 (chronic knee instability)
2. Physical exam shows positive Lachman test
3. 8 weeks of conservative treatment completed without improvement
4. MRI needed for surgical planning
    </letter>
    <justification>
    Strong clinical indication for imaging based on exam findings and failed conservative care.
    </justification>
    <policy_citations>NONE</policy_citations>
</appeal>
"""


def _mock_llm(generator, response_text):
    """Patch the generator's client to return mocked LLM response."""
    mock_message = MagicMock()
    mock_message.content = [MagicMock(text=response_text)]
    mock_client = MagicMock()
    mock_client.messages.create.return_value = mock_message

    generator._client = mock_client
    return generator


# ---------------------------------------------------------------------------
# Initial Appeal Tests
# ---------------------------------------------------------------------------


class TestInitialAppeal:
    """Tests for initial appeal letter generation."""

    def test_generates_letter_content(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="Insufficient documentation",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="Patient presents with knee instability...",
            necessity_decision=denied_decision,
        )
        assert len(letter.letter_content) > 0

    def test_appeal_type_is_initial(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="Insufficient documentation",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert letter.appeal_type == AppealType.INITIAL

    def test_denial_reason_preserved(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="My specific denial reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert letter.denial_reason == "My specific denial reason"

    def test_procedure_code_preserved(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert letter.procedure_code == "73221"

    def test_policy_citations_parsed(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert len(letter.policy_citations) > 0

    def test_justification_parsed(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert len(letter.clinical_justification) > 0


# ---------------------------------------------------------------------------
# Peer-to-Peer Review Tests
# ---------------------------------------------------------------------------


class TestPeerToPeer:
    """Tests for peer-to-peer review appeal."""

    def test_generates_p2p_content(self, generator, denied_decision, peer_to_peer_response):
        _mock_llm(generator, peer_to_peer_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
            appeal_type=AppealType.PEER_TO_PEER,
        )
        assert letter.appeal_type == AppealType.PEER_TO_PEER
        assert len(letter.letter_content) > 0

    def test_no_citations_returns_empty_list(
        self, generator, denied_decision, peer_to_peer_response
    ):
        _mock_llm(generator, peer_to_peer_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
            appeal_type=AppealType.PEER_TO_PEER,
        )
        assert letter.policy_citations == []


# ---------------------------------------------------------------------------
# Edge Cases
# ---------------------------------------------------------------------------


class TestParsingEdgeCases:
    """Tests for XML parsing edge cases."""

    def test_malformed_response_uses_raw(self, generator, denied_decision):
        _mock_llm(generator, "This is just plain text, not XML.")
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=["M23.5"],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        # Fallback: raw response becomes the letter
        assert letter.letter_content == "This is just plain text, not XML."

    def test_empty_diagnosis_codes(self, generator, denied_decision, sample_appeal_response):
        _mock_llm(generator, sample_appeal_response)
        letter = generator.generate(
            denial_reason="reason",
            procedure_code="73221",
            diagnosis_codes=[],
            clinical_text="text",
            necessity_decision=denied_decision,
        )
        assert letter.letter_content  # Should still generate
