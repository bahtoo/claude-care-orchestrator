"""
FHIR US Core R4 Profile Validator.

Validates FHIR R4 resources against US Core profile rules without
requiring a running HAPI FHIR server. Uses configurable rule checks
covering the must-support elements defined in:
  - US Core Patient Profile (v6.1.0)
  - US Core Condition Profile (v6.1.0)
  - US Core ServiceRequest Profile (v6.1.0)

Usage:
    validator = FHIRValidator()
    result = validator.validate("Patient", resource_dict)
    if not result.valid:
        print(result.errors)
"""

from __future__ import annotations

from dataclasses import dataclass, field

from care_orchestrator.logging_config import logger

# ---------------------------------------------------------------------------
# Known compliant code systems
# ---------------------------------------------------------------------------

_CLINICAL_STATUS_SYSTEMS = {
    "http://terminology.hl7.org/CodeSystem/condition-clinical",
}

_ICD10_SYSTEMS = {
    "http://hl7.org/fhir/sid/icd-10-cm",
    "http://hl7.org/fhir/sid/icd-10",
}

_SNOMED_SYSTEMS = {
    "http://snomed.info/sct",
}

_CPT_SYSTEMS = {
    "http://www.ama-assn.org/go/cpt",
    "http://terminology.hl7.org/CodeSystem/CPT",
}

_LANGUAGE_SYSTEMS = {
    "urn:ietf:bcp:47",
}

# Supported resource types for profile validation
SUPPORTED_PROFILES = frozenset({"Patient", "Condition", "ServiceRequest", "Procedure"})


# ---------------------------------------------------------------------------
# Result model
# ---------------------------------------------------------------------------


@dataclass
class ValidationResult:
    """
    Result of a US Core profile validation.

    Attributes:
        valid:    True if no errors (warnings are allowed).
        profile:  The profile name that was checked.
        errors:   Hard violations (resource would fail conformance testing).
        warnings: Soft violations (should-support elements that are missing).
    """

    valid: bool
    profile: str
    errors: list[str] = field(default_factory=list)
    warnings: list[str] = field(default_factory=list)

    def to_dict(self) -> dict:  # noqa: ANN401
        """Serialise for HTTP response / OperationOutcome mapping."""
        return {
            "valid": self.valid,
            "profile": self.profile,
            "errors": self.errors,
            "warnings": self.warnings,
        }


# ---------------------------------------------------------------------------
# Validator
# ---------------------------------------------------------------------------


class FHIRValidator:
    """
    Rule-based FHIR US Core profile validator.

    Checks must-support elements for Patient, Condition, and ServiceRequest.
    Falls back to a generic resource-type check for unsupported profiles.
    """

    def validate(self, resource_type: str, resource: dict) -> ValidationResult:  # noqa: ANN401
        """
        Validate a FHIR resource against its US Core profile.

        Args:
            resource_type: FHIR resource type string (e.g. "Patient").
            resource:      Parsed resource dict (from model_dump or raw JSON).

        Returns:
            ValidationResult with valid flag, errors, and warnings.
        """
        if resource_type not in SUPPORTED_PROFILES:
            return ValidationResult(
                valid=False,
                profile=resource_type,
                errors=[
                    f"Profile validation not supported for resource type '{resource_type}'. "
                    f"Supported: {sorted(SUPPORTED_PROFILES)}"
                ],
            )

        from collections.abc import Callable

        dispatch: dict[str, Callable[[dict], ValidationResult]] = {
            "Patient": self._validate_patient,
            "Condition": self._validate_condition,
            "ServiceRequest": self._validate_service_request,
            "Procedure": self._validate_procedure,
        }

        result = dispatch[resource_type](resource)
        logger.info(
            f"FHIR validation [{resource_type}]: "
            f"valid={result.valid}, "
            f"errors={len(result.errors)}, "
            f"warnings={len(result.warnings)}"
        )
        return result

    # ------------------------------------------------------------------
    # Private validators
    # ------------------------------------------------------------------

    def _validate_patient(self, resource: dict) -> ValidationResult:  # noqa: ANN401
        """
        US Core Patient must-support elements:
          - identifier (≥1)
          - name.family + name.given
          - gender
          - birthDate (or absent-reason extension)
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Must-support: identifier
        identifiers = resource.get("identifier", [])
        if not identifiers:
            errors.append(
                "US Core Patient: 'identifier' is required (must-support). "
                "Add at least one identifier (e.g. MR number, SSN last 4)."
            )

        # Must-support: name
        names = resource.get("name", [])
        if not names:
            errors.append("US Core Patient: 'name' is required (must-support).")
        else:
            has_family = any(n.get("family") for n in names)
            has_given = any(n.get("given") for n in names)
            if not has_family:
                warnings.append(
                    "US Core Patient: 'name.family' should be present (should-support)."
                )
            if not has_given:
                warnings.append("US Core Patient: 'name.given' should be present (should-support).")

        # Must-support: gender
        if not resource.get("gender"):
            errors.append(
                "US Core Patient: 'gender' is required (must-support). "
                "Use: male | female | other | unknown."
            )

        # Should-support: birthDate
        if not resource.get("birthDate"):
            # Check for data-absent-reason extension
            extensions = resource.get("extension", [])
            has_absent = any("data-absent-reason" in e.get("url", "") for e in extensions)
            if not has_absent:
                warnings.append(
                    "US Core Patient: 'birthDate' should be present. "
                    "If not available, add a data-absent-reason extension."
                )

        return ValidationResult(
            valid=len(errors) == 0,
            profile="US Core Patient (v6.1.0)",
            errors=errors,
            warnings=warnings,
        )

    def _validate_condition(self, resource: dict) -> ValidationResult:  # noqa: ANN401
        """
        US Core Condition must-support elements:
          - clinicalStatus (required, correct code system)
          - code (required, ICD-10 or SNOMED coding)
          - subject (required)
        """
        errors: list[str] = []
        warnings: list[str] = []

        # Must-support: clinicalStatus
        clinical_status = resource.get("clinicalStatus")
        if not clinical_status:
            errors.append("US Core Condition: 'clinicalStatus' is required (must-support).")
        else:
            codings = clinical_status.get("coding", [])
            if not codings:
                errors.append("US Core Condition: 'clinicalStatus.coding' must be present.")
            else:
                systems = {c.get("system", "") for c in codings}
                if not systems & _CLINICAL_STATUS_SYSTEMS:
                    errors.append(
                        "US Core Condition: 'clinicalStatus.coding.system' must use "
                        "http://terminology.hl7.org/CodeSystem/condition-clinical."
                    )

        # Must-support: code
        code = resource.get("code")
        if not code:
            errors.append(
                "US Core Condition: 'code' is required (must-support). "
                "Must include ICD-10 or SNOMED coding."
            )
        else:
            codings = code.get("coding", [])
            if not codings:
                errors.append(
                    "US Core Condition: 'code.coding' must be present with "
                    "ICD-10-CM or SNOMED CT system."
                )
            else:
                systems = {c.get("system", "") for c in codings}
                if not (systems & _ICD10_SYSTEMS or systems & _SNOMED_SYSTEMS):
                    warnings.append(
                        "US Core Condition: 'code.coding.system' should use "
                        "ICD-10-CM or SNOMED CT for interoperability."
                    )

        # Must-support: subject
        if not resource.get("subject"):
            errors.append(
                "US Core Condition: 'subject' is required (must-support). "
                "Must reference a Patient resource."
            )

        # Should-support: recordedDate
        if not resource.get("recordedDate") and not resource.get("onset"):
            warnings.append(
                "US Core Condition: 'recordedDate' or 'onsetDateTime' should be present."
            )

        return ValidationResult(
            valid=len(errors) == 0,
            profile="US Core Condition (v6.1.0)",
            errors=errors,
            warnings=warnings,
        )

    def _validate_service_request(self, resource: dict) -> ValidationResult:  # noqa: ANN401
        """
        US Core ServiceRequest must-support elements:
          - status (required)
          - intent (required)
          - code (required, CPT or SNOMED)
          - subject (required)
          - authoredOn (required for PA workflows)
        """
        errors: list[str] = []
        warnings: list[str] = []

        # All four mandatory
        for field_name in ("status", "intent", "subject"):
            if not resource.get(field_name):
                errors.append(f"US Core ServiceRequest: '{field_name}' is required (must-support).")

        # code — handle nested concept (R5 CodeableReference) or direct
        code = resource.get("code")
        if not code:
            errors.append("US Core ServiceRequest: 'code' is required (must-support).")
        else:
            # R5 uses code.concept.coding, R4 uses code.coding
            codings = code.get("coding") or (code.get("concept") or {}).get("coding", [])
            if not codings:
                errors.append("US Core ServiceRequest: 'code.coding' must be present.")
            else:
                systems = {c.get("system", "") for c in codings}
                if not (systems & _CPT_SYSTEMS or systems & _SNOMED_SYSTEMS):
                    warnings.append(
                        "US Core ServiceRequest: 'code.coding.system' should use "
                        "CPT or SNOMED CT for interoperability."
                    )

        # Should-support: authoredOn (required in PA workflows)
        if not resource.get("authoredOn"):
            warnings.append(
                "US Core ServiceRequest: 'authoredOn' is strongly recommended "
                "for Prior Authorization workflows (CMS-0057)."
            )

        return ValidationResult(
            valid=len(errors) == 0,
            profile="US Core ServiceRequest (v6.1.0)",
            errors=errors,
            warnings=warnings,
        )

    def _validate_procedure(self, resource: dict) -> ValidationResult:  # noqa: ANN401
        """
        US Core Procedure must-support elements:
          - status (required)
          - code (required, CPT or SNOMED)
          - subject (required)
        """
        errors: list[str] = []
        warnings: list[str] = []

        for field_name in ("status", "subject"):
            if not resource.get(field_name):
                errors.append(f"US Core Procedure: '{field_name}' is required (must-support).")

        code = resource.get("code")
        if not code:
            errors.append("US Core Procedure: 'code' is required (must-support).")
        else:
            codings = code.get("coding", [])
            if not codings:
                errors.append("US Core Procedure: 'code.coding' must be present.")
            else:
                systems = {c.get("system", "") for c in codings}
                if not (systems & _CPT_SYSTEMS or systems & _SNOMED_SYSTEMS):
                    warnings.append(
                        "US Core Procedure: 'code.coding.system' should use CPT or SNOMED CT."
                    )

        if not resource.get("performed") and not resource.get("performedDateTime"):
            warnings.append("US Core Procedure: 'performed[x]' should be present when known.")

        return ValidationResult(
            valid=len(errors) == 0,
            profile="US Core Procedure (v6.1.0)",
            errors=errors,
            warnings=warnings,
        )


# Module-level convenience instance
fhir_validator = FHIRValidator()
