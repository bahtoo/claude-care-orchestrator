"""
FHIR R4 Bundle assembler.

Builds FHIR searchset Bundles from lists of entries — used by the
Patient Access API (CMS-0057) to return patient-level data.
"""

from __future__ import annotations

from datetime import UTC, datetime
from typing import Any


def make_bundle(
    resource_type: str,
    entries: list[dict[str, Any]],
    base_url: str = "http://care-orchestrator/fhir",
) -> dict[str, Any]:
    """
    Assemble a FHIR R4 searchset Bundle.

    Args:
        resource_type: The primary resource type in entries (e.g. "Patient").
        entries: List of FHIR resource dicts to wrap as bundle entries.
        base_url: Server base URL used for fullUrl construction.

    Returns:
        A FHIR R4 Bundle dict with type=searchset.
    """
    bundle_entries = [
        {
            "fullUrl": f"{base_url}/{resource_type}/{entry.get('id', 'unknown')}",
            "resource": entry,
            "search": {"mode": "match"},
        }
        for entry in entries
    ]

    return {
        "resourceType": "Bundle",
        "id": f"bundle-{resource_type.lower()}-{datetime.now(tz=UTC).strftime('%Y%m%d%H%M%S')}",
        "meta": {"lastUpdated": datetime.now(tz=UTC).isoformat()},
        "type": "searchset",
        "total": len(entries),
        "entry": bundle_entries,
    }


def make_eob_entry(record: dict[str, Any]) -> dict[str, Any]:
    """
    Build a minimal ExplanationOfBenefit FHIR resource from a PARecord dict.

    This is a stub representation — a production EOB would pull from a
    claims adjudication system. This satisfies the CMS-0057 data element
    requirements at a structural level.
    """
    return {
        "resourceType": "ExplanationOfBenefit",
        "id": record.get("pa_number", "unknown").replace("PA-", "EOB-"),
        "status": "active",
        "type": {
            "coding": [
                {
                    "system": "http://terminology.hl7.org/CodeSystem/claim-type",
                    "code": "professional",
                }
            ]
        },
        "use": "claim",
        "patient": {"reference": f"Patient/{record.get('patient_id', 'unknown')}"},
        "created": record.get("created_at", datetime.now(tz=UTC).isoformat()),
        "outcome": "complete" if record.get("success") else "error",
        "item": [
            {
                "sequence": i + 1,
                "productOrService": {
                    "coding": [
                        {
                            "system": "http://www.ama-assn.org/go/cpt",
                            "code": cpt,
                        }
                    ]
                },
                "adjudication": [
                    {
                        "category": {
                            "coding": [
                                {
                                    "system": "http://terminology.hl7.org/CodeSystem/adjudication",
                                    "code": "benefit",
                                }
                            ]
                        },
                        "reason": {
                            "coding": [
                                {
                                    "code": record.get("pa_status", "pending"),
                                }
                            ]
                        },
                    }
                ],
            }
            for i, cpt in enumerate(record.get("cpt_codes", []))
        ],
    }


def make_coverage_entry(record: dict[str, Any]) -> dict[str, Any]:
    """
    Build a minimal Coverage FHIR resource from a PARecord dict.

    Stub representation satisfying CMS-0057 Coverage data element requirements.
    """
    return {
        "resourceType": "Coverage",
        "id": record.get("pa_number", "unknown").replace("PA-", "COV-"),
        "status": "active",
        "beneficiary": {"reference": f"Patient/{record.get('patient_id', 'unknown')}"},
        "payor": [{"display": "Payer (stub)"}],
        "period": {
            "start": record.get("created_at", datetime.now(tz=UTC).isoformat())[:10],
        },
    }
