"""
EHR Adapter base class.

All EHR adapters implement this interface, enabling the care orchestrator
to query any supported EHR system for patient data without knowing the
underlying authentication or API details.

Concrete implementations live in the same package:
  oracle_health.py — Oracle Health / Cerner
  epic.py          — Epic Systems
  intersystems.py  — InterSystems IRIS / HealthShare
  veradigm.py      — Veradigm (AllScripts)
"""

from __future__ import annotations

import time
from abc import ABC, abstractmethod
from typing import Any

import httpx

from care_orchestrator.logging_config import logger


class EHRAdapter(ABC):
    """
    Abstract base for EHR FHIR R4 adapters.

    Each adapter handles its own OAuth 2.0 token acquisition and caching.
    Subclasses only need to implement `_get_base_url`, `_build_headers`, and
    the data methods — the token lifecycle is managed here.
    """

    def __init__(
        self,
        base_url: str,
        client_id: str = "",
        client_secret: str = "",
        token_url: str = "",
        timeout: float = 30.0,
    ) -> None:
        self.base_url = base_url.rstrip("/")
        self.client_id = client_id
        self.client_secret = client_secret
        self.token_url = token_url
        self.timeout = timeout
        self._token: str | None = None
        self._token_expires_at: float = 0.0

    # ------------------------------------------------------------------
    # Token management (sync fast path + async refresh)
    # ------------------------------------------------------------------

    def _token_valid(self) -> bool:
        return bool(self._token) and time.time() < self._token_expires_at - 30

    async def get_token(self) -> str:
        """Return a valid Bearer token, refreshing if expired."""
        if self._token_valid():
            return self._token  # type: ignore[return-value]
        self._token, ttl = await self._fetch_token()
        self._token_expires_at = time.time() + ttl
        logger.info(f"{self.__class__.__name__}: token refreshed (ttl={ttl}s)")
        return self._token

    @abstractmethod
    async def _fetch_token(self) -> tuple[str, int]:
        """
        Fetch a fresh access token.

        Returns:
            (access_token, expires_in_seconds)
        """

    # ------------------------------------------------------------------
    # HTTP helpers
    # ------------------------------------------------------------------

    async def _get(self, path: str, params: dict | None = None) -> dict[str, Any]:
        """
        Perform an authenticated FHIR GET request.

        If the adapter has no token_url (open sandbox) the request is
        sent without an Authorization header.
        """
        url = f"{self.base_url}/{path.lstrip('/')}"
        headers = {"Accept": "application/fhir+json"}

        if self.token_url:
            token = await self.get_token()
            headers["Authorization"] = f"Bearer {token}"

        async with httpx.AsyncClient(timeout=self.timeout) as client:
            resp = await client.get(url, headers=headers, params=params or {})

        if resp.status_code == 404:
            return {}
        resp.raise_for_status()
        return resp.json()

    # ------------------------------------------------------------------
    # FHIR data methods
    # ------------------------------------------------------------------

    async def get_patient(self, patient_id: str) -> dict[str, Any]:
        """Fetch a FHIR Patient resource by ID."""
        return await self._get(f"Patient/{patient_id}")

    async def get_conditions(self, patient_id: str) -> list[dict[str, Any]]:
        """Fetch all Conditions for a patient."""
        bundle = await self._get("Condition", params={"patient": patient_id})
        return _bundle_entries(bundle)

    async def search_service_requests(self, patient_id: str) -> list[dict[str, Any]]:
        """Fetch all ServiceRequests (prior auth candidates) for a patient."""
        bundle = await self._get("ServiceRequest", params={"patient": patient_id})
        return _bundle_entries(bundle)

    async def get_coverage(self, patient_id: str) -> list[dict[str, Any]]:
        """Fetch Coverage resources for a patient."""
        bundle = await self._get("Coverage", params={"patient": patient_id})
        return _bundle_entries(bundle)

    async def health_check(self) -> bool:
        """Return True if the FHIR server metadata endpoint responds."""
        try:
            meta = await self._get("metadata")
            return meta.get("resourceType") == "CapabilityStatement"
        except Exception:  # noqa: BLE001
            return False


# ------------------------------------------------------------------
# Helper
# ------------------------------------------------------------------


def _bundle_entries(bundle: dict[str, Any]) -> list[dict[str, Any]]:
    """Extract resource dicts from a FHIR Bundle."""
    if not bundle:
        return []
    return [e["resource"] for e in bundle.get("entry", []) if "resource" in e]
