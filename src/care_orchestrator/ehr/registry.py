"""
EHR Adapter Registry.

Instantiates the correct EHRAdapter subclass based on environment variables.

Usage:
    from care_orchestrator.ehr.registry import get_ehr_adapter
    adapter = get_ehr_adapter()          # reads EHR_VENDOR from env
    patient = await adapter.get_patient("12724066")

Environment variables:
    EHR_VENDOR          oracle_health | epic | intersystems | veradigm
    EHR_BASE_URL        Override base FHIR URL (optional, sensible defaults per vendor)
    EHR_TOKEN_URL       OAuth 2.0 token endpoint
    EHR_CLIENT_ID       OAuth 2.0 client ID
    EHR_CLIENT_SECRET   OAuth 2.0 client secret (oracle_health, intersystems, veradigm)
    EHR_PRIVATE_KEY_PATH Path to RSA PEM private key file (epic only)
"""

from __future__ import annotations

import os

from care_orchestrator.ehr.base import EHRAdapter

# Default open sandbox URLs (no auth required for read operations)
_DEFAULTS: dict[str, dict[str, str]] = {
    "oracle_health": {
        "base_url": ("https://fhir-open.cerner.com/r4/ec2458f2-1e24-41c8-b71b-0e701af7583d"),
        "token_url": "",
    },
    "epic": {
        "base_url": ("https://fhir.epic.com/interconnect-amcurr-oauth2/api/FHIR/R4"),
        "token_url": ("https://fhir.epic.com/interconnect-amcurr-oauth2/oauth2/token"),
    },
    "intersystems": {
        "base_url": "https://fhirserver.isccloud.io/r4",
        "token_url": "",
    },
    "veradigm": {
        "base_url": "https://api.platform.allscripts.com/fhir/r4",
        "token_url": "https://api.platform.allscripts.com/connect/token",
    },
}


def get_ehr_adapter(vendor: str | None = None) -> EHRAdapter:
    """
    Return the EHR adapter for the configured vendor.

    Args:
        vendor: Override EHR_VENDOR env var. One of:
                oracle_health | epic | intersystems | veradigm

    Raises:
        ValueError: if vendor is unknown.
    """
    vendor = (vendor or os.getenv("EHR_VENDOR", "oracle_health")).lower()
    defaults = _DEFAULTS.get(vendor)
    if defaults is None:
        raise ValueError(f"Unknown EHR vendor: {vendor!r}. Valid options: {list(_DEFAULTS)}")

    base_url = os.getenv("EHR_BASE_URL") or defaults["base_url"]
    token_url = os.getenv("EHR_TOKEN_URL") or defaults["token_url"]
    client_id = os.getenv("EHR_CLIENT_ID", "")
    client_secret = os.getenv("EHR_CLIENT_SECRET", "")
    private_key_path = os.getenv("EHR_PRIVATE_KEY_PATH", "")

    if vendor == "oracle_health":
        from care_orchestrator.ehr.oracle_health import OracleHealthAdapter

        return OracleHealthAdapter(
            base_url=base_url,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    if vendor == "epic":
        from care_orchestrator.ehr.epic import EpicAdapter

        return EpicAdapter(
            base_url=base_url,
            token_url=token_url,
            client_id=client_id,
            private_key_path=private_key_path,
        )

    if vendor == "intersystems":
        from care_orchestrator.ehr.intersystems import InterSystemsAdapter

        return InterSystemsAdapter(
            base_url=base_url,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    if vendor == "veradigm":
        from care_orchestrator.ehr.veradigm import VeradigmAdapter

        return VeradigmAdapter(
            base_url=base_url,
            token_url=token_url,
            client_id=client_id,
            client_secret=client_secret,
        )

    raise ValueError(f"Unhandled vendor: {vendor!r}")  # unreachable
