"""
Tests for Pydantic data models.

Validates model creation, serialization, and validation constraints.
"""

from care_orchestrator.models import (
    AdminMetadata,
    ClinicalNote,
    FHIRResourceOutput,
    PHIDetectionResult,
    PHIEntity,
    PHIType,
)


class TestPHIEntity:
    """Tests for PHIEntity model."""

    def test_create_entity(self):
        entity = PHIEntity(value="123-45-6789", phi_type=PHIType.SSN, start=0, end=11)
        assert entity.value == "123-45-6789"
        assert entity.phi_type == PHIType.SSN

    def test_entity_serialization(self):
        entity = PHIEntity(value="test@email.com", phi_type=PHIType.EMAIL, start=5, end=19)
        data = entity.model_dump()
        assert data["phi_type"] == "EMAIL"
        assert data["start"] == 5


class TestPHIDetectionResult:
    """Tests for PHIDetectionResult model."""

    def test_clean_result(self):
        result = PHIDetectionResult(is_clean=True, entities=[], redacted_text="clean text")
        assert result.is_clean
        assert result.entity_count == 0

    def test_result_with_entities(self):
        entities = [
            PHIEntity(value="123-45-6789", phi_type=PHIType.SSN, start=0, end=11),
            PHIEntity(value="test@test.com", phi_type=PHIType.EMAIL, start=20, end=33),
        ]
        result = PHIDetectionResult(
            is_clean=False, entities=entities, redacted_text="[REDACTED]", entity_count=2
        )
        assert not result.is_clean
        assert result.entity_count == 2


class TestClinicalNote:
    """Tests for ClinicalNote model."""

    def test_minimal_note(self):
        note = ClinicalNote(text="Patient presents with pain")
        assert note.text == "Patient presents with pain"
        assert note.source == "unknown"
        assert note.note_type == "general"

    def test_full_note(self):
        note = ClinicalNote(text="...", source="epic", note_type="discharge")
        assert note.source == "epic"
        assert note.note_type == "discharge"


class TestAdminMetadata:
    """Tests for AdminMetadata model."""

    def test_empty_metadata(self):
        meta = AdminMetadata()
        assert meta.cpt_codes == []
        assert meta.icd10_codes == []
        assert meta.workflow_type == "unknown"

    def test_populated_metadata(self):
        meta = AdminMetadata(
            cpt_codes=["73221", "99214"],
            icd10_codes=["M23.5"],
            workflow_type="prior_auth",
        )
        assert len(meta.cpt_codes) == 2
        assert meta.workflow_type == "prior_auth"


class TestFHIRResourceOutput:
    """Tests for FHIRResourceOutput model."""

    def test_valid_resource(self):
        resource = FHIRResourceOutput(
            resource_type="Patient",
            resource_json={"resourceType": "Patient", "id": "test"},
            is_valid=True,
        )
        assert resource.is_valid
        assert resource.validation_errors == []

    def test_invalid_resource(self):
        resource = FHIRResourceOutput(
            resource_type="Condition",
            resource_json={},
            is_valid=False,
            validation_errors=["Missing required field: code"],
        )
        assert not resource.is_valid
        assert len(resource.validation_errors) == 1
