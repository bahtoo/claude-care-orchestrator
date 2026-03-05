"""
InterSystems IRIS for Health / HealthShare FHIR R4 Adapter.

Auth: SMART on FHIR client_credentials OAuth 2.0
Default sandbox: InterSystems cloud FHIR server

Developer resources:
  https://learning.intersystems.com/
  https://github.com/intersystems-community/iris-fhir-server-demo
"""

from __future__ import annotations

import httpx

from care_orchestrator.ehr.base import EHRAdapter
from care_orchestrator.logging_config import logger


class InterSystemsAdapter(EHRAdapter):
    """
    InterSystems IRIS for Health FHIR R4 adapter.

    Uses SMART client_credentials grant. When token_url or credentials
    are absent the adapter operates without an Authorization header
    (useful for open IRIS demo servers).
    """

    async def _fetch_token(self) -> tuple[str, int]:
        """Exchange client_credentials for an IRIS access token."""
        if not self.token_url or not self.client_id:
            logger.info("InterSystemsAdapter: no auth configured — open mode")
            return ("open-sandbox", 3600)

        logger.info("InterSystemsAdapter: fetching access token")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "system/Patient.read system/Condition.read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        resp.raise_for_status()
        body = resp.json()
        return body["access_token"], int(body.get("expires_in", 300))
