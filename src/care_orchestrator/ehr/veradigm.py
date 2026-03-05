"""
Veradigm (AllScripts) FHIR R4 Adapter.

Auth: SMART on FHIR OAuth 2.0 client_credentials
FHIR version: R4 (DSTU2 dropped June 2025)

Developer portal: https://veradigm.com/veradigm-developer/
Sandbox: https://api.platform.allscripts.com/fhir/r4
"""

from __future__ import annotations

import httpx

from care_orchestrator.ehr.base import EHRAdapter
from care_orchestrator.logging_config import logger


class VeradigmAdapter(EHRAdapter):
    """
    Veradigm (formerly Allscripts) FHIR R4 adapter.

    Uses SMART OAuth 2.0 client_credentials. Falls back to unauthenticated
    mode for open test endpoints.
    """

    async def _fetch_token(self) -> tuple[str, int]:
        """Exchange client_credentials for a Veradigm access token."""
        if not self.token_url or not self.client_id:
            logger.info("VeradigmAdapter: no auth configured — open mode")
            return ("open-sandbox", 3600)

        logger.info("VeradigmAdapter: fetching access token")
        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_id": self.client_id,
                    "client_secret": self.client_secret,
                    "scope": "system/Patient.read system/Condition.read",
                },
                # Veradigm accepts Basic auth as alternative — form body is simpler
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        resp.raise_for_status()
        body = resp.json()
        return body["access_token"], int(body.get("expires_in", 300))
