"""
MCP Server for care-orchestrator.

Exposes healthcare compliance tools via the Model Context Protocol (MCP),
allowing Claude Desktop / Claude Code to safely interact with the engine.

Tools exposed (Phase 1):
  - audit_clinical_text: Full two-pass compliance audit
  - extract_fhir_resources: Convert clinical text to FHIR R4 JSON
  - check_phi_status: Quick regex-only PHI scan (no LLM cost)

Tools exposed (Phase 2):
  - submit_prior_auth: End-to-end prior authorization workflow
  - evaluate_medical_necessity: Medical necessity check against payer criteria
  - generate_appeal: Appeal letter for denied prior authorizations
"""

from __future__ import annotations

import json

from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import TextContent, Tool

from care_orchestrator.appeal_generator import AppealGenerator
from care_orchestrator.compliance_engine import ComplianceEngine
from care_orchestrator.fhir_mapper import fhir_mapper
from care_orchestrator.models import AppealType, ClinicalNote, NecessityDetermination
from care_orchestrator.phi_detector import phi_detector
from care_orchestrator.prior_auth import PriorAuthGenerator

# Initialize the MCP server
server = Server("care-orchestrator")

# Lazy-init singletons
_engine: ComplianceEngine | None = None
_pa_generator: PriorAuthGenerator | None = None
_appeal_gen: AppealGenerator | None = None


def _get_engine() -> ComplianceEngine:
    """Get or create the compliance engine singleton."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = ComplianceEngine()
    return _engine


def _get_pa_generator() -> PriorAuthGenerator:
    """Get or create the PA generator singleton."""
    global _pa_generator  # noqa: PLW0603
    if _pa_generator is None:
        _pa_generator = PriorAuthGenerator()
    return _pa_generator


def _get_appeal_gen() -> AppealGenerator:
    """Get or create the appeal generator singleton."""
    global _appeal_gen  # noqa: PLW0603
    if _appeal_gen is None:
        _appeal_gen = AppealGenerator()
    return _appeal_gen


# ---------------------------------------------------------------------------
# Tool Definitions
# ---------------------------------------------------------------------------


@server.list_tools()
async def list_tools() -> list[Tool]:
    """List all available MCP tools."""
    return [
        Tool(
            name="audit_clinical_text",
            description=(
                "Run a full two-pass compliance audit on clinical text. "
                "Pass 1: Deterministic regex PHI scan. "
                "Pass 2: LLM-powered contextual audit + CPT/ICD-10 extraction. "
                "Returns structured audit report with redacted text and admin metadata."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw clinical text to audit for PHI and extract codes from.",
                    },
                    "source": {
                        "type": "string",
                        "description": "Source system (e.g., 'epic', 'cerner'). Optional.",
                        "default": "unknown",
                    },
                    "note_type": {
                        "type": "string",
                        "description": "Note type (e.g., 'progress', 'discharge'). Optional.",
                        "default": "general",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="extract_fhir_resources",
            description=(
                "Convert clinical text into validated FHIR R4 resources. "
                "First runs compliance audit to extract codes, then generates "
                "Patient, Condition, Procedure, and ServiceRequest resources."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw clinical text to convert to FHIR R4.",
                    },
                },
                "required": ["text"],
            },
        ),
        Tool(
            name="check_phi_status",
            description=(
                "Quick PHI scan using deterministic regex patterns only (no LLM cost). "
                "Returns detected PHI entities and redacted text. "
                "Use this for fast pre-screening before full audit."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Text to scan for PHI.",
                    },
                },
                "required": ["text"],
            },
        ),
        # ── Phase 2 Tools ──────────────────────────────────────────────
        Tool(
            name="submit_prior_auth",
            description=(
                "Run the full Prior Authorization workflow: compliance audit → "
                "policy lookup → medical necessity evaluation → FHIR generation → "
                "PA request assembly. Returns status, decision, and documents."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw clinical note text.",
                    },
                    "payer_id": {
                        "type": "string",
                        "description": (
                            "Payer identifier (e.g., 'commercial_generic', "
                            "'medicare', 'medicaid')."
                        ),
                    },
                },
                "required": ["text", "payer_id"],
            },
        ),
        Tool(
            name="evaluate_medical_necessity",
            description=(
                "Evaluate whether clinical documentation supports medical "
                "necessity for a procedure based on a specific payer's criteria."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw clinical note text.",
                    },
                    "payer_id": {
                        "type": "string",
                        "description": "Payer identifier.",
                    },
                },
                "required": ["text", "payer_id"],
            },
        ),
        Tool(
            name="generate_appeal",
            description=(
                "Generate an appeal letter for a denied prior authorization. "
                "Supports initial, peer-to-peer, and external review appeals."
            ),
            inputSchema={
                "type": "object",
                "properties": {
                    "text": {
                        "type": "string",
                        "description": "Raw clinical note text.",
                    },
                    "payer_id": {
                        "type": "string",
                        "description": "Payer identifier.",
                    },
                    "denial_reason": {
                        "type": "string",
                        "description": "The payer's stated reason for denial.",
                    },
                    "appeal_type": {
                        "type": "string",
                        "description": (
                            "Type of appeal: 'initial_appeal', "
                            "'peer_to_peer_review', or 'external_review'."
                        ),
                        "default": "initial_appeal",
                    },
                },
                "required": ["text", "payer_id", "denial_reason"],
            },
        ),
    ]


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from Claude."""
    handlers = {
        "audit_clinical_text": _handle_audit,
        "extract_fhir_resources": _handle_fhir,
        "check_phi_status": _handle_phi_check,
        "submit_prior_auth": _handle_prior_auth,
        "evaluate_medical_necessity": _handle_necessity,
        "generate_appeal": _handle_appeal,
    }
    handler = handlers.get(name)
    if handler:
        return await handler(arguments)
    return [TextContent(type="text", text=f"Unknown tool: {name}")]


async def _handle_audit(arguments: dict) -> list[TextContent]:
    """Handle the audit_clinical_text tool call."""
    note = ClinicalNote(
        text=arguments["text"],
        source=arguments.get("source", "unknown"),
        note_type=arguments.get("note_type", "general"),
    )

    engine = _get_engine()
    report = engine.audit(note)

    result = {
        "phi_status": report.phi_status,
        "entities_found": report.phi_detection.entity_count,
        "entities": [
            {"type": e.phi_type.value, "value": "[HIDDEN]"} for e in report.phi_detection.entities
        ],
        "redacted_text": report.redacted_text,
        "cpt_codes": report.admin_metadata.cpt_codes,
        "icd10_codes": report.admin_metadata.icd10_codes,
        "workflow_type": report.admin_metadata.workflow_type,
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_fhir(arguments: dict) -> list[TextContent]:
    """Handle the extract_fhir_resources tool call."""
    engine = _get_engine()
    report = engine.audit_text(arguments["text"])

    fhir_output = fhir_mapper.map(
        admin_metadata=report.admin_metadata,
        redacted_text=report.redacted_text,
    )

    result = {
        "total_resources": fhir_output.total_resources,
        "resources": [
            {
                "resource_type": r.resource_type,
                "is_valid": r.is_valid,
                "resource": r.resource_json,
                "validation_errors": r.validation_errors,
            }
            for r in fhir_output.resources
        ],
    }

    return [TextContent(type="text", text=json.dumps(result, indent=2))]


async def _handle_phi_check(arguments: dict) -> list[TextContent]:
    """Handle the check_phi_status tool call (regex only, no LLM)."""
    result = phi_detector.detect(arguments["text"])

    output = {
        "is_clean": result.is_clean,
        "entity_count": result.entity_count,
        "entities": [
            {
                "type": e.phi_type.value,
                "position": {"start": e.start, "end": e.end},
            }
            for e in result.entities
        ],
        "redacted_text": result.redacted_text,
    }

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _handle_prior_auth(arguments: dict) -> list[TextContent]:
    """Handle the submit_prior_auth tool call."""
    pa_gen = _get_pa_generator()
    result = pa_gen.submit(
        clinical_text=arguments["text"],
        payer_id=arguments["payer_id"],
    )

    output = {
        "status": result.status.value,
        "summary": result.summary,
        "turnaround_minutes": result.turnaround_estimate_minutes,
    }
    if result.request:
        output["decision"] = {
            "determination": result.request.necessity_decision.determination.value,
            "rationale": result.request.necessity_decision.rationale,
            "confidence": result.request.necessity_decision.confidence_score,
            "criteria_met": result.request.necessity_decision.criteria_met,
            "criteria_unmet": result.request.necessity_decision.criteria_unmet,
            "missing_docs": result.request.necessity_decision.missing_documentation,
        }
        if result.request.fhir_resources:
            output["fhir_resource_count"] = result.request.fhir_resources.total_resources

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _handle_necessity(arguments: dict) -> list[TextContent]:
    """Handle the evaluate_medical_necessity tool call."""
    # Run a PA workflow but return just the necessity decision
    pa_gen = _get_pa_generator()
    result = pa_gen.submit(
        clinical_text=arguments["text"],
        payer_id=arguments["payer_id"],
    )

    if result.request and result.request.necessity_decision:
        dec = result.request.necessity_decision
        output = {
            "determination": dec.determination.value,
            "rationale": dec.rationale,
            "confidence": dec.confidence_score,
            "criteria_met": dec.criteria_met,
            "criteria_unmet": dec.criteria_unmet,
            "missing_documentation": dec.missing_documentation,
        }
    else:
        output = {
            "determination": "not_evaluated",
            "rationale": result.summary,
        }

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


async def _handle_appeal(arguments: dict) -> list[TextContent]:
    """Handle the generate_appeal tool call."""
    # First run PA workflow to get the necessity decision
    pa_gen = _get_pa_generator()
    result = pa_gen.submit(
        clinical_text=arguments["text"],
        payer_id=arguments["payer_id"],
    )

    necessity_decision = (
        result.request.necessity_decision
        if result.request
        else NecessityDetermination.DENIED
    )

    appeal_type_str = arguments.get("appeal_type", "initial_appeal")
    try:
        appeal_type = AppealType(appeal_type_str)
    except ValueError:
        appeal_type = AppealType.INITIAL

    appeal_gen = _get_appeal_gen()
    letter = appeal_gen.generate(
        denial_reason=arguments["denial_reason"],
        procedure_code=result.request.procedure_code if result.request else "unknown",
        diagnosis_codes=result.request.diagnosis_codes if result.request else [],
        clinical_text=result.audit_report.redacted_text if result.audit_report else "",
        necessity_decision=necessity_decision,
        payer_name=arguments["payer_id"],
        appeal_type=appeal_type,
    )

    output = {
        "appeal_type": letter.appeal_type.value,
        "letter": letter.letter_content,
        "justification": letter.clinical_justification,
        "policy_citations": letter.policy_citations,
    }

    return [TextContent(type="text", text=json.dumps(output, indent=2))]


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the MCP server via stdio transport."""
    await run_server(server)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
