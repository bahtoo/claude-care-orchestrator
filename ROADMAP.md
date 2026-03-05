# Strategic Roadmap: Anthropic Healthcare Vertical (0 → 1)

## Phase 1: Foundation (The Early Momentum) ✅

- **Objective:** HIPAA-Compliant Data Pipelines.
- **Key Result:** 99% accuracy in automated PII redaction across messy clinical transcripts.
- **Feature:** `clinical-to-fhir` mapping tool for rapid EHR integration.

### Implementation Notes (v0.1.0 — 2026-03-05)

- Two-pass PHI detection (deterministic regex + LLM contextual audit)
- FHIR R5 resource generation (Patient, Condition, Procedure, ServiceRequest)
- MCP server for Claude Desktop/Code integration
- 61 automated tests, ruff linting, GitHub Actions CI

## Phase 2: Friction Reduction (Shipping Products) ✅

- **Objective:** The "Payer-Provider Bridge."
- **Key Result:** Reduce Prior Authorization turnaround time from 72 hours to < 5 minutes using Claude's 200k context window.
- **Feature:** Automated Medical Necessity Audit Engine.

### Implementation Notes (v0.2.0 — 2026-03-05)

- Payer Policy Engine with 3 payer configs (Commercial, Medicare, Medicaid)
- LLM-powered Medical Necessity Evaluator with dynamic payer-criteria prompts
- End-to-end Prior Auth Generator orchestrating 5-step workflow
- Appeal Letter Generator supporting initial, peer-to-peer, and external review
- 3 new MCP tools, 10 new domain models, 53 new tests (114 total)

## Phase 3: Scaling the Vertical (Market Leadership) ✅

- **Objective:** Regulatory and Policy Leadership.
- **Key Result:** Establishing Anthropic as the "Voice of AI" for HHS and CMS regulatory readiness.
- **Feature:** Multi-agent orchestration for complex Hospital Revenue Cycle Management (RCM).

### Implementation Notes (v0.3.0 — 2026-03-05)

- Agent framework: BaseAgent ABC + AgentRegistry with chaining
- 4 specialized RCM agents: Coding, Eligibility, Prior Auth, Claims
- End-to-end RCM Orchestrator with compliance audit pre-pass
- Regulatory Dashboard with CMS-ready report generation
- 9 MCP tools total, 176 automated tests

## Phase 4: FHIR API Platform (Deployable Product) ✅

- **Objective:** Turn the pipeline into a deployable, publicly consumable FHIR-compliant API.
- **Key Result:** REST API satisfying CMS-0057 prior authorization mandate (2026/2027 deadlines).
- **Feature:** FastAPI FHIR server + Claude Code skill packaging.

### Implementation Notes (v0.4.0 — 2026-03-05)

- 4 FHIR REST endpoints: POST/GET prior-authorization, POST coding/validate, GET compliance/metrics
- CMS/NPI live data via Anthropic's public MCP servers (opt-in, TTL-cached)
- PolicyEngine extended with live CMS fallback (`USE_CMS_MCP=true`)
- `claude.json` skill manifest for Anthropic healthcare marketplace
- 197 automated tests (25 new), ruff clean

## Phase 5: Interoperability Layer ✅

- **Objective:** Make the API credible to the FHIR interoperability community.
- **Key Result:** US Core profile validation + SMART on FHIR authorization protocol.
- **Feature:** Resource validation against US Core v6.1.0 + EHR launch context stub.

### Implementation Notes (v0.5.0 — 2026-03-05)

- Rule-based US Core profile validator for 4 resource types (no HAPI FHIR server needed)
- FHIRMapper now validates every generated resource; profile violations surface as actionable errors
- POST /fhir/validate endpoint with OperationOutcome response
- SMART on FHIR auth: JWT (python-jose), discovery, introspection, opt-in enforcement
- 223 automated tests (26 new), ruff clean

## Phase 6: Production Hardening (Next)

- **Objective:** Bridge from demo to production-ready deployment.
- **Candidates:**
  - PostgreSQL-backed PA record store (replace in-memory dashboard)
  - Patient Access FHIR API (CMS-0057 Jan 2027 mandate)
  - Epic/Cerner FHIR sandbox integration (SMART EHR launch)
  - Multi-tenant payer configuration
