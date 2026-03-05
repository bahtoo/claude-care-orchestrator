"""
CMS-0057 Patient Access FHIR API.

Implements the three Patient Access API endpoints mandated by CMS-0057
(Prior Authorization Rule, effective Jan 2027):

  GET /Patient/{patient_id}/$everything    — all resources for a patient
  GET /ExplanationOfBenefit               — claims data
  GET /Coverage                           — insurance coverage data

All endpoints return FHIR R4 Bundle resources (type: searchset).
Data is sourced from the PA records database. This is a compliant stub:
structure satisfies CMS-0057 data element requirements; a production
deployment would integrate with a claims adjudication system.

SMART Bearer token enforcement follows the same opt-in pattern as other
protected endpoints (SMART_AUTH_ENABLED=true).
"""

from __future__ import annotations

from typing import Any

from fastapi import APIRouter, Depends, Query
from fastapi.responses import JSONResponse

from care_orchestrator.fhir_bundle import make_bundle, make_coverage_entry, make_eob_entry
from care_orchestrator.logging_config import logger
from care_orchestrator.smart_auth import require_smart_token

patient_access_router = APIRouter(tags=["CMS-0057 Patient Access"])


# ---------------------------------------------------------------------------
# GET /Patient/{patient_id}/$everything
# ---------------------------------------------------------------------------


@patient_access_router.get(
    "/Patient/{patient_id}/$everything",
    summary="Patient $everything — all FHIR resources for a patient (CMS-0057)",
)
async def patient_everything(
    patient_id: str,
    _token: dict | None = Depends(require_smart_token),  # noqa: B008
) -> JSONResponse:
    """
    Returns a FHIR R4 searchset Bundle of all resources associated with the
    given patient_id, sourced from persisted PA records.

    Satisfies CMS-0057 § 422.119(b)(1)(i) patient data access requirement.
    """
    records = await _get_patient_records(patient_id)

    if not records:
        # Return an empty Bundle (not 404 — per FHIR spec)
        return JSONResponse(content=make_bundle("Patient", []))

    # Build a Patient stub entry
    patient_entry: dict[str, Any] = {
        "resourceType": "Patient",
        "id": patient_id,
        "meta": {"profile": ["http://hl7.org/fhir/us/core/StructureDefinition/us-core-patient"]},
    }

    # Bundle: Patient + all linked EOBs and Coverages
    all_entries: list[dict] = [patient_entry]
    for rec in records:
        all_entries.append(make_eob_entry(rec))
        all_entries.append(make_coverage_entry(rec))

    bundle = make_bundle("Patient", all_entries)
    logger.info(f"Patient $everything: patient={patient_id}, entries={len(all_entries)}")
    return JSONResponse(content=bundle)


# ---------------------------------------------------------------------------
# GET /ExplanationOfBenefit
# ---------------------------------------------------------------------------


@patient_access_router.get(
    "/ExplanationOfBenefit",
    summary="ExplanationOfBenefit search — claims data (CMS-0057)",
)
async def explanation_of_benefit(
    patient: str | None = Query(None, description="Filter by Patient/{id}"),
    _token: dict | None = Depends(require_smart_token),  # noqa: B008
) -> JSONResponse:
    """
    Returns a FHIR R4 searchset Bundle of ExplanationOfBenefit resources.

    Optionally filter by patient reference (e.g. patient=Patient/123).
    Satisfies CMS-0057 § 422.119(b)(1)(ii) EOB data access requirement.
    """
    patient_id = _extract_patient_id(patient)
    records = await _get_patient_records(patient_id) if patient_id else await _all_records()

    eobs = [make_eob_entry(r) for r in records]
    bundle = make_bundle("ExplanationOfBenefit", eobs)
    logger.info(f"EOB search: patient={patient_id}, count={len(eobs)}")
    return JSONResponse(content=bundle)


# ---------------------------------------------------------------------------
# GET /Coverage
# ---------------------------------------------------------------------------


@patient_access_router.get(
    "/Coverage",
    summary="Coverage search — insurance coverage data (CMS-0057)",
)
async def coverage(
    beneficiary: str | None = Query(None, description="Filter by Patient/{id}"),
    _token: dict | None = Depends(require_smart_token),  # noqa: B008
) -> JSONResponse:
    """
    Returns a FHIR R4 searchset Bundle of Coverage resources.

    Optionally filter by beneficiary reference (e.g. beneficiary=Patient/123).
    Satisfies CMS-0057 § 422.119(b)(1)(iii) coverage data access requirement.
    """
    patient_id = _extract_patient_id(beneficiary)
    records = await _get_patient_records(patient_id) if patient_id else await _all_records()

    coverages = [make_coverage_entry(r) for r in records]
    bundle = make_bundle("Coverage", coverages)
    logger.info(f"Coverage search: patient={patient_id}, count={len(coverages)}")
    return JSONResponse(content=bundle)


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------


def _extract_patient_id(reference: str | None) -> str | None:
    """Extract bare ID from a FHIR reference like 'Patient/123'."""
    if not reference:
        return None
    return reference.split("/")[-1] if "/" in reference else reference


async def _get_patient_records(patient_id: str | None) -> list[dict]:
    """Fetch all DB rows for a patient (by patient_id column)."""
    if not patient_id:
        return []

    from sqlalchemy import select

    from care_orchestrator.database import AsyncSessionLocal
    from care_orchestrator.models_db import PARecord

    async with AsyncSessionLocal() as session:
        stmt = select(PARecord).where(PARecord.patient_id == patient_id)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "pa_number": r.pa_number,
            "patient_id": r.patient_id,
            "pa_status": r.status,
            "cpt_codes": r.cpt_codes,
            "icd10_codes": r.icd10_codes,
            "turnaround_minutes": r.turnaround_minutes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "summary": r.summary,
            **r.result_json,
        }
        for r in rows
    ]


async def _all_records() -> list[dict]:
    """Fetch all DB rows (for unfiltered searches)."""
    from sqlalchemy import select

    from care_orchestrator.database import AsyncSessionLocal
    from care_orchestrator.models_db import PARecord

    async with AsyncSessionLocal() as session:
        stmt = select(PARecord)
        result = await session.execute(stmt)
        rows = result.scalars().all()

    return [
        {
            "pa_number": r.pa_number,
            "patient_id": r.patient_id,
            "pa_status": r.status,
            "cpt_codes": r.cpt_codes,
            "icd10_codes": r.icd10_codes,
            "turnaround_minutes": r.turnaround_minutes,
            "created_at": r.created_at.isoformat() if r.created_at else None,
            "summary": r.summary,
            **r.result_json,
        }
        for r in rows
    ]
