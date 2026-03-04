"""
Tests for the FHIR R4 mapper.

Validates that clinical metadata is correctly mapped to FHIR R4 resources.
"""

import pytest

from care_orchestrator.fhir_mapper import FHIRMapper
from care_orchestrator.models import AdminMetadata


@pytest.fixture
def mapper():
    """Fresh FHIRMapper instance for each test."""
    return FHIRMapper()


@pytest.fixture
def sample_metadata():
    """Sample admin metadata with codes."""
    return AdminMetadata(
        cpt_codes=["73221"],
        icd10_codes=["M23.5"],
        workflow_type="prior_auth",
    )


@pytest.fixture
def multi_code_metadata():
    """Metadata with multiple codes."""
    return AdminMetadata(
        cpt_codes=["99214", "72148"],
        icd10_codes=["E11.9", "I10", "M54.5"],
        workflow_type="coding",
    )


# ---------------------------------------------------------------------------
# Patient Resource
# ---------------------------------------------------------------------------


class TestPatientResource:
    """Tests for FHIR Patient resource generation."""

    def test_patient_generated(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        patient_resources = [r for r in output.resources if r.resource_type == "Patient"]
        assert len(patient_resources) == 1

    def test_patient_is_valid(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        patient = next(r for r in output.resources if r.resource_type == "Patient")
        assert patient.is_valid
        assert patient.validation_errors == []

    def test_patient_has_redacted_name(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        patient = next(r for r in output.resources if r.resource_type == "Patient")
        names = patient.resource_json.get("name", [])
        assert len(names) > 0
        assert names[0]["family"] == "[REDACTED]"

    def test_patient_phi_tag(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        patient = next(r for r in output.resources if r.resource_type == "Patient")
        tags = patient.resource_json.get("meta", {}).get("tag", [])
        assert any(t.get("code") == "redacted" for t in tags)


# ---------------------------------------------------------------------------
# Condition Resource (ICD-10)
# ---------------------------------------------------------------------------


class TestConditionResource:
    """Tests for FHIR Condition resource generation from ICD-10 codes."""

    def test_condition_generated(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        conditions = [r for r in output.resources if r.resource_type == "Condition"]
        assert len(conditions) == 1

    def test_condition_has_correct_code(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        condition = next(r for r in output.resources if r.resource_type == "Condition")
        coding = condition.resource_json["code"]["coding"][0]
        assert coding["code"] == "M23.5"
        assert coding["system"] == "http://hl7.org/fhir/sid/icd-10-cm"

    def test_condition_is_valid(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        condition = next(r for r in output.resources if r.resource_type == "Condition")
        assert condition.is_valid

    def test_multiple_conditions(self, mapper, multi_code_metadata):
        output = mapper.map(multi_code_metadata, "redacted text")
        conditions = [r for r in output.resources if r.resource_type == "Condition"]
        assert len(conditions) == 3  # E11.9, I10, M54.5


# ---------------------------------------------------------------------------
# Procedure Resource (CPT)
# ---------------------------------------------------------------------------


class TestProcedureResource:
    """Tests for FHIR Procedure resource generation from CPT codes."""

    def test_procedure_generated(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        procedures = [r for r in output.resources if r.resource_type == "Procedure"]
        assert len(procedures) == 1

    def test_procedure_has_correct_code(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        procedure = next(r for r in output.resources if r.resource_type == "Procedure")
        coding = procedure.resource_json["code"]["coding"][0]
        assert coding["code"] == "73221"
        assert coding["system"] == "http://www.ama-assn.org/go/cpt"

    def test_procedure_is_valid(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        procedure = next(r for r in output.resources if r.resource_type == "Procedure")
        assert procedure.is_valid

    def test_multiple_procedures(self, mapper, multi_code_metadata):
        output = mapper.map(multi_code_metadata, "redacted text")
        procedures = [r for r in output.resources if r.resource_type == "Procedure"]
        assert len(procedures) == 2  # 99214, 72148


# ---------------------------------------------------------------------------
# ServiceRequest (Prior Auth)
# ---------------------------------------------------------------------------


class TestServiceRequest:
    """Tests for FHIR ServiceRequest generation in Prior Auth workflows."""

    def test_service_request_for_prior_auth(self, mapper, sample_metadata):
        """ServiceRequest should only be generated for prior_auth workflows."""
        output = mapper.map(sample_metadata, "redacted text")
        srs = [r for r in output.resources if r.resource_type == "ServiceRequest"]
        assert len(srs) == 1

    def test_no_service_request_for_coding(self, mapper, multi_code_metadata):
        """ServiceRequest should NOT be generated for coding workflows."""
        output = mapper.map(multi_code_metadata, "redacted text")
        srs = [r for r in output.resources if r.resource_type == "ServiceRequest"]
        assert len(srs) == 0

    def test_service_request_has_reason_codes(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        sr = next(r for r in output.resources if r.resource_type == "ServiceRequest")
        assert sr.is_valid
        # Should reference the ICD-10 diagnosis as reason (FHIR R5: 'reason' field)
        reasons = sr.resource_json.get("reason", [])
        assert len(reasons) > 0


# ---------------------------------------------------------------------------
# Overall Output
# ---------------------------------------------------------------------------


class TestFHIROutput:
    """Tests for overall FHIR output structure."""

    def test_total_resources_count(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "redacted text")
        # Patient + 1 Condition + 1 Procedure + 1 ServiceRequest = 4
        assert output.total_resources == 4

    def test_source_text_preserved(self, mapper, sample_metadata):
        output = mapper.map(sample_metadata, "the redacted clinical text")
        assert output.source_text_redacted == "the redacted clinical text"

    def test_empty_codes(self, mapper):
        empty_metadata = AdminMetadata(cpt_codes=[], icd10_codes=[], workflow_type="general")
        output = mapper.map(empty_metadata, "text")
        # Should still generate Patient resource
        assert output.total_resources == 1
        assert output.resources[0].resource_type == "Patient"
