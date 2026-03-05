"""
FHIR-shaped Pydantic schemas for the FastAPI layer.

These models approximate FHIR resource structure without requiring a full
HAPI FHIR server. They ensure CMS-0057-compatible request/response shapes.
"""

from __future__ import annotations

from datetime import datetime
from typing import Any

from pydantic import BaseModel, ConfigDict, Field

# ---------------------------------------------------------------------------
# Shared
# ---------------------------------------------------------------------------


class OperationOutcomeIssue(BaseModel):
    """Single issue within a FHIR OperationOutcome."""

    severity: str  # "error" | "warning" | "information"
    code: str  # "invalid" | "not-found" | "processing"
    details: str


class OperationOutcome(BaseModel):
    """FHIR OperationOutcome — returned on errors."""

    model_config = ConfigDict(populate_by_name=True)
    resource_type: str = Field(default="OperationOutcome", alias="resourceType")
    issues: list[OperationOutcomeIssue] = Field(default_factory=list)


# ---------------------------------------------------------------------------
# Prior Authorization
# ---------------------------------------------------------------------------


class PARequest(BaseModel):
    """
    Prior Authorization request — maps to FHIR Task (workflow pattern).

    Minimum required fields for CMS-0057 compliance:
    - clinical_text  : raw clinical note
    - payer_id       : target payer (must match a configured policy or CMS)
    - npi            : ordering provider NPI (optional, validated if provided)
    """

    clinical_text: str = Field(..., min_length=10, description="Raw clinical note text")
    payer_id: str = Field(
        ..., description="Payer identifier (e.g. 'medicare', 'commercial_generic')"
    )
    npi: str | None = Field(None, description="Ordering provider NPI (10 digits)")
    patient_id: str | None = Field(None, description="Opaque patient reference")
    stages: list[str] | None = Field(
        None,
        description="Optional subset of pipeline stages to run",
    )


class PAStageDetail(BaseModel):
    """Per-stage result summary."""

    agent: str
    success: bool
    errors: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)


class PAResponse(BaseModel):
    """
    Prior Authorization response — maps to FHIR Task output bundle.

    Includes CMS-0057 required fields:
    - pa_number      : authorization reference
    - pa_status      : approved | denied | pending | not_required
    - denial_reason  : specific reason if denied (CMS mandate)
    - turnaround_minutes : for SLA tracking
    """

    model_config = ConfigDict(populate_by_name=True)
    resource_type: str = Field(default="Task", alias="resourceType")
    pa_number: str | None = None
    pa_status: str
    denial_reason: str | None = None
    success: bool
    stages_completed: list[str]
    turnaround_minutes: float
    summary: str
    stage_details: dict[str, PAStageDetail] = Field(default_factory=dict)
    timestamp: datetime = Field(default_factory=datetime.utcnow)


# ---------------------------------------------------------------------------
# Coding Validation
# ---------------------------------------------------------------------------


class CodingValidateRequest(BaseModel):
    """CPT / ICD-10 coding validation request."""

    cpt_codes: list[str] = Field(..., min_length=1)
    icd10_codes: list[str] = Field(..., min_length=1)


class CodingValidateResponse(BaseModel):
    """Coding validation result with OperationOutcome-style issues."""

    valid: bool
    errors: list[str] = Field(default_factory=list)
    recommendations: list[str] = Field(default_factory=list)
    outcome: OperationOutcome = Field(default_factory=OperationOutcome)


# ---------------------------------------------------------------------------
# Compliance Metrics
# ---------------------------------------------------------------------------


class ComplianceMetricsResponse(BaseModel):
    """CMS-0057 compliance report response."""

    report_type: str
    generated_at: str
    total_encounters: int
    metrics: dict[str, Any] = Field(default_factory=dict)
