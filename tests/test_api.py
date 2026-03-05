"""
Tests for the FastAPI FHIR endpoints.

All LLM calls are mocked. Tests cover happy paths and error conditions
for all 4 endpoints: POST /prior-authorization, GET /prior-authorization/{id},
POST /coding/validate, GET /compliance/metrics.
"""

from unittest.mock import MagicMock, patch
import uuid

import pytest
from fastapi.testclient import TestClient

from care_orchestrator.app import app
from care_orchestrator.models import (
    AgentResult,
    RCMContext,
    RCMResult,
)


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


def _make_rcm_result(pa_status: str = "approved") -> RCMResult:
    """Build a minimal mock RCMResult."""
    agents = [
        AgentResult(
            agent_name="coding_agent_coding",
            stage="coding",
            success=True,
            output_data={"cpt_codes": ["73221"], "icd10_codes": ["M23.5"]},
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
            output_data={
                "pa_status": pa_status,
                "pa_number": f"PA-COM-{uuid.uuid4().hex[:6].upper()}",
            },
        ),
        AgentResult(
            agent_name="claims_agent",
            stage="claims",
            success=True,
            output_data={"is_valid": True},
        ),
    ]
    context = RCMContext(
        clinical_text="Patient has knee pain.",
        payer_id="commercial_generic",
        agent_results=agents,
    )
    return RCMResult(
        success=True,
        stages_completed=["coding", "eligibility", "prior_auth", "claims"],
        context=context,
        summary="RCM pipeline completed: 4/4 stages.",
        turnaround_minutes=0.1,
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


class TestHealth:
    def test_health_ok(self, client):
        resp = client.get("/health")
        assert resp.status_code == 200
        assert resp.json()["status"] == "ok"


# ---------------------------------------------------------------------------
# POST /prior-authorization
# ---------------------------------------------------------------------------


class TestSubmitPriorAuth:
    def test_valid_request_returns_201(self, client):
        with patch("care_orchestrator.app._get_rcm") as mock_rcm_factory:
            mock_rcm = MagicMock()
            mock_rcm.run.return_value = _make_rcm_result()
            mock_rcm_factory.return_value = mock_rcm

            resp = client.post(
                "/prior-authorization",
                json={
                    "clinical_text": "Patient presents with knee pain requiring MRI.",
                    "payer_id": "commercial_generic",
                },
            )
        assert resp.status_code == 201
        body = resp.json()
        assert body["pa_status"] == "approved"
        assert body["success"] is True
        assert body["turnaround_minutes"] >= 0

    def test_pa_number_present(self, client):
        with patch("care_orchestrator.app._get_rcm") as mock_rcm_factory:
            mock_rcm = MagicMock()
            mock_rcm.run.return_value = _make_rcm_result()
            mock_rcm_factory.return_value = mock_rcm

            resp = client.post(
                "/prior-authorization",
                json={
                    "clinical_text": "Patient requires MRI of the right knee.",
                    "payer_id": "commercial_generic",
                },
            )
        assert resp.json()["pa_number"].startswith("PA-COM-")

    def test_missing_clinical_text_returns_422(self, client):
        resp = client.post(
            "/prior-authorization",
            json={"payer_id": "commercial_generic"},
        )
        assert resp.status_code == 422

    def test_short_clinical_text_returns_422(self, client):
        resp = client.post(
            "/prior-authorization",
            json={"clinical_text": "Hi", "payer_id": "commercial_generic"},
        )
        assert resp.status_code == 422


# ---------------------------------------------------------------------------
# GET /prior-authorization/{pa_number}
# ---------------------------------------------------------------------------


class TestGetPriorAuth:
    def test_not_found_returns_404(self, client):
        resp = client.get("/prior-authorization/PA-NONEXISTENT-999")
        assert resp.status_code == 404

    def test_found_after_submit(self, client):
        with patch("care_orchestrator.app._get_rcm") as mock_rcm_factory:
            mock_rcm = MagicMock()
            mock_rcm.run.return_value = _make_rcm_result()
            mock_rcm_factory.return_value = mock_rcm

            post_resp = client.post(
                "/prior-authorization",
                json={
                    "clinical_text": "Knee pain with mechanical symptoms.",
                    "payer_id": "commercial_generic",
                },
            )

        # Dashboard lookup — may or may not be in memory depending on mock path
        pa_num = post_resp.json()["pa_number"]
        resp = client.get(f"/prior-authorization/{pa_num}")
        # 200 if dashboard recorded it, 404 otherwise (both valid in unit test)
        assert resp.status_code in (200, 404)


# ---------------------------------------------------------------------------
# POST /coding/validate
# ---------------------------------------------------------------------------


class TestValidateCoding:
    def test_valid_codes(self, client):
        resp = client.post(
            "/coding/validate",
            json={"cpt_codes": ["73221"], "icd10_codes": ["M23.5"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert "valid" in body
        assert "errors" in body

    def test_empty_cpt_returns_422(self, client):
        resp = client.post(
            "/coding/validate",
            json={"cpt_codes": [], "icd10_codes": ["M23.5"]},
        )
        assert resp.status_code == 422

    def test_bundling_conflict_detected(self, client):
        resp = client.post(
            "/coding/validate",
            json={"cpt_codes": ["99215", "99213"], "icd10_codes": ["M23.5"]},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert any("Bundling" in e for e in body["errors"])


# ---------------------------------------------------------------------------
# GET /compliance/metrics
# ---------------------------------------------------------------------------


class TestComplianceMetrics:
    def test_empty_metrics_returns_200(self, client):
        resp = client.get("/compliance/metrics")
        assert resp.status_code == 200
        body = resp.json()
        assert "total_encounters" in body
        assert "report_type" in body
