"""
Pydantic models for care-orchestrator data structures.

Defines the core domain models used across the compliance engine,
PHI detector, and FHIR mapper.
"""

from enum import StrEnum

from pydantic import BaseModel, Field

# ---------------------------------------------------------------------------
# PHI Detection Models
# ---------------------------------------------------------------------------


class PHIType(StrEnum):
    """Categories of Protected Health Information."""

    SSN = "SSN"
    PHONE = "PHONE"
    DOB = "DATE_OF_BIRTH"
    EMAIL = "EMAIL"
    NAME = "NAME"
    MRN = "MEDICAL_RECORD_NUMBER"
    ADDRESS = "ADDRESS"


class PHIEntity(BaseModel):
    """A single detected PHI entity in the text."""

    value: str = Field(description="The original PHI value found in text")
    phi_type: PHIType = Field(description="Category of PHI")
    start: int = Field(description="Start character position in original text")
    end: int = Field(description="End character position in original text")


class PHIDetectionResult(BaseModel):
    """Result of the deterministic PHI detection pass."""

    is_clean: bool = Field(description="True if no PHI was detected")
    entities: list[PHIEntity] = Field(default_factory=list, description="All detected PHI entities")
    redacted_text: str = Field(description="Text with PHI replaced by [REDACTED_*] tokens")
    entity_count: int = Field(default=0, description="Total number of PHI entities found")


# ---------------------------------------------------------------------------
# Clinical Note Models
# ---------------------------------------------------------------------------


class ClinicalNote(BaseModel):
    """Input model representing a raw clinical note."""

    text: str = Field(description="Raw clinical text to process")
    source: str = Field(default="unknown", description="Source system (e.g., 'epic', 'cerner')")
    note_type: str = Field(
        default="general", description="Note type (e.g., 'progress', 'discharge')"
    )


# ---------------------------------------------------------------------------
# Compliance / Audit Models
# ---------------------------------------------------------------------------


class AdminMetadata(BaseModel):
    """Administrative metadata extracted from clinical text."""

    cpt_codes: list[str] = Field(default_factory=list, description="CPT procedure codes found")
    icd10_codes: list[str] = Field(default_factory=list, description="ICD-10 diagnosis codes found")
    workflow_type: str = Field(
        default="unknown",
        description="Detected workflow type (prior_auth, appeal, coding)",
    )


class AuditReport(BaseModel):
    """Full compliance audit report from the two-pass engine."""

    phi_status: str = Field(description="CLEAN or REDACTED")
    phi_detection: PHIDetectionResult = Field(description="Results from deterministic PHI scan")
    redacted_text: str = Field(description="Final redacted text after both passes")
    admin_metadata: AdminMetadata = Field(description="Extracted administrative metadata")
    raw_llm_response: str = Field(default="", description="Raw response from the LLM audit pass")


# ---------------------------------------------------------------------------
# FHIR Output Models
# ---------------------------------------------------------------------------


class FHIRResourceOutput(BaseModel):
    """A single generated FHIR R4 resource."""

    resource_type: str = Field(description="FHIR resource type (Patient, Condition, etc.)")
    resource_json: dict = Field(description="The FHIR R4 resource as a dictionary")
    is_valid: bool = Field(default=True, description="Whether the resource passed FHIR validation")
    validation_errors: list[str] = Field(
        default_factory=list,
        description="Validation error messages if any",
    )


class FHIROutput(BaseModel):
    """Collection of generated FHIR R4 resources from a clinical note."""

    resources: list[FHIRResourceOutput] = Field(
        default_factory=list,
        description="Generated FHIR R4 resources",
    )
    source_text_redacted: str = Field(description="The redacted source text used for generation")
    total_resources: int = Field(default=0, description="Total number of resources generated")
