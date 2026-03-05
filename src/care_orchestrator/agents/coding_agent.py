"""
Coding Agent — validates CPT/ICD-10 code combinations.

Checks code pairing rules, modifier requirements, and bundling.
Runs the compliance engine to extract codes, then validates them.
"""

from __future__ import annotations

from care_orchestrator.agents import BaseAgent
from care_orchestrator.models import AgentResult, AgentTask, RCMStage
from care_orchestrator.phi_detector import phi_detector

# Known bundling conflicts: (primary_cpt, bundled_cpt)
BUNDLING_RULES: dict[str, list[str]] = {
    "99214": ["99213", "99212"],  # Can't bill higher + lower E&M same day
    "99215": ["99214", "99213", "99212"],
    "27447": ["27446"],  # Total knee includes partial
}

# CPT codes that commonly require modifiers
MODIFIER_REQUIREMENTS: dict[str, str] = {
    "99213": "-25 (if billed with procedure on same day)",
    "99214": "-25 (if billed with procedure on same day)",
}

# Valid CPT-ICD10 pairings (simplified — real systems use CCI edits)
VALID_PAIRINGS: dict[str, list[str]] = {
    "27447": ["M17.11", "M17.12", "M17.0", "M17.9"],
    "73221": ["M23.5", "M23.0", "M23.2", "S83.5", "M25.56"],
    "72148": ["M54.5", "M54.4", "M51.16", "M51.17", "G89.29"],
}


class CodingAgent(BaseAgent):
    """Validates CPT/ICD-10 code combinations and identifies issues."""

    def __init__(self) -> None:
        super().__init__(name="coding_agent", stage=RCMStage.CODING)

    def can_handle(self, task: AgentTask) -> bool:
        return task.task_type == RCMStage.CODING

    def _execute(self, task: AgentTask) -> AgentResult:
        clinical_text = task.input_data.get("clinical_text", "")
        cpt_codes = task.context.get("cpt_codes", [])
        icd10_codes = task.context.get("icd10_codes", [])

        # If no codes provided, run PHI detection to get redacted text
        if not cpt_codes:
            phi_result = phi_detector.detect(clinical_text)
            redacted = phi_result.redacted_text
        else:
            redacted = task.context.get("redacted_text", clinical_text)

        errors: list[str] = []
        recommendations: list[str] = []
        validated_cpt = list(cpt_codes)
        validated_icd = list(icd10_codes)

        # Check bundling conflicts
        for primary, conflicts in BUNDLING_RULES.items():
            if primary in cpt_codes:
                for conflict in conflicts:
                    if conflict in cpt_codes:
                        errors.append(
                            f"Bundling conflict: CPT {primary} cannot be billed with {conflict}"
                        )

        # Check modifier requirements
        has_procedure = any(c for c in cpt_codes if c not in ("99213", "99214", "99215"))
        if has_procedure:
            for code in cpt_codes:
                if str(code) in MODIFIER_REQUIREMENTS:
                    recommendations.append(
                        f"CPT {code} may need modifier {MODIFIER_REQUIREMENTS[str(code)]}"
                    )

        # Validate CPT-ICD10 pairings
        for cpt in cpt_codes:
            if str(cpt) in VALID_PAIRINGS:
                valid_dx = VALID_PAIRINGS[str(cpt)]
                matched = [dx for dx in icd10_codes if str(dx) in valid_dx]
                if not matched:
                    recommendations.append(
                        f"CPT {cpt}: no qualifying ICD-10 code found. "
                        f"Expected one of: {', '.join(valid_dx)}"
                    )

        has_errors = len(errors) > 0

        return AgentResult(
            agent_name=self.name,
            stage=self.stage,
            success=True,  # Coding always succeeds; errors are advisory
            output_data={
                "cpt_codes": validated_cpt,
                "icd10_codes": validated_icd,
                "redacted_text": redacted,
                "coding_errors": errors,
                "has_coding_issues": has_errors,
            },
            errors=errors,
            recommendations=recommendations,
        )
