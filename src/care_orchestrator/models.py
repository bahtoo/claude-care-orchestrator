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


# ---------------------------------------------------------------------------
# Payer Policy Models (Phase 2)
# ---------------------------------------------------------------------------


class CoverageCriteria(BaseModel):
    """Criteria a payer requires to approve a procedure."""

    required_diagnoses: list[str] = Field(
        default_factory=list,
        description="ICD-10 codes that qualify for coverage",
    )
    required_documentation: list[str] = Field(
        default_factory=list,
        description="Required clinical documentation (e.g., 'failed conservative treatment')",
    )
    age_restrictions: str = Field(
        default="none",
        description="Age-based restrictions (e.g., '18+', '40-75')",
    )
    review_timeline_hours: int = Field(
        default=72,
        description="Payer's standard review timeline in hours",
    )


class PriorAuthRequirement(BaseModel):
    """Whether a specific CPT code requires prior authorization."""

    cpt_code: str = Field(description="The CPT procedure code")
    requires_auth: bool = Field(description="Whether PA is required")
    criteria: CoverageCriteria | None = Field(
        default=None, description="Coverage criteria if PA is required"
    )
    auto_approve_diagnoses: list[str] = Field(
        default_factory=list,
        description="ICD-10 codes that qualify for automatic approval",
    )


class PayerPolicy(BaseModel):
    """A payer's prior authorization policy configuration."""

    payer_id: str = Field(description="Unique payer identifier")
    payer_name: str = Field(description="Display name of the payer")
    policy_version: str = Field(default="1.0", description="Policy version")
    prior_auth_rules: list[PriorAuthRequirement] = Field(
        default_factory=list,
        description="PA requirements by CPT code",
    )
    default_requires_auth: bool = Field(
        default=False,
        description="Default PA requirement for unlisted CPT codes",
    )


# ---------------------------------------------------------------------------
# Medical Necessity Models (Phase 2)
# ---------------------------------------------------------------------------


class NecessityDetermination(StrEnum):
    """Possible outcomes of a medical necessity evaluation."""

    APPROVED = "approved"
    DENIED = "denied"
    NEEDS_INFO = "needs_additional_info"


class NecessityDecision(BaseModel):
    """Result of a medical necessity evaluation."""

    determination: NecessityDetermination = Field(
        description="Outcome: approved, denied, or needs_additional_info"
    )
    rationale: str = Field(description="Clinical rationale for the decision")
    criteria_met: list[str] = Field(
        default_factory=list,
        description="Which payer criteria were satisfied",
    )
    criteria_unmet: list[str] = Field(
        default_factory=list,
        description="Which payer criteria were NOT satisfied",
    )
    missing_documentation: list[str] = Field(
        default_factory=list,
        description="Documentation needed to change the determination",
    )
    confidence_score: float = Field(
        default=0.0,
        description="0.0–1.0 confidence in the determination",
    )


# ---------------------------------------------------------------------------
# Prior Auth Models (Phase 2)
# ---------------------------------------------------------------------------


class PriorAuthStatus(StrEnum):
    """Status of a prior authorization request."""

    NOT_REQUIRED = "not_required"
    APPROVED = "approved"
    DENIED = "denied"
    PENDING_INFO = "pending_additional_info"
    SUBMITTED = "submitted"


class PriorAuthRequest(BaseModel):
    """A generated prior authorization request document."""

    payer_id: str = Field(description="Target payer identifier")
    procedure_code: str = Field(description="Primary CPT code for the procedure")
    diagnosis_codes: list[str] = Field(default_factory=list, description="Supporting ICD-10 codes")
    clinical_summary: str = Field(description="Redacted clinical summary supporting the request")
    necessity_decision: NecessityDecision = Field(description="Medical necessity evaluation result")
    fhir_resources: FHIROutput | None = Field(default=None, description="Generated FHIR resources")


class PriorAuthResult(BaseModel):
    """Full result of the prior authorization workflow."""

    status: PriorAuthStatus = Field(description="Overall PA status")
    request: PriorAuthRequest | None = Field(
        default=None, description="Generated PA request (if PA was required)"
    )
    turnaround_estimate_minutes: float = Field(
        default=0.0,
        description="Estimated processing time in minutes",
    )
    audit_report: AuditReport | None = Field(
        default=None, description="Underlying compliance audit"
    )
    summary: str = Field(default="", description="Human-readable summary")


# ---------------------------------------------------------------------------
# Appeal Letter Models (Phase 2)
# ---------------------------------------------------------------------------


class AppealType(StrEnum):
    """Types of prior authorization appeals."""

    INITIAL = "initial_appeal"
    PEER_TO_PEER = "peer_to_peer_review"
    EXTERNAL = "external_review"


class AppealLetter(BaseModel):
    """A generated appeal letter for a denied prior authorization."""

    appeal_type: AppealType = Field(description="Type of appeal")
    letter_content: str = Field(description="Full appeal letter text (markdown)")
    clinical_justification: str = Field(description="Key clinical arguments supporting the appeal")
    policy_citations: list[str] = Field(
        default_factory=list,
        description="Payer policy sections cited in the appeal",
    )
    denial_reason: str = Field(description="Original reason for denial")
    procedure_code: str = Field(description="CPT code being appealed")


# ---------------------------------------------------------------------------
# Agent Framework Models (Phase 3)
# ---------------------------------------------------------------------------


class RCMStage(StrEnum):
    """Stages in the Revenue Cycle Management pipeline."""

    CODING = "coding"
    ELIGIBILITY = "eligibility"
    PRIOR_AUTH = "prior_auth"
    CLAIMS = "claims"


class AgentTask(BaseModel):
    """A task dispatched to an agent."""

    task_type: str = Field(description="Type of task (maps to RCMStage)")
    input_data: dict = Field(default_factory=dict, description="Input data for the agent")
    context: dict = Field(
        default_factory=dict,
        description="Shared context from previous agents",
    )


class AgentResult(BaseModel):
    """Result produced by an agent."""

    agent_name: str = Field(description="Name of the agent that produced this")
    stage: str = Field(description="RCM stage this result belongs to")
    success: bool = Field(description="Whether the agent completed successfully")
    output_data: dict = Field(default_factory=dict, description="Agent's output data")
    errors: list[str] = Field(default_factory=list, description="Error messages if any")
    recommendations: list[str] = Field(
        default_factory=list,
        description="Agent recommendations for downstream stages",
    )


# ---------------------------------------------------------------------------
# RCM Pipeline Models (Phase 3)
# ---------------------------------------------------------------------------


class ClaimLine(BaseModel):
    """A single line item on a healthcare claim."""

    cpt_code: str = Field(description="CPT procedure code")
    icd10_codes: list[str] = Field(default_factory=list, description="Linked diagnosis codes")
    units: int = Field(default=1, description="Number of units")
    modifiers: list[str] = Field(default_factory=list, description="CPT modifiers (e.g., -25, -59)")
    charge_amount: float = Field(default=0.0, description="Charge amount in USD")


class ClaimData(BaseModel):
    """CMS-1500 / UB-04 claim data structure."""

    claim_type: str = Field(
        default="professional",
        description="professional (CMS-1500) or institutional (UB-04)",
    )
    payer_id: str = Field(description="Target payer identifier")
    patient_id: str = Field(default="REDACTED", description="Redacted patient ID")
    lines: list[ClaimLine] = Field(default_factory=list, description="Claim line items")
    total_charges: float = Field(default=0.0, description="Total charge amount")
    authorization_number: str = Field(default="", description="Prior auth number if applicable")
    is_valid: bool = Field(default=True, description="Whether validation passed")
    validation_errors: list[str] = Field(
        default_factory=list, description="Validation error messages"
    )


class RCMContext(BaseModel):
    """Context passed through the RCM pipeline between agents."""

    clinical_text: str = Field(description="Original clinical note text")
    payer_id: str = Field(description="Target payer for the encounter")
    redacted_text: str = Field(default="", description="PHI-redacted text")
    cpt_codes: list[str] = Field(default_factory=list, description="Validated CPT codes")
    icd10_codes: list[str] = Field(default_factory=list, description="Validated ICD-10 codes")
    is_eligible: bool = Field(default=False, description="Patient eligibility status")
    pa_status: str = Field(default="", description="Prior auth status")
    pa_number: str = Field(default="", description="Prior auth reference number")
    claim: ClaimData | None = Field(default=None, description="Generated claim data")
    agent_results: list[AgentResult] = Field(
        default_factory=list,
        description="Results from each agent in the pipeline",
    )


class RCMResult(BaseModel):
    """Full result of the RCM pipeline."""

    success: bool = Field(description="Whether the pipeline completed")
    stages_completed: list[str] = Field(default_factory=list, description="RCM stages that ran")
    context: RCMContext = Field(description="Final pipeline context")
    summary: str = Field(default="", description="Human-readable summary")
    turnaround_minutes: float = Field(default=0.0, description="Total processing time")


# ---------------------------------------------------------------------------
# Regulatory Dashboard Models (Phase 3)
# ---------------------------------------------------------------------------


class ComplianceMetrics(BaseModel):
    """Aggregated compliance metrics for regulatory reporting."""

    total_encounters: int = Field(default=0, description="Total encounters processed")
    phi_redaction_rate: float = Field(
        default=0.0, description="Pct of encounters with PHI redacted"
    )
    pa_approval_rate: float = Field(default=0.0, description="Pct of PAs approved")
    pa_denial_rate: float = Field(default=0.0, description="Pct of PAs denied")
    avg_turnaround_minutes: float = Field(default=0.0, description="Average processing time")
    coding_error_rate: float = Field(
        default=0.0, description="Pct of encounters with coding issues"
    )
    claims_submitted: int = Field(default=0, description="Total claims generated")
    appeals_generated: int = Field(default=0, description="Total appeal letters generated")
