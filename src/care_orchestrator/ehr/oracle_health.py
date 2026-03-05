"""
Oracle Health (Cerner) FHIR R4 Adapter.

Supports two modes:
  - Open sandbox: no auth — uses fhir-open.cerner.com (default)
  - Secure sandbox: client_credentials via Cerner Authorization Server

Sandbox registration: https://code.cerner.com/developer/smart-on-fhir
"""

from __future__ import annotations

import httpx

from care_orchestrator.ehr.base import EHRAdapter
from care_orchestrator.logging_config import logger


class OracleHealthAdapter(EHRAdapter):
    """
    Oracle Health (Cerner) FHIR R4 adapter.

    When token_url is empty the adapter operates in open-sandbox mode
    (no Authorization header). When client_id + client_secret + token_url
    are provided it uses the SMART backend services client_credentials flow.
    """

    async def _fetch_token(self) -> tuple[str, int]:
        """
        Exchange client_credentials for a Cerner access token.

        Token endpoint: https://authorization.cerner.com/tenants/{tenant}/
                        protocols/oauth2/profiles/smart-v1/token
        """
        if not self.token_url:
            # Open sandbox — no token needed
            return ("open-sandbox", 3600)

        logger.info("OracleHealthAdapter: fetching access token")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "system/Patient.read system/Condition.read system/ServiceRequest.read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        resp.raise_for_status()
        body = resp.json()
        return body["access_token"], int(body.get("expires_in", 300))
