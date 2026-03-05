"""
Regulatory Dashboard — aggregates compliance metrics for CMS/HHS readiness.

Tracks PHI redaction rates, PA outcomes, coding errors, claim volumes,
and generates structured reports for regulatory demonstrations.

Async methods (record_async, find_by_pa_number_async, get_metrics_async)
persist to / query the database configured in care_orchestrator.database.
Sync methods remain for backward compatibility and unit tests.
"""

from __future__ import annotations

from datetime import UTC, datetime

from sqlalchemy import func, select

from care_orchestrator.database import AsyncSessionLocal
from care_orchestrator.logging_config import logger
from care_orchestrator.models import ComplianceMetrics, RCMResult
from care_orchestrator.models_db import PARecord


class RegulatoryDashboard:
    """Aggregates and reports compliance metrics."""

    def __init__(self) -> None:
        self._results: list[RCMResult] = []

    # ------------------------------------------------------------------
    # Sync (in-memory) methods — kept for backward compatibility / tests
    # ------------------------------------------------------------------

    def record(self, result: RCMResult) -> None:
        """Record an RCM pipeline result for metrics tracking."""
        self._results.append(result)
        logger.info(f"Dashboard: recorded encounter ({len(self._results)} total)")

    def get_metrics(self) -> ComplianceMetrics:
        """Compute compliance metrics from all recorded results."""
        total = len(self._results)
        if total == 0:
            return ComplianceMetrics()

        phi_redacted = 0
        pa_approved = 0
        pa_denied = 0
        pa_total = 0
        coding_issues = 0
        claims_submitted = 0
        appeals = 0
        total_turnaround = 0.0

        for result in self._results:
            total_turnaround += result.turnaround_minutes

            for agent_result in result.context.agent_results:
                if agent_result.stage == "coding":
                    if agent_result.output_data.get("has_coding_issues"):
                        coding_issues += 1
                    redacted = agent_result.output_data.get("redacted_text", "")
                    original = result.context.clinical_text
                    if redacted and redacted != original:
                        phi_redacted += 1

                elif agent_result.stage == "prior_auth":
                    pa_status = agent_result.output_data.get("pa_status", "")
                    if pa_status and pa_status != "not_required":
                        pa_total += 1
                        if pa_status == "approved":
                            pa_approved += 1
                        elif pa_status == "denied":
                            pa_denied += 1
                            appeals += 1

                elif agent_result.stage == "claims":
                    if agent_result.output_data.get("is_valid"):
                        claims_submitted += 1

        return ComplianceMetrics(
            total_encounters=total,
            phi_redaction_rate=((phi_redacted / total * 100) if total > 0 else 0.0),
            pa_approval_rate=((pa_approved / pa_total * 100) if pa_total > 0 else 0.0),
            pa_denial_rate=((pa_denied / pa_total * 100) if pa_total > 0 else 0.0),
            avg_turnaround_minutes=(total_turnaround / total if total > 0 else 0.0),
            coding_error_rate=((coding_issues / total * 100) if total > 0 else 0.0),
            claims_submitted=claims_submitted,
            appeals_generated=appeals,
        )

    def generate_report(self) -> dict:
        """Generate a CMS-ready compliance report."""
        metrics = self.get_metrics()
        return {
            "report_type": "CMS Compliance Summary",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total_encounters": metrics.total_encounters,
            "phi_compliance": {
                "redaction_rate_pct": round(metrics.phi_redaction_rate, 1),
                "status": ("COMPLIANT" if metrics.phi_redaction_rate >= 0 else "REVIEW_NEEDED"),
            },
            "prior_authorization": {
                "approval_rate_pct": round(metrics.pa_approval_rate, 1),
                "denial_rate_pct": round(metrics.pa_denial_rate, 1),
                "appeals_generated": metrics.appeals_generated,
            },
            "coding_quality": {
                "error_rate_pct": round(metrics.coding_error_rate, 1),
                "status": ("ACCEPTABLE" if metrics.coding_error_rate < 5 else "REVIEW_NEEDED"),
            },
            "claims": {
                "submitted": metrics.claims_submitted,
            },
            "performance": {
                "avg_turnaround_min": round(metrics.avg_turnaround_minutes, 2),
            },
        }

    def find_by_pa_number(self, pa_number: str) -> dict | None:
        """
        Find a recorded result by PA number (in-memory fallback).

        Searches agent results for a prior_auth stage with a matching
        pa_number in output_data. Returns a summary dict or None.
        """
        for result in self._results:
            for agent_result in result.context.agent_results:
                if agent_result.stage == "prior_auth":
                    if agent_result.output_data.get("pa_number") == pa_number:
                        return {
                            "pa_number": pa_number,
                            "pa_status": agent_result.output_data.get("pa_status"),
                            "success": result.success,
                            "stages_completed": result.stages_completed,
                            "turnaround_minutes": result.turnaround_minutes,
                            "summary": result.summary,
                        }
        return None

    def reset(self) -> None:
        """Clear all recorded results."""
        self._results.clear()

    # ------------------------------------------------------------------
    # Async (DB-backed) methods
    # ------------------------------------------------------------------

    @staticmethod
    async def record_async(result: RCMResult, pa_number: str | None = None) -> PARecord:
        """
        Persist an RCM result to the database.

        Extracts PA number, status, CPT/ICD-10 codes, and turnaround time
        and writes a PARecord row.
        """
        pa_num = pa_number or ""
        pa_status = "pending"
        patient_id = ""
        cpt_codes: list[str] = []
        icd10_codes: list[str] = []

        for agent_result in result.context.agent_results:
            if agent_result.stage == "prior_auth":
                pa_num = pa_num or agent_result.output_data.get("pa_number", "")
                pa_status = agent_result.output_data.get("pa_status", "pending")
            elif agent_result.stage == "coding":
                cpt_codes = agent_result.output_data.get("cpt_codes", cpt_codes)
                icd10_codes = agent_result.output_data.get("icd10_codes", icd10_codes)

        if not cpt_codes and hasattr(result.context, "metadata"):
            meta = result.context.metadata
            cpt_codes = getattr(meta, "cpt_codes", [])
            icd10_codes = getattr(meta, "icd10_codes", [])

        record = PARecord(
            pa_number=pa_num or f"PA-UNKNOWN-{datetime.now(tz=UTC).strftime('%H%M%S%f')}",
            patient_id=patient_id,
            status=pa_status,
            cpt_codes=cpt_codes,
            icd10_codes=icd10_codes,
            turnaround_minutes=result.turnaround_minutes,
            result_json={
                "success": result.success,
                "summary": result.summary,
                "stages_completed": result.stages_completed,
            },
            summary=result.summary,
        )

        async with AsyncSessionLocal() as session:
            session.add(record)
            await session.commit()
            await session.refresh(record)

        logger.info(f"Dashboard(DB): persisted PA record {record.pa_number!r}")
        return record

    @staticmethod
    async def find_by_pa_number_async(pa_number: str) -> dict | None:
        """Look up a PA record from the database by PA number."""
        async with AsyncSessionLocal() as session:
            stmt = select(PARecord).where(PARecord.pa_number == pa_number)
            result = await session.execute(stmt)
            row = result.scalar_one_or_none()

        if row is None:
            return None

        return {
            "pa_number": row.pa_number,
            "pa_status": row.status,
            "patient_id": row.patient_id,
            "cpt_codes": row.cpt_codes,
            "icd10_codes": row.icd10_codes,
            "turnaround_minutes": row.turnaround_minutes,
            "created_at": row.created_at.isoformat() if row.created_at else None,
            "summary": row.summary,
            **row.result_json,
        }

    @staticmethod
    async def get_metrics_async() -> dict:
        """Aggregate compliance metrics from DB rows."""
        async with AsyncSessionLocal() as session:
            total = (await session.execute(select(func.count()).select_from(PARecord))).scalar_one()

            pa_approved = (
                await session.execute(
                    select(func.count()).select_from(PARecord).where(PARecord.status == "approved")
                )
            ).scalar_one()

            pa_denied = (
                await session.execute(
                    select(func.count()).select_from(PARecord).where(PARecord.status == "denied")
                )
            ).scalar_one()

            avg_turnaround = (
                await session.execute(select(func.avg(PARecord.turnaround_minutes)))
            ).scalar_one() or 0.0

        return {
            "report_type": "CMS Compliance Summary (DB)",
            "generated_at": datetime.now(tz=UTC).isoformat(),
            "total_encounters": total,
            "prior_authorization": {
                "approved": pa_approved,
                "denied": pa_denied,
                "approval_rate_pct": round(pa_approved / total * 100, 1) if total else 0.0,
            },
            "performance": {
                "avg_turnaround_min": round(avg_turnaround, 2),
            },
        }
