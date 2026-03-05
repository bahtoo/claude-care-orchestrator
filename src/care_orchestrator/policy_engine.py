"""
Payer Policy Engine — loads and queries payer-specific prior auth rules.

Loads payer policies from JSON config files and provides lookup methods
to determine PA requirements for given CPT/ICD-10 code combinations.
"""

from __future__ import annotations

import json
from pathlib import Path

from care_orchestrator.cms_mcp_client import CMSCoverageResult
from care_orchestrator.logging_config import logger
from care_orchestrator.models import PayerPolicy, PriorAuthRequirement


class PolicyEngine:
    """Loads payer policies and checks prior authorization requirements."""

    def __init__(self, policies_dir: str | Path = "config/policies") -> None:
        """
        Initialize the policy engine.

        Args:
            policies_dir: Directory containing payer policy JSON files.
        """
        self._policies_dir = Path(policies_dir)
        self._policies: dict[str, PayerPolicy] = {}
        self._load_policies()

    def _load_policies(self) -> None:
        """Load all payer policy JSON files from the policies directory."""
        if not self._policies_dir.exists():
            logger.warning(f"Policies directory not found: {self._policies_dir}")
            return

        for policy_file in self._policies_dir.glob("*.json"):
            try:
                with open(policy_file, encoding="utf-8") as f:
                    data = json.load(f)
                policy = PayerPolicy.model_validate(data)
                self._policies[policy.payer_id] = policy
                logger.info(
                    f"Loaded payer policy: {policy.payer_name} "
                    f"({len(policy.prior_auth_rules)} rules)"
                )
            except Exception as e:
                logger.error(f"Failed to load policy {policy_file}: {e}")

    @property
    def available_payers(self) -> list[str]:
        """List all loaded payer IDs."""
        return list(self._policies.keys())

    def get_policy(self, payer_id: str) -> PayerPolicy | None:
        """Get a payer policy by ID."""
        return self._policies.get(payer_id)

    def check_requirements(
        self,
        cpt_code: str,
        icd10_codes: list[str],
        payer_id: str,
    ) -> PriorAuthRequirement | None:
        """
        Check if a procedure requires prior authorization for a specific payer.

        Args:
            cpt_code: The CPT procedure code to check.
            icd10_codes: Supporting diagnosis codes.
            payer_id: The payer to check against.

        Returns:
            PriorAuthRequirement if the payer has a rule for this code,
            or a default requirement based on the payer's default policy.
            Returns None if the payer is not found.
        """
        policy = self._policies.get(payer_id)
        if policy is None:
            logger.warning(f"Payer not found: {payer_id}")
            return None

        # Look for a specific rule for this CPT code
        for rule in policy.prior_auth_rules:
            if rule.cpt_code == cpt_code:
                logger.info(
                    f"Policy match: {payer_id} / CPT {cpt_code} → "
                    f"requires_auth={rule.requires_auth}"
                )
                return rule

        # No specific rule — use payer's default
        default_rule = PriorAuthRequirement(
            cpt_code=cpt_code,
            requires_auth=policy.default_requires_auth,
        )
        logger.info(
            f"No specific rule for CPT {cpt_code}, "
            f"using default: requires_auth={policy.default_requires_auth}"
        )
        return default_rule

    def check_auto_approve(
        self,
        cpt_code: str,
        icd10_codes: list[str],
        payer_id: str,
    ) -> bool:
        """
        Check if the diagnosis qualifies for automatic approval.

        Args:
            cpt_code: The CPT code.
            icd10_codes: The patient's diagnosis codes.
            payer_id: The payer to check against.

        Returns:
            True if any diagnosis qualifies for auto-approval.
        """
        requirement = self.check_requirements(cpt_code, icd10_codes, payer_id)
        if requirement is None or not requirement.requires_auth:
            return False

        overlap = set(icd10_codes) & set(requirement.auto_approve_diagnoses)
        if overlap:
            logger.info(f"Auto-approve match: {overlap} for CPT {cpt_code} / {payer_id}")
            return True
        return False

    def check_requirements_with_cms_fallback(
        self,
        cpt_code: str,
        icd10_codes: list[str],
        payer_id: str,
    ) -> PriorAuthRequirement | None:
        """
        Check PA requirements with live CMS fallback.

        1. Tries local JSON policy (fast, no network).
        2. If payer not found AND USE_CMS_MCP=true, imports the async
           CMS MCP client and schedules a coverage lookup synchronously
           via a thread-safe helper.

        Args:
            cpt_code: The CPT procedure code.
            icd10_codes: Supporting diagnosis codes.
            payer_id: Payer ID — falls back to CMS if not in local config.

        Returns:
            PriorAuthRequirement from local policy OR derived from CMS data,
            or None if payer not found and CMS MCP is disabled/unavailable.
        """
        # Fast path — local JSON policy found
        local = self.check_requirements(cpt_code, icd10_codes, payer_id)
        if local is not None:
            return local

        # Slow path — delegate to CMS MCP
        import asyncio
        import os

        if os.getenv("USE_CMS_MCP", "false").lower() != "true":
            logger.info(
                f"Payer '{payer_id}' not in local config; CMS MCP disabled (USE_CMS_MCP=false)"
            )
            return None

        try:
            from care_orchestrator.cms_mcp_client import cms_mcp_client

            logger.info(f"Payer '{payer_id}' not local — querying CMS MCP for CPT {cpt_code}")

            # Run async call in a new event loop if not already in one
            coverage: CMSCoverageResult | None = None
            try:
                loop = asyncio.get_event_loop()
                if loop.is_running():
                    import concurrent.futures

                    with concurrent.futures.ThreadPoolExecutor(max_workers=1) as ex:
                        def _run_coverage() -> CMSCoverageResult | None:
                            return asyncio.run(cms_mcp_client.check_coverage(cpt_code))
                        future = ex.submit(_run_coverage)  # type: ignore
                        coverage = future.result(timeout=6)
                else:
                    coverage = loop.run_until_complete(cms_mcp_client.check_coverage(cpt_code))
            except RuntimeError:
                coverage = asyncio.run(cms_mcp_client.check_coverage(cpt_code))

            if coverage is None:
                return None

            return PriorAuthRequirement(
                cpt_code=cpt_code,
                requires_auth=coverage.requires_auth,
                criteria=[coverage.notes] if coverage.notes else [],
            )

        except Exception as e:
            logger.warning(f"CMS MCP fallback failed: {e}")
            return None


# Module-level convenience instance
policy_engine = PolicyEngine()
