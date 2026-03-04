# claude-care-orchestrator 🏥

**The AI-Native Vertical Engine for Reducing U.S. Healthcare Administrative Friction.**

[![CI](https://github.com/bahtoo/claude-care-orchestrator/actions/workflows/ci.yml/badge.svg)](https://github.com/bahtoo/claude-care-orchestrator/actions/workflows/ci.yml)
[![Python 3.11+](https://img.shields.io/badge/python-3.11+-blue.svg)](https://www.python.org/downloads/)
[![License: MIT](https://img.shields.io/badge/License-MIT-green.svg)](LICENSE)

## 0 → 1 Vision

U.S. healthcare waste exceeds **$265B annually** due to administrative complexity—the friction between payers, providers, and the systems that connect them. `claude-care-orchestrator` is a modular framework designed to prove that AI can materially reduce this waste by acting as an intelligent intermediary.

## Core Product Pillars

- **Workflow Triage:** Automatically identifying and routing high-value workflows (Prior Auth, Claims Appeals, Coding).
- **Regulatory-First Design:** Native HIPAA guardrails and PII scrubbing built into the orchestration layer.
- **Interoperability:** Translating unstructured clinical dialogue into structured FHIR R4 resources.

---

## Architecture

```
                    ┌─────────────────────────────┐
                    │     Raw Clinical Text        │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Pass 1: PHI Detector       │
                    │   (Deterministic Regex)       │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   Pass 2: LLM Audit          │
                    │   (Claude — Contextual PHI    │
                    │    + Code Extraction)         │
                    └──────────────┬──────────────┘
                                   │
                    ┌──────────────▼──────────────┐
                    │   FHIR R4 Mapper             │
                    │   Patient | Condition |       │
                    │   Procedure | ServiceRequest  │
                    └──────────────┬──────────────┘
                                   │
              ┌────────────────────┼────────────────────┐
              │                    │                    │
     ┌────────▼─────┐   ┌────────▼─────┐   ┌─────────▼────────┐
     │  Prior Auth   │   │   Appeals    │   │   MCP Server     │
     │  Request      │   │   Letter     │   │   (Claude Tools) │
     └──────────────┘   └──────────────┘   └──────────────────┘
```

### Key Components

| Component                          | Description                                                              |
| ---------------------------------- | ------------------------------------------------------------------------ |
| `phi_detector.py`                  | Deterministic regex PHI detection (SSN, phone, DOB, email, MRN, address) |
| `compliance_engine.py`             | Two-pass audit engine (regex → LLM) with structured output               |
| `fhir_mapper.py`                   | Clinical-to-FHIR R4 resource generator                                   |
| `mcp_server.py`                    | MCP server exposing tools for Claude Desktop / Claude Code               |
| `config/regulatory_guardrails.xml` | HIPAA safety rules and escalation triggers                               |
| `master_prompt.md`                 | System prompt for Claude's "Administrative Brain"                        |

---

## Getting Started

### Prerequisites

- Python 3.11+
- An [Anthropic API key](https://console.anthropic.com/)

### Installation

```bash
# Clone the repo
git clone https://github.com/bahtoo/claude-care-orchestrator.git
cd claude-care-orchestrator

# Install in development mode
pip install -e ".[dev]"

# Set up your environment
cp .env.example .env
# Edit .env and add your ANTHROPIC_API_KEY
```

### Run the Compliance Engine

```bash
python -m care_orchestrator.compliance_engine
```

### Run the MCP Server

```bash
python -m care_orchestrator.mcp_server
```

To connect to **Claude Desktop**, add this to your `claude_desktop_config.json`:

```json
{
  "mcpServers": {
    "care-orchestrator": {
      "command": "python",
      "args": ["-m", "care_orchestrator.mcp_server"],
      "cwd": "/path/to/claude-care-orchestrator"
    }
  }
}
```

### Run Tests

```bash
# All tests (no API key needed — everything is mocked)
pytest tests/ -v

# Linting
ruff check src/ tests/
```

---

## 🛡️ The DRI Safety Filter

`claude-care-orchestrator` implements a **dual-pass compliance check** — a deterministic regex pre-pass followed by LLM-powered contextual analysis. This ensures zero-leakage of PHI, aligning with Constitutional AI and safety-first delivery in highly regulated industries.

---

## MCP Tools

When connected via MCP, Claude gets access to these tools:

| Tool                     | Description                          | LLM Cost      |
| ------------------------ | ------------------------------------ | ------------- |
| `audit_clinical_text`    | Full two-pass compliance audit       | Yes           |
| `extract_fhir_resources` | Convert clinical text → FHIR R4 JSON | Yes           |
| `check_phi_status`       | Quick regex-only PHI scan            | **No** (free) |

---

## Strategic Roadmap

See [ROADMAP.md](ROADMAP.md) for the full 0→1 plan across three phases:

1. **Foundation** — HIPAA-Compliant Data Pipelines ← _current_
2. **Friction Reduction** — Prior Auth automation ("Payer-Provider Bridge")
3. **Scaling** — Multi-agent Revenue Cycle Management

---

## Strategic Leadership

This repository is managed with a **Low Ego, High Accountability** mindset. It is designed to triage cross-functional threads across Product, Engineering, Policy, and Research to ensure nothing important falls through the cracks.

## License

[MIT](LICENSE) — Bahtiyar Aytac
