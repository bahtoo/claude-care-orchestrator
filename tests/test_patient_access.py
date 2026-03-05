"""
Tests for the CMS-0057 Patient Access FHIR API.

Covers: /Patient/{id}/$everything, /ExplanationOfBenefit, /Coverage.
Uses FastAPI TestClient (sync) — no async test runner needed for HTTP layer.
Database is patched to return canned records, keeping tests fast and isolated.
"""

from unittest.mock import AsyncMock, patch

import pytest
from fastapi.testclient import TestClient

from care_orchestrator.app import app
from care_orchestrator.fhir_bundle import make_bundle, make_coverage_entry, make_eob_entry

# ---------------------------------------------------------------------------
# Fixtures
# ---------------------------------------------------------------------------


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


SAMPLE_RECORD = {
    "pa_number": "PA-20260305-001",
    "patient_id": "patient-123",
    "pa_status": "approved",
    "cpt_codes": ["73221"],
    "icd10_codes": ["M23.5"],
    "turnaround_minutes": 4.5,
    "created_at": "2026-03-05T04:00:00+00:00",
    "summary": "Approved after review",
    "success": True,
    "stages_completed": 4,
}


# ---------------------------------------------------------------------------
# fhir_bundle unit tests
# ---------------------------------------------------------------------------


class TestFHIRBundle:
    def test_make_bundle_structure(self):
        entries = [{"resourceType": "Patient", "id": "p1"}]
        bundle = make_bundle("Patient", entries)
        assert bundle["resourceType"] == "Bundle"
        assert bundle["type"] == "searchset"
        assert bundle["total"] == 1
        assert len(bundle["entry"]) == 1

    def test_make_bundle_empty(self):
        bundle = make_bundle("Patient", [])
        assert bundle["total"] == 0
        assert bundle["entry"] == []

    def test_make_bundle_full_url(self):
        entries = [{"resourceType": "Patient", "id": "abc"}]
        bundle = make_bundle("Patient", entries, base_url="http://test")
        assert bundle["entry"][0]["fullUrl"] == "http://test/Patient/abc"

    def test_make_eob_entry_structure(self):
        eob = make_eob_entry(SAMPLE_RECORD)
        assert eob["resourceType"] == "ExplanationOfBenefit"
        assert eob["patient"]["reference"] == "Patient/patient-123"
        assert len(eob["item"]) == 1
        assert eob["item"][0]["productOrService"]["coding"][0]["code"] == "73221"

    def test_make_coverage_entry_structure(self):
        cov = make_coverage_entry(SAMPLE_RECORD)
        assert cov["resourceType"] == "Coverage"
        assert cov["beneficiary"]["reference"] == "Patient/patient-123"
        assert cov["status"] == "active"


# ---------------------------------------------------------------------------
# /Patient/{id}/$everything
# ---------------------------------------------------------------------------


class TestPatientEverything:
    def test_empty_patient_returns_bundle(self, client):
        with patch(
            "care_orchestrator.patient_access._get_patient_records",
            new_callable=AsyncMock,
            return_value=[],
        ):
            resp = client.get("/Patient/unknown-patient/$everything")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resourceType"] == "Bundle"
        assert body["total"] == 0

    def test_patient_with_record_returns_entries(self, client):
        with patch(
            "care_orchestrator.patient_access._get_patient_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD],
        ):
            resp = client.get("/Patient/patient-123/$everything")
        assert resp.status_code == 200
        body = resp.json()
        # Patient + EOB + Coverage = 3 entries
        assert body["total"] == 3

    def test_bundle_contains_eob_and_coverage(self, client):
        with patch(
            "care_orchestrator.patient_access._get_patient_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD],
        ):
            resp = client.get("/Patient/patient-123/$everything")
        types = [e["resource"]["resourceType"] for e in resp.json()["entry"]]
        assert "Patient" in types
        assert "ExplanationOfBenefit" in types
        assert "Coverage" in types


# ---------------------------------------------------------------------------
# /ExplanationOfBenefit
# ---------------------------------------------------------------------------


class TestExplanationOfBenefit:
    def test_eob_returns_bundle(self, client):
        with patch(
            "care_orchestrator.patient_access._get_patient_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD],
        ):
            resp = client.get("/ExplanationOfBenefit?patient=Patient/patient-123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resourceType"] == "Bundle"
        assert body["total"] == 1
        assert body["entry"][0]["resource"]["resourceType"] == "ExplanationOfBenefit"

    def test_eob_unfiltered_uses_all_records(self, client):
        with patch(
            "care_orchestrator.patient_access._all_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD, SAMPLE_RECORD],
        ):
            resp = client.get("/ExplanationOfBenefit")
        assert resp.status_code == 200
        assert resp.json()["total"] == 2


# ---------------------------------------------------------------------------
# /Coverage
# ---------------------------------------------------------------------------


class TestCoverage:
    def test_coverage_returns_bundle(self, client):
        with patch(
            "care_orchestrator.patient_access._get_patient_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD],
        ):
            resp = client.get("/Coverage?beneficiary=Patient/patient-123")
        assert resp.status_code == 200
        body = resp.json()
        assert body["resourceType"] == "Bundle"
        assert body["entry"][0]["resource"]["resourceType"] == "Coverage"

    def test_coverage_unfiltered(self, client):
        with patch(
            "care_orchestrator.patient_access._all_records",
            new_callable=AsyncMock,
            return_value=[SAMPLE_RECORD],
        ):
            resp = client.get("/Coverage")
        assert resp.status_code == 200
        assert resp.json()["total"] == 1
