"""
MCP Server for care-orchestrator.

Exposes healthcare compliance tools via the Model Context Protocol (MCP),
allowing Claude Desktop / Claude Code to safely interact with the engine.

Tools exposed:
  - audit_clinical_text: Full two-pass compliance audit
  - extract_fhir_resources: Convert clinical text to FHIR R4 JSON
  - check_phi_status: Quick regex-only PHI scan (no LLM cost)
"""

from __future__ import annotations

import json

from mcp.server import Server
from mcp.server.stdio import run_server
from mcp.types import TextContent, Tool

from care_orchestrator.compliance_engine import ComplianceEngine
from care_orchestrator.fhir_mapper import fhir_mapper
from care_orchestrator.models import ClinicalNote
from care_orchestrator.phi_detector import phi_detector

# Initialize the MCP server
server = Server("care-orchestrator")

# Lazy-init compliance engine (only created when a tool that needs it is called)
_engine: ComplianceEngine | None = None


def _get_engine() -> ComplianceEngine:
    """Get or create the compliance engine singleton."""
    global _engine  # noqa: PLW0603
    if _engine is None:
        _engine = ComplianceEngine()
    return _engine


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
    ]


# ---------------------------------------------------------------------------
# Tool Handlers
# ---------------------------------------------------------------------------


@server.call_tool()
async def call_tool(name: str, arguments: dict) -> list[TextContent]:
    """Handle tool calls from Claude."""
    if name == "audit_clinical_text":
        return await _handle_audit(arguments)
    elif name == "extract_fhir_resources":
        return await _handle_fhir(arguments)
    elif name == "check_phi_status":
        return await _handle_phi_check(arguments)
    else:
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


# ---------------------------------------------------------------------------
# Entry point
# ---------------------------------------------------------------------------


async def main() -> None:
    """Run the MCP server via stdio transport."""
    await run_server(server)


if __name__ == "__main__":
    import asyncio

    asyncio.run(main())
