"""
Clinical-to-FHIR R4 Mapper.

Converts clinical text and extracted medical codes into validated FHIR R4 resources.

Supported resource types (Phase 1):
  - Patient (with redacted demographics)
  - Condition (from ICD-10 codes)
  - Procedure (from CPT codes)
  - ServiceRequest (for Prior Auth scenarios)
"""

from __future__ import annotations

import uuid
from datetime import UTC, datetime

from fhir.resources.condition import Condition
from fhir.resources.patient import Patient
from fhir.resources.procedure import Procedure
from fhir.resources.servicerequest import ServiceRequest

from care_orchestrator.logging_config import logger
from care_orchestrator.models import AdminMetadata, FHIROutput, FHIRResourceOutput

# ---------------------------------------------------------------------------
# Common ICD-10 / CPT code descriptions (sample lookup — extend as needed)
# ---------------------------------------------------------------------------

ICD10_DESCRIPTIONS: dict[str, str] = {
    "M23.5": "Chronic instability of knee",
    "M17.11": "Primary osteoarthritis, right knee",
    "M17.12": "Primary osteoarthritis, left knee",
    "M54.5": "Low back pain",
    "E11.9": "Type 2 diabetes mellitus without complications",
    "I10": "Essential (primary) hypertension",
    "J06.9": "Acute upper respiratory infection, unspecified",
    "Z00.00": "Encounter for general adult medical examination",
}

CPT_DESCRIPTIONS: dict[str, str] = {
    "73221": "MRI, any joint of lower extremity",
    "99213": "Office visit, established patient, low complexity",
    "99214": "Office visit, established patient, moderate complexity",
    "99215": "Office visit, established patient, high complexity",
    "27447": "Total knee replacement arthroplasty",
    "72148": "MRI, lumbar spine without contrast",
    "99385": "Preventive visit, new patient, 18-39 years",
}


class FHIRMapper:
    """Maps clinical metadata to validated FHIR R4 resources."""

    def map(
        self,
        admin_metadata: AdminMetadata,
        redacted_text: str,
        patient_id: str | None = None,
    ) -> FHIROutput:
        """
        Generate FHIR R4 resources from administrative metadata.

        Args:
            admin_metadata: Extracted CPT/ICD-10 codes and workflow type.
            redacted_text: The PHI-redacted clinical text (used as reference).
            patient_id: Optional patient identifier. Auto-generated if not provided.

        Returns:
            FHIROutput containing all generated and validated resources.
        """
        patient_id = patient_id or str(uuid.uuid4())
        resources: list[FHIRResourceOutput] = []

        logger.info(
            f"FHIR mapping started: "
            f"{len(admin_metadata.icd10_codes)} ICD-10 codes, "
            f"{len(admin_metadata.cpt_codes)} CPT codes, "
            f"workflow={admin_metadata.workflow_type}"
        )

        # ── Generate Patient resource ─────────────────────────────────────
        patient_resource = self._build_patient(patient_id)
        resources.append(patient_resource)

        # ── Generate Condition resources from ICD-10 codes ────────────────
        for code in admin_metadata.icd10_codes:
            condition = self._build_condition(code, patient_id)
            resources.append(condition)

        # ── Generate Procedure resources from CPT codes ───────────────────
        for code in admin_metadata.cpt_codes:
            procedure = self._build_procedure(code, patient_id)
            resources.append(procedure)

        # ── Generate ServiceRequest for Prior Auth workflows ──────────────
        if admin_metadata.workflow_type == "prior_auth":
            service_request = self._build_service_request(
                admin_metadata, patient_id
            )
            resources.append(service_request)

        output = FHIROutput(
            resources=resources,
            source_text_redacted=redacted_text,
            total_resources=len(resources),
        )

        logger.info(f"FHIR mapping complete: {output.total_resources} resources generated")
        return output

    def _build_patient(self, patient_id: str) -> FHIRResourceOutput:
        """Build a FHIR R4 Patient resource with redacted demographics."""
        try:
            patient = Patient.model_validate(
                {
                    "resourceType": "Patient",
                    "id": patient_id,
                    "active": True,
                    "name": [
                        {
                            "use": "official",
                            "family": "[REDACTED]",
                            "given": ["[REDACTED]"],
                        }
                    ],
                    "gender": "unknown",
                    "meta": {
                        "lastUpdated": datetime.now(tz=UTC).isoformat(),
                        "tag": [
                            {
                                "system": "https://care-orchestrator.dev/phi-status",
                                "code": "redacted",
                                "display": "PHI Redacted",
                            }
                        ],
                    },
                }
            )
            return FHIRResourceOutput(
                resource_type="Patient",
                resource_json=patient.model_dump(exclude_none=True),
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"Patient resource validation failed: {e}")
            return FHIRResourceOutput(
                resource_type="Patient",
                resource_json={"id": patient_id, "error": str(e)},
                is_valid=False,
                validation_errors=[str(e)],
            )

    def _build_condition(self, icd10_code: str, patient_id: str) -> FHIRResourceOutput:
        """Build a FHIR R4 Condition resource from an ICD-10 code."""
        display = ICD10_DESCRIPTIONS.get(icd10_code, f"ICD-10 code {icd10_code}")

        try:
            condition = Condition.model_validate(
                {
                    "resourceType": "Condition",
                    "id": str(uuid.uuid4()),
                    "clinicalStatus": {
                        "coding": [
                            {
                                "system": "http://terminology.hl7.org/CodeSystem/condition-clinical",
                                "code": "active",
                                "display": "Active",
                            }
                        ]
                    },
                    "code": {
                        "coding": [
                            {
                                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                "code": icd10_code,
                                "display": display,
                            }
                        ],
                        "text": display,
                    },
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "recordedDate": datetime.now(tz=UTC).strftime("%Y-%m-%d"),
                }
            )
            return FHIRResourceOutput(
                resource_type="Condition",
                resource_json=condition.model_dump(exclude_none=True),
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"Condition resource validation failed for {icd10_code}: {e}")
            return FHIRResourceOutput(
                resource_type="Condition",
                resource_json={"code": icd10_code, "error": str(e)},
                is_valid=False,
                validation_errors=[str(e)],
            )

    def _build_procedure(self, cpt_code: str, patient_id: str) -> FHIRResourceOutput:
        """Build a FHIR R4 Procedure resource from a CPT code."""
        display = CPT_DESCRIPTIONS.get(cpt_code, f"CPT code {cpt_code}")

        try:
            procedure = Procedure.model_validate(
                {
                    "resourceType": "Procedure",
                    "id": str(uuid.uuid4()),
                    "status": "preparation",
                    "code": {
                        "coding": [
                            {
                                "system": "http://www.ama-assn.org/go/cpt",
                                "code": cpt_code,
                                "display": display,
                            }
                        ],
                        "text": display,
                    },
                    "subject": {"reference": f"Patient/{patient_id}"},
                }
            )
            return FHIRResourceOutput(
                resource_type="Procedure",
                resource_json=procedure.model_dump(exclude_none=True),
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"Procedure resource validation failed for {cpt_code}: {e}")
            return FHIRResourceOutput(
                resource_type="Procedure",
                resource_json={"code": cpt_code, "error": str(e)},
                is_valid=False,
                validation_errors=[str(e)],
            )

    def _build_service_request(
        self, admin_metadata: AdminMetadata, patient_id: str
    ) -> FHIRResourceOutput:
        """Build a FHIR R5 ServiceRequest for Prior Auth workflows."""
        # Use the first CPT code as the primary service being requested
        primary_code = admin_metadata.cpt_codes[0] if admin_metadata.cpt_codes else "unknown"
        display = CPT_DESCRIPTIONS.get(primary_code, f"CPT code {primary_code}")

        # Collect supporting diagnoses as CodeableReference items
        reason_refs = []
        for icd_code in admin_metadata.icd10_codes:
            icd_display = ICD10_DESCRIPTIONS.get(icd_code, f"ICD-10 code {icd_code}")
            reason_refs.append(
                {
                    "concept": {
                        "coding": [
                            {
                                "system": "http://hl7.org/fhir/sid/icd-10-cm",
                                "code": icd_code,
                                "display": icd_display,
                            }
                        ],
                        "text": icd_display,
                    }
                }
            )

        try:
            service_request = ServiceRequest.model_validate(
                {
                    "resourceType": "ServiceRequest",
                    "id": str(uuid.uuid4()),
                    "status": "draft",
                    "intent": "order",
                    "priority": "routine",
                    "code": {
                        "concept": {
                            "coding": [
                                {
                                    "system": "http://www.ama-assn.org/go/cpt",
                                    "code": primary_code,
                                    "display": display,
                                }
                            ],
                            "text": f"Prior Authorization Request: {display}",
                        }
                    },
                    "subject": {"reference": f"Patient/{patient_id}"},
                    "authoredOn": datetime.now(tz=UTC).isoformat(),
                    "reason": reason_refs if reason_refs else None,
                }
            )
            return FHIRResourceOutput(
                resource_type="ServiceRequest",
                resource_json=service_request.model_dump(exclude_none=True),
                is_valid=True,
            )
        except Exception as e:
            logger.error(f"ServiceRequest resource validation failed: {e}")
            return FHIRResourceOutput(
                resource_type="ServiceRequest",
                resource_json={"code": primary_code, "error": str(e)},
                is_valid=False,
                validation_errors=[str(e)],
            )


# Module-level convenience instance
fhir_mapper = FHIRMapper()
