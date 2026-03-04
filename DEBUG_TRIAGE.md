# Cross-Functional Triage & Debugging

This document tracks how we "catch the balls" across Engineering, Policy, and Research.

| Issue Type              | Triage Owner        | Strategy                                                                 |
| :---------------------- | :------------------ | :----------------------------------------------------------------------- |
| **Model Gaps**          | Research/Applied AI | Identify where Claude 3.5 falls short in clinical reasoning.             |
| **HIPAA Leakage**       | Safety/Legal        | Immediate halt and refinement of the `regulatory_guardrails.xml`.        |
| **Integration Failure** | Engineering         | Review MCP (Model Context Protocol) connection to Epic/Cerner endpoints. |
| **Market Friction**     | Product Lead        | Translate partner feedback into new feature priorities for the roadmap.  |

### Feedback Loop

When a customer (Payer or Provider) reports a friction point, the DRI (Product Lead) logs the "Product Feature Requirement" here before moving it to the Engineering backlog.
