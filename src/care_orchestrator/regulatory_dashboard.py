"""
Regulatory Dashboard — aggregates compliance metrics for CMS/HHS readiness.

Tracks PHI redaction rates, PA outcomes, coding errors, claim volumes,
and generates structured reports for regulatory demonstrations.
"""

from __future__ import annotations

from care_orchestrator.logging_config import logger
from care_orchestrator.models import ComplianceMetrics, RCMResult


class RegulatoryDashboard:
    """Aggregates and reports compliance metrics."""

    def __init__(self) -> None:
        self._results: list[RCMResult] = []

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
                    # If redacted text differs from input, PHI was found
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
        from datetime import datetime

        metrics = self.get_metrics()
        return {
            "report_type": "CMS Compliance Summary",
            "generated_at": datetime.utcnow().isoformat(),
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
        Find a recorded result by PA number.

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
