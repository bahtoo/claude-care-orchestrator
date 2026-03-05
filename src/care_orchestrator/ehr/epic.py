"""
Epic FHIR R4 Adapter.

Epic Backend Services authentication:
  1. Generate RSA-2048 key pair (once)
  2. Register public key on fhir.epic.com
  3. At runtime: build a JWT client assertion signed with the private key
  4. POST the signed JWT to Epic's token endpoint
  5. Receive a Bearer token → use for FHIR API calls

When no private key is configured the adapter falls back to the open
sandbox (https://open.epic.com) in unauthenticated mode for development.

Sandbox: https://fhir.epic.com/interconnect-amcurr-oauth2/api/FHIR/R4
Registration: https://fhir.epic.com (non-production app)
"""

from __future__ import annotations

import os
import time
import uuid
from typing import Any

import httpx

from care_orchestrator.ehr.base import EHRAdapter
from care_orchestrator.logging_config import logger

# Try python-jose (already a dependency)
try:
    from jose import jwt as jose_jwt

    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False


class EpicAdapter(EHRAdapter):
    """
    Epic FHIR R4 backend services adapter.

    Args:
        base_url:         Epic FHIR base URL
        token_url:        Epic OAuth 2.0 token endpoint
        client_id:        Epic app client ID (from fhir.epic.com)
        private_key_path: Path to RSA-2048 PEM private key file
    """

    def __init__(
        self,
        base_url: str,
        token_url: str = "",
        client_id: str = "",
        private_key_path: str = "",
        timeout: float = 30.0,
    ) -> None:
        super().__init__(
            base_url=base_url,
            client_id=client_id,
            token_url=token_url,
            timeout=timeout,
        )
        self.private_key_path = private_key_path
        self._private_key: str | None = None

    def _load_private_key(self) -> str | None:
        """Load RSA PEM key from disk (cached after first read)."""
        if self._private_key:
            return self._private_key
        if not self.private_key_path or not os.path.exists(self.private_key_path):
            return None
        with open(self.private_key_path) as f:
            self._private_key = f.read()
        return self._private_key

    def _build_jwt_assertion(self, private_key: str) -> str:
        """
        Build a signed JWT client assertion per Epic's backend services spec.

        Claims:
            iss / sub: client_id
            aud:       token_url
            jti:       unique per request
            exp:       now + 4 minutes (Epic max is 5 min)
        """
        if not _JOSE_AVAILABLE:
            raise RuntimeError(
                "python-jose is required for Epic JWT auth — "
                "install: pip install python-jose[cryptography]"
            )
        now = int(time.time())
        payload = {
            "iss": self.client_id,
            "sub": self.client_id,
            "aud": self.token_url,
            "jti": str(uuid.uuid4()),
            "iat": now,
            "exp": now + 240,
        }
        return jose_jwt.encode(payload, private_key, algorithm="RS256")

    async def _fetch_token(self) -> tuple[str, int]:
        """
        Exchange RSA-signed JWT assertion for an Epic Bearer token.

        Falls back to open sandbox mode (no auth) when no private key
        is configured — useful for CI and development.
        """
        private_key = self._load_private_key()

        if not private_key or not self.token_url or not self.client_id:
            # Open sandbox fallback
            logger.info("EpicAdapter: no key configured — open sandbox mode (no auth)")
            return ("open-sandbox", 3600)

        logger.info("EpicAdapter: fetching access token via JWT assertion")
        assertion = self._build_jwt_assertion(private_key)

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.post(
                self.token_url,
                data={
                    "grant_type": "client_credentials",
                    "client_assertion_type": (
                        "urn:ietf:params:oauth:client-assertion-type:jwt-bearer"
                    ),
                    "client_assertion": assertion,
                    "scope": "system/Patient.read system/Condition.read system/ServiceRequest.read",
                },
                headers={"Content-Type": "application/x-www-form-urlencoded"},
            )
        resp.raise_for_status()
        body = resp.json()
        return body["access_token"], int(body.get("expires_in", 300))

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """Override to skip auth header in open sandbox mode."""
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/fhir+json"}

        if self.token_url and self.client_id and self._load_private_key():
            token = await self.get_token()
            if token != "open-sandbox":  # noqa: S105
                headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers, params=params or {})

        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()
