# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.1.0] - 2026-03-05

### Added

- **Project scaffolding**: `pyproject.toml`, `.env.example`, `src/care_orchestrator/` package structure
- **Deterministic PHI detector** (`phi_detector.py`): Regex-based detection for SSN, phone, DOB, email, MRN, addresses
- **Two-pass compliance engine** (`compliance_engine.py`): Regex pre-pass + LLM audit with structured XML parsing
- **FHIR R5 mapper** (`fhir_mapper.py`): Clinical-to-FHIR resource generation (Patient, Condition, Procedure, ServiceRequest)
- **MCP server** (`mcp_server.py`): 3 tools exposed via stdio transport (`audit_clinical_text`, `extract_fhir_resources`, `check_phi_status`)
- **Configuration** (`config.py`): Pydantic-settings based config loading from `.env`
- **Domain models** (`models.py`): 10 Pydantic models for PHI, Audit, FHIR data contracts
- **Audit logging** (`logging_config.py`): JSON-structured compliance trail logging
- **Regulatory guardrails** (`config/regulatory_guardrails.xml`): HIPAA safety rules, escalation triggers, output constraints
- **Test suite**: 61 tests across 4 test files (PHI detector, compliance engine, FHIR mapper, models)
- **CI pipeline** (`.github/workflows/ci.yml`): GitHub Actions running ruff + pytest on Python 3.11-3.13
- **Sprint workflow** (`.agent/workflows/sprint-close.md`): Reusable sprint close process
