"""
FastAPI FHIR-shaped REST API for claude-care-orchestrator.

Exposes the RCM pipeline, coding validation, and compliance metrics
via HTTP endpoints designed for CMS-0057 compliance (2026/2027 mandates).

Start with:
    uvicorn care_orchestrator.app:app --reload --port 8000
"""

from __future__ import annotations

import os
from collections.abc import AsyncGenerator
from contextlib import asynccontextmanager
from typing import Any

from fastapi import Depends, FastAPI, HTTPException, Request, status
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse

from care_orchestrator.agents.coding_agent import CodingAgent
from care_orchestrator.database import create_tables
from care_orchestrator.fhir_schemas import (
    CodingValidateRequest,
    CodingValidateResponse,
    ComplianceMetricsResponse,
    FHIRValidateRequest,
    FHIRValidateResponse,
    OperationOutcome,
    OperationOutcomeIssue,
    PARequest,
    PAResponse,
    PAStageDetail,
)
from care_orchestrator.fhir_validator import fhir_validator
from care_orchestrator.logging_config import logger
from care_orchestrator.models import AgentTask, RCMStage
from care_orchestrator.patient_access import patient_access_router
from care_orchestrator.rcm_orchestrator import RCMOrchestrator
from care_orchestrator.regulatory_dashboard import RegulatoryDashboard
from care_orchestrator.smart_auth import auth_router, require_smart_token

# ---------------------------------------------------------------------------
# Application state
# ---------------------------------------------------------------------------

_rcm: RCMOrchestrator | None = None
_dashboard: RegulatoryDashboard | None = None
_coding_agent: CodingAgent | None = None


def _get_rcm() -> RCMOrchestrator:
    global _rcm
    if _rcm is None:
        _rcm = RCMOrchestrator(
            api_key=os.getenv("ANTHROPIC_API_KEY"),
            model=os.getenv("ANTHROPIC_MODEL", "claude-opus-4-5"),
            policies_dir=os.getenv("POLICIES_DIR", "config/policies"),
        )
    return _rcm


def _get_dashboard() -> RegulatoryDashboard:
    global _dashboard
    if _dashboard is None:
        _dashboard = RegulatoryDashboard()
    return _dashboard


def _get_coding_agent() -> CodingAgent:
    global _coding_agent
    if _coding_agent is None:
        _coding_agent = CodingAgent()
    return _coding_agent


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncGenerator[None, None]:  # noqa: ANN001
    """Warm up singletons and initialise DB tables on startup."""
    logger.info("care-orchestrator API starting up")
    await create_tables()
    _get_rcm()
    _get_dashboard()
    _get_coding_agent()
    yield
    logger.info("care-orchestrator API shutting down")


# ---------------------------------------------------------------------------
# App
# ---------------------------------------------------------------------------

app = FastAPI(
    title="Care Orchestrator API",
    description=(
        "AI-native healthcare Revenue Cycle Management API. "
        "End-to-end prior authorization, coding validation, "
        "and CMS-0057 compliance metrics."
    ),
    version="0.6.0",
    contact={"name": "Bahtiyar Aytac"},
    license_info={"name": "MIT"},
    lifespan=lifespan,
)

app.add_middleware(
    CORSMiddleware,
    allow_origins=["*"],
    allow_methods=["GET", "POST"],
    allow_headers=["*"],
)

# Register SMART on FHIR auth router (/.well-known/*, /auth/*)
app.include_router(auth_router)

# Register CMS-0057 Patient Access router (/Patient, /ExplanationOfBenefit, /Coverage)
app.include_router(patient_access_router)


# ---------------------------------------------------------------------------
# Error handlers
# ---------------------------------------------------------------------------


@app.exception_handler(Exception)
async def global_exception_handler(request: Request, exc: Exception) -> JSONResponse:
    logger.error(f"Unhandled error on {request.url.path}: {exc}")
    outcome = OperationOutcome(
        issues=[
            OperationOutcomeIssue(
                severity="error",
                code="processing",
                details=str(exc),
            )
        ]
    )
    return JSONResponse(
        status_code=status.HTTP_500_INTERNAL_SERVER_ERROR,
        content=outcome.model_dump(),
    )


# ---------------------------------------------------------------------------
# Health
# ---------------------------------------------------------------------------


@app.get("/health", tags=["System"])
async def health() -> dict[str, str]:
    """Liveness probe."""
    return {"status": "ok", "version": "0.4.0"}


# ---------------------------------------------------------------------------
# POST /prior-authorization
# ---------------------------------------------------------------------------


@app.post(
    "/prior-authorization",
    response_model=PAResponse,
    status_code=status.HTTP_201_CREATED,
    tags=["Prior Authorization"],
    summary="Run the full RCM pipeline for a prior authorization request",
)
async def submit_prior_auth(payload: PARequest) -> PAResponse:
    """
    Submit a prior authorization request.

    Runs: PHI audit → Coding validation → Eligibility check →
          Prior Auth decision → CMS-1500 claim assembly.

    Returns a FHIR Task-shaped response with PA number, status, and
    per-stage details required by CMS-0057.
    """
    rcm = _get_rcm()
    dashboard = _get_dashboard()

    stages = payload.stages or [
        RCMStage.CODING,
        RCMStage.ELIGIBILITY,
        RCMStage.PRIOR_AUTH,
        RCMStage.CLAIMS,
    ]

    result = rcm.run(
        clinical_text=payload.clinical_text,
        payer_id=payload.payer_id,
        stages=stages,
    )

    await RegulatoryDashboard.record_async(result)

    # Extract PA details from agent results
    pa_number: str | None = None
    pa_status = "pending"
    denial_reason: str | None = None

    stage_details: dict[str, PAStageDetail] = {}
    for ar in result.context.agent_results:
        stage_details[ar.stage] = PAStageDetail(
            agent=ar.agent_name,
            success=ar.success,
            errors=ar.errors,
            recommendations=ar.recommendations,
        )
        if ar.stage == RCMStage.PRIOR_AUTH:
            pa_number = ar.output_data.get("pa_number")
            pa_status = ar.output_data.get("pa_status", "pending")
        if ar.stage == RCMStage.CLAIMS and not ar.success:
            denial_reason = "; ".join(ar.errors) if ar.errors else None

    return PAResponse(
        pa_number=pa_number,
        pa_status=pa_status,
        denial_reason=denial_reason,
        success=result.success,
        stages_completed=result.stages_completed,
        turnaround_minutes=result.turnaround_minutes,
        summary=result.summary,
        stage_details=stage_details,
    )


# ---------------------------------------------------------------------------
# GET /prior-authorization/{pa_number}
# ---------------------------------------------------------------------------


@app.get(
    "/prior-authorization/{pa_number}",
    tags=["Prior Authorization"],
    summary="Look up a prior authorization by PA number",
)
async def get_prior_auth(pa_number: str) -> dict[str, Any]:
    """
    Status lookup by PA number.

    Returns the last recorded result for this PA number from
    the in-memory dashboard. Persisted storage would be a Phase 5
    addition (PostgreSQL / DynamoDB).
    """
    match = await RegulatoryDashboard.find_by_pa_number_async(pa_number)
    if match is None:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail=f"PA number '{pa_number}' not found",
        )
    return match


# ---------------------------------------------------------------------------
# POST /coding/validate
# ---------------------------------------------------------------------------


@app.post(
    "/coding/validate",
    response_model=CodingValidateResponse,
    tags=["Coding"],
    summary="Validate CPT / ICD-10 code combinations",
)
async def validate_coding(payload: CodingValidateRequest) -> CodingValidateResponse:
    """
    Validate CPT and ICD-10 code pairings.

    Checks bundling conflicts, modifier requirements, and qualifying
    diagnosis pairings without running the full RCM pipeline.
    """
    agent = _get_coding_agent()
    task = AgentTask(
        task_type="coding",
        input_data={"clinical_text": ""},
        context={
            "cpt_codes": payload.cpt_codes,
            "icd10_codes": payload.icd10_codes,
        },
    )
    result = agent.process(task)

    issues = [
        OperationOutcomeIssue(severity="error", code="invalid", details=e) for e in result.errors
    ]

    return CodingValidateResponse(
        valid=result.success and not result.errors,
        errors=result.errors,
        recommendations=result.recommendations,
        outcome=OperationOutcome(issues=issues),
    )


# ---------------------------------------------------------------------------
# GET /compliance/metrics
# ---------------------------------------------------------------------------


@app.get(
    "/compliance/metrics",
    response_model=ComplianceMetricsResponse,
    tags=["Compliance"],
    summary="Get CMS-0057 compliance metrics report",
)
async def get_compliance_metrics() -> ComplianceMetricsResponse:
    """
    Generate a CMS-0057 compliance report.

    Aggregates PA turnaround times, denial rates, PHI redaction coverage,
    coding error rates, and claims volume for regulatory reporting.

    First annual public report due: March 31, 2026 (CMS mandate).
    """
    report = await RegulatoryDashboard.get_metrics_async()

    return ComplianceMetricsResponse(
        report_type=report.get("report_type", "CMS Compliance Summary"),
        generated_at=report.get("generated_at", ""),
        total_encounters=report.get("total_encounters", 0),
        metrics={
            k: v
            for k, v in report.items()
            if k not in ("report_type", "generated_at", "total_encounters")
        },
    )


# ---------------------------------------------------------------------------
# POST /fhir/validate
# ---------------------------------------------------------------------------


@app.post(
    "/fhir/validate",
    response_model=FHIRValidateResponse,
    tags=["FHIR"],
    summary="Validate a FHIR resource against its US Core profile",
)
async def validate_fhir_resource(
    payload: FHIRValidateRequest,
    _token: dict | None = Depends(require_smart_token),  # noqa: B008
) -> FHIRValidateResponse:
    """
    Validate a FHIR R4 resource against US Core profile rules.

    Supported resource types: Patient, Condition, ServiceRequest, Procedure.
    Returns a FHIR OperationOutcome-shaped response with errors and warnings.
    """
    result = fhir_validator.validate(payload.resource_type, payload.resource)

    issues = [
        OperationOutcomeIssue(severity="error", code="invalid", details=e) for e in result.errors
    ] + [
        OperationOutcomeIssue(severity="warning", code="informational", details=w)
        for w in result.warnings
    ]

    return FHIRValidateResponse(
        valid=result.valid,
        profile=result.profile,
        errors=result.errors,
        warnings=result.warnings,
        outcome=OperationOutcome(issues=issues),
    )
