# Changelog

All notable changes to this project will be documented in this file.

The format is based on [Keep a Changelog](https://keepachangelog.com/en/1.1.0/),
and this project adheres to [Semantic Versioning](https://semver.org/spec/v2.0.0.html).

## [0.7.0] - 2026-03-05

### Added

- **EHR Adapter Framework** (`src/care_orchestrator/ehr/`): abstract `EHRAdapter` base with token caching + TTL refresh, authenticated/open-sandbox FHIR GET helper, `_bundle_entries` utility
- **Oracle Health Adapter** (`ehr/oracle_health.py`): open sandbox (no auth) + secure sandbox via SMART `client_credentials` against Cerner Authorization Server
- **Epic Adapter** (`ehr/epic.py`): RSA-2048 signed JWT assertion → token exchange (no `client_secret`); open sandbox fallback when no key configured; `python-jose` signing
- **InterSystems IRIS Adapter** (`ehr/intersystems.py`): SMART `client_credentials`, configurable base URL + token URL
- **Veradigm (AllScripts) Adapter** (`ehr/veradigm.py`): SMART OAuth 2.0 `client_credentials`, targets Veradigm Developer Portal sandbox
- **`EHRRegistry`** (`ehr/registry.py`): env-driven factory (`EHR_VENDOR`, `EHR_BASE_URL`, `EHR_CLIENT_ID`, `EHR_CLIENT_SECRET`, `EHR_PRIVATE_KEY_PATH`); sensible open-sandbox defaults so CI works with zero config
- **Alembic migration framework** (`alembic/`): async SQLAlchemy env, `render_as_batch` for SQLite ALTER TABLE, `_get_url()` reads config then env var (correct test isolation)
- **Initial migration** (`0001_initial_pa_records.py`): creates `pa_records` table + indexes
- **Second migration** (`0002_add_payer_configs.py`): creates `payer_configs` table
- **`PayerConfig` ORM model** (`models_db.py`): `payer_id` (unique), `display_name`, `rules_json`, `active`, timestamps — multi-tenant payer policy store
- **Payer seed script** (`seeds/load_payer_configs.py`): idempotent upsert from `config/policies/*.json` → `payer_configs` table; runnable as `python -m care_orchestrator.seeds.load_payer_configs`

### Tests

- +39 new tests: `test_ehr_adapters.py` (22), `test_alembic.py` (6), `test_payer_config_db.py` (11)
- Total: **284 passing** (245 → 284)
- Alembic migration round-trip: `upgrade head → downgrade base → upgrade head` verified on SQLite in CI

## [0.6.0] - 2026-03-05

### Added

- **PostgreSQL persistence** (`database.py` + `models_db.py`): SQLAlchemy 2.0 async engine with `PARecord` ORM model; defaults to SQLite (aiosqlite) in dev/test, PostgreSQL (asyncpg) in production via `DATABASE_URL`
- **`RegulatoryDashboard` async methods**: `record_async()`, `find_by_pa_number_async()`, `get_metrics_async()` — DB-backed alongside original sync methods
- **`create_tables()` on startup**: `app.py` lifespan now calls `await create_tables()` so tables are always ready on boot
- **CMS-0057 Patient Access FHIR API** (`patient_access.py`): three mandated endpoints
  - `GET /Patient/{patient_id}/$everything` — patient resource bundle (CMS-0057 § 422.119(b)(1)(i))
  - `GET /ExplanationOfBenefit` — claims data with optional patient filter (§ 422.119(b)(1)(ii))
  - `GET /Coverage` — insurance coverage with optional beneficiary filter (§ 422.119(b)(1)(iii))
- **FHIR R4 Bundle assembler** (`fhir_bundle.py`): `make_bundle()`, `make_eob_entry()`, `make_coverage_entry()` helpers
- `sqlalchemy[asyncio]>=2.0.0` + `asyncpg>=0.30.0` added to core deps; `aiosqlite>=0.20.0` added to dev deps
- `asyncio_mode = "auto"` added to `pytest.ini_options`
- 22 new tests: `test_database.py` (10) + `test_patient_access.py` (12) — total suite now 245 tests

## [0.5.0] - 2026-03-05

### Added

- **FHIR US Core Profile Validator** (`fhir_validator.py`): Rule-based US Core v6.1.0 profile checks for Patient, Condition, ServiceRequest, Procedure — no HAPI server required
- **`FHIRMapper` profile validation**: Every generated resource is now validated against its US Core profile; violations surface as actionable `validation_errors`
- **`POST /fhir/validate` endpoint**: Submit any FHIR resource and receive a FHIR OperationOutcome with profile errors and warnings
- **SMART on FHIR Authorization Server Stub** (`smart_auth.py`): `client_credentials` + `authorization_code` grants, JWT via `python-jose`, opaque token fallback
- **`GET /.well-known/smart-configuration`**: SMART App Launch Framework v2.0 capability discovery
- **`POST /auth/token` + `POST /auth/introspect`**: OAuth 2.0 token issuance + RFC 7662 introspection
- **`require_smart_token` FastAPI dependency**: Opt-in auth enforcement via `SMART_AUTH_ENABLED=true` (default: `false`, backward compatible)
- **`FHIRValidateRequest/Response`** Pydantic schemas in `fhir_schemas.py`
- `python-jose[cryptography]>=3.3.0` dependency added
- 26 new tests across `test_fhir_validator.py` (17) and `test_smart_auth.py` (13) — total suite now 223 tests

## [0.4.0] - 2026-03-05

### Added

- **FastAPI FHIR REST server** (`app.py`): `POST /prior-authorization`, `GET /prior-authorization/{pa_number}`, `POST /coding/validate`, `GET /compliance/metrics`
- **FHIR-shaped Pydantic schemas** (`fhir_schemas.py`): `PARequest`, `PAResponse`, `CodingValidateRequest/Response`, `ComplianceMetricsResponse`, `OperationOutcome`
- **CMS/NPI MCP Client** (`cms_mcp_client.py`): Live CMS coverage + NPI registry via Anthropic's public MCP servers; TTL cache + graceful fallback
- **PolicyEngine CMS fallback** (`check_requirements_with_cms_fallback`): Falls back to live CMS data when payer not in local JSON config (`USE_CMS_MCP=true`)
- **`RegulatoryDashboard.find_by_pa_number()`**: Status lookup by PA number for GET endpoint
- **`claude.json`**: Anthropic Claude Code skill manifest for healthcare marketplace packaging
- CORS middleware and global FHIR OperationOutcome error handler
- `fastapi>=0.115`, `uvicorn[standard]>=0.32`, `httpx>=0.27` dependencies added
- 25 new tests across `test_api.py` (14) and `test_cms_mcp_client.py` (11) — total suite now 197 tests

## [0.3.0] - 2026-03-05

### Added

- **Agent Framework** — `BaseAgent` abstract class + `AgentRegistry` with task routing and agent chaining
- **Coding Agent** — validates CPT/ICD-10 pairings, bundling conflicts, modifier requirements
- **Eligibility Agent** — verifies insurance coverage per CPT code against payer policies
- **Prior Auth Agent** — wraps Phase 2 PA workflow as a chainable pipeline agent
- **Claims Agent** — assembles CMS-1500 claims, validates pre-conditions, routes denials
- **RCM Orchestrator** — end-to-end pipeline: Coding → Eligibility → Prior Auth → Claims
- **Regulatory Dashboard** — compliance metrics aggregation, CMS-ready report generation
- 12 new domain models (`RCMStage`, `AgentTask`, `AgentResult`, `ClaimLine`, `ClaimData`, `RCMContext`, `RCMResult`, `ComplianceMetrics`)
- 3 new MCP tools: `run_rcm_pipeline`, `get_compliance_metrics`, `validate_coding`
- 62 new tests across 6 test files (176 total, up from 114)

## [0.2.0] - 2026-03-05

### Added

- **Payer Policy Engine** (`policy_engine.py`): Loads payer-specific PA rules from JSON configs, checks requirements, auto-approve matching
- **Payer policy configs** (`config/policies/`): Commercial generic, Medicare, Medicaid — with CPT/ICD-10 rules, documentation requirements, review timelines
- **Medical Necessity Evaluator** (`medical_necessity.py`): LLM-powered evaluation against payer-specific criteria with structured XML parsing
- **Prior Auth Generator** (`prior_auth.py`): End-to-end orchestrator chaining audit → policy → necessity → FHIR → PA assembly
- **Appeal Letter Generator** (`appeal_generator.py`): Drafts initial, peer-to-peer, and external review appeals with clinical justification + policy citations
- **10 new domain models** (`models.py`): `CoverageCriteria`, `PriorAuthRequirement`, `PayerPolicy`, `NecessityDecision`, `PriorAuthRequest`, `PriorAuthResult`, `AppealLetter`, and related enums
- **3 new MCP tools** (`mcp_server.py`): `submit_prior_auth`, `evaluate_medical_necessity`, `generate_appeal`
- **53 new tests**: Policy engine (22), medical necessity (13), prior auth (10), appeal generator (12) — total suite now 114 tests

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
