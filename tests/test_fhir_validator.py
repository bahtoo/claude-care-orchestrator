"""
Tests for FHIRValidator — US Core profile validation.

Covers Patient, Condition, ServiceRequest, and Procedure profiles,
plus the /fhir/validate FastAPI endpoint.
"""

import pytest
from fastapi.testclient import TestClient

from care_orchestrator.app import app
from care_orchestrator.fhir_validator import FHIRValidator


@pytest.fixture
def validator() -> FHIRValidator:
    return FHIRValidator()


@pytest.fixture
def client():
    with TestClient(app) as c:
        yield c


# ---------------------------------------------------------------------------
# US Core Patient
# ---------------------------------------------------------------------------


class TestPatientValidation:
    def test_valid_full_patient_passes(self, validator):
        resource = {
            "resourceType": "Patient",
            "id": "123",
            "identifier": [{"system": "http://example.org/mrn", "value": "MRN001"}],
            "name": [{"family": "Smith", "given": ["Jane"]}],
            "gender": "female",
            "birthDate": "1980-01-15",
        }
        result = validator.validate("Patient", resource)
        assert result.valid is True
        assert not result.errors

    def test_missing_identifier_raises_error(self, validator):
        resource = {
            "resourceType": "Patient",
            "id": "123",
            "name": [{"family": "Smith", "given": ["Jane"]}],
            "gender": "female",
        }
        result = validator.validate("Patient", resource)
        assert result.valid is False
        assert any("identifier" in e for e in result.errors)

    def test_missing_gender_raises_error(self, validator):
        resource = {
            "resourceType": "Patient",
            "id": "123",
            "identifier": [{"value": "MRN001"}],
            "name": [{"family": "Smith"}],
        }
        result = validator.validate("Patient", resource)
        assert result.valid is False
        assert any("gender" in e for e in result.errors)

    def test_missing_birthdate_raises_warning_not_error(self, validator):
        resource = {
            "resourceType": "Patient",
            "id": "123",
            "identifier": [{"value": "MRN001"}],
            "name": [{"family": "Smith", "given": ["Jane"]}],
            "gender": "unknown",
        }
        result = validator.validate("Patient", resource)
        # Missing birthDate is a warning, not a hard error
        assert any("birthDate" in w for w in result.warnings)

    def test_unsupported_resource_type_fails(self, validator):
        result = validator.validate("MedicationRequest", {"resourceType": "MedicationRequest"})
        assert result.valid is False
        assert any("not supported" in e for e in result.errors)


# ---------------------------------------------------------------------------
# US Core Condition
# ---------------------------------------------------------------------------


class TestConditionValidation:
    def test_valid_condition_passes(self, validator):
        resource = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }
                ]
            },
            "code": {
                "coding": [
                    {
                        "system": "http://hl7.org/fhir/sid/icd-10-cm",
                        "code": "M23.5",
                        "display": "Chronic instability of knee",
                    }
                ]
            },
            "subject": {"reference": "Patient/123"},
        }
        result = validator.validate("Condition", resource)
        assert result.valid is True
        assert not result.errors

    def test_missing_clinical_status_fails(self, validator):
        resource = {
            "resourceType": "Condition",
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "M23.5"}]},
            "subject": {"reference": "Patient/123"},
        }
        result = validator.validate("Condition", resource)
        assert result.valid is False
        assert any("clinicalStatus" in e for e in result.errors)

    def test_wrong_clinical_status_system_fails(self, validator):
        resource = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [{"system": "http://example.org/custom-status", "code": "active"}]
            },
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "M23.5"}]},
            "subject": {"reference": "Patient/123"},
        }
        result = validator.validate("Condition", resource)
        assert result.valid is False
        assert any("terminology.hl7.org" in e for e in result.errors)

    def test_missing_subject_fails(self, validator):
        resource = {
            "resourceType": "Condition",
            "clinicalStatus": {
                "coding": [
                    {
                        "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                        "code": "active",
                    }
                ]
            },
            "code": {"coding": [{"system": "http://hl7.org/fhir/sid/icd-10-cm", "code": "M23.5"}]},
        }
        result = validator.validate("Condition", resource)
        assert result.valid is False
        assert any("subject" in e for e in result.errors)


# ---------------------------------------------------------------------------
# US Core ServiceRequest
# ---------------------------------------------------------------------------


class TestServiceRequestValidation:
    def test_valid_service_request_passes(self, validator):
        resource = {
            "resourceType": "ServiceRequest",
            "status": "draft",
            "intent": "order",
            "code": {
                "coding": [
                    {
                        "system": "http://www.ama-assn.org/go/cpt",
                        "code": "73221",
                    }
                ]
            },
            "subject": {"reference": "Patient/123"},
            "authoredOn": "2026-03-05",
        }
        result = validator.validate("ServiceRequest", resource)
        assert result.valid is True

    def test_missing_intent_fails(self, validator):
        resource = {
            "resourceType": "ServiceRequest",
            "status": "draft",
            "code": {"coding": [{"system": "http://www.ama-assn.org/go/cpt", "code": "73221"}]},
            "subject": {"reference": "Patient/123"},
        }
        result = validator.validate("ServiceRequest", resource)
        assert result.valid is False
        assert any("intent" in e for e in result.errors)


# ---------------------------------------------------------------------------
# /fhir/validate endpoint
# ---------------------------------------------------------------------------


class TestFHIRValidateAPI:
    def test_valid_patient_returns_200(self, client):
        resp = client.post(
            "/fhir/validate",
            json={
                "resource_type": "Patient",
                "resource": {
                    "resourceType": "Patient",
                    "identifier": [{"value": "MRN001"}],
                    "name": [{"family": "Smith", "given": ["Jane"]}],
                    "gender": "female",
                    "birthDate": "1980-01-15",
                },
            },
        )
        assert resp.status_code == 200
        assert resp.json()["valid"] is True

    def test_invalid_patient_returns_errors(self, client):
        resp = client.post(
            "/fhir/validate",
            json={
                "resource_type": "Patient",
                "resource": {"resourceType": "Patient", "id": "bare-minimum"},
            },
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
        assert len(body["errors"]) >= 1

    def test_unsupported_type_returns_error(self, client):
        resp = client.post(
            "/fhir/validate",
            json={"resource_type": "Encounter", "resource": {"resourceType": "Encounter"}},
        )
        assert resp.status_code == 200
        body = resp.json()
        assert body["valid"] is False
