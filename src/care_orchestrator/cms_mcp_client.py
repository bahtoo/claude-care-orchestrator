"""
CMS Coverage and NPI Registry MCP client.

Provides a lightweight async client that calls Anthropic's public MCP
servers for live CMS LCD/NCD coverage lookups and NPI provider validation.

Usage:
    client = CMSMCPClient()
    coverage = await client.check_coverage("73221")
    provider = await client.validate_npi("1234567890")

Enable by setting USE_CMS_MCP=true in your environment.
Falls back gracefully (returns None) on any network error or timeout.
"""

from __future__ import annotations

import os
import time
from dataclasses import dataclass
from typing import cast

import httpx

from care_orchestrator.logging_config import logger

_CachedValue = object  # type alias for cache values

# Public MCP endpoints provided by Anthropic / DeepSense
_CMS_COVERAGE_URL = "https://mcp.deepsense.ai/cms_coverage/mcp"
_NPI_REGISTRY_URL = "https://mcp.deepsense.ai/npi_registry/mcp"

# Cache TTL in seconds (1 hour)
_TTL = 3600


@dataclass
class _CacheEntry:
    value: object
    expires_at: float


@dataclass
class CMSCoverageResult:
    """Result from the CMS coverage MCP lookup."""

    cpt_code: str
    covered: bool
    coverage_type: str  # "LCD" | "NCD" | "unknown"
    requires_auth: bool
    notes: str = ""


@dataclass
class NPIResult:
    """Result from the NPI registry MCP lookup."""

    npi: str
    valid: bool
    provider_name: str = ""
    specialty: str = ""
    state: str = ""


class CMSMCPClient:
    """
    Async client for Anthropic's public healthcare MCP servers.

    All methods return None on error/timeout — callers must handle
    graceful degradation to local policy data.
    """

    def __init__(self, timeout: float = 5.0) -> None:
        self._timeout = timeout
        self._cache: dict[str, _CacheEntry] = {}
        self._enabled = os.getenv("USE_CMS_MCP", "false").lower() == "true"

        if self._enabled:
            logger.info("CMSMCPClient: live CMS/NPI lookups enabled")
        else:
            logger.info("CMSMCPClient: disabled (set USE_CMS_MCP=true to enable)")

    def _get_cache(self, key: str) -> object | None:
        """Return cached value if still valid."""
        entry = self._cache.get(key)
        if entry and entry.expires_at > time.monotonic():
            return entry.value
        return None

    def _set_cache(self, key: str, value: object) -> None:
        self._cache[key] = _CacheEntry(
            value=value,
            expires_at=time.monotonic() + _TTL,
        )

    async def check_coverage(self, cpt_code: str) -> CMSCoverageResult | None:
        """
        Look up CMS LCD/NCD coverage for a CPT code.

        Returns None if disabled, on network error, or on timeout.
        """
        if not self._enabled:
            return None

        cache_key = f"coverage:{cpt_code}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cast(CMSCoverageResult, cached)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _CMS_COVERAGE_URL,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "check_coverage",
                            "arguments": {"cpt_code": cpt_code},
                        },
                    },
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("result", {}).get("content", [{}])
                result_data = content[0].get("text", {}) if content else {}

                if isinstance(result_data, str):
                    import json

                    result_data = json.loads(result_data)

                result = CMSCoverageResult(
                    cpt_code=cpt_code,
                    covered=bool(result_data.get("covered", False)),
                    coverage_type=str(result_data.get("coverage_type", "unknown")),
                    requires_auth=bool(result_data.get("requires_prior_auth", False)),
                    notes=str(result_data.get("notes", "")),
                )
                self._set_cache(cache_key, result)
                logger.info(
                    f"CMS coverage: CPT {cpt_code} → "
                    f"covered={result.covered}, type={result.coverage_type}"
                )
                return result

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"CMS MCP lookup failed for CPT {cpt_code}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in CMS MCP lookup: {e}")
            return None

    async def validate_npi(self, npi: str) -> NPIResult | None:
        """
        Validate an NPI number against the NPI registry.

        Returns None if disabled, on network error, or on timeout.
        """
        if not self._enabled:
            return None

        if not npi or len(npi) != 10 or not npi.isdigit():
            logger.warning(f"Invalid NPI format: {npi}")
            return NPIResult(npi=npi, valid=False)

        cache_key = f"npi:{npi}"
        cached = self._get_cache(cache_key)
        if cached is not None:
            return cast(NPIResult, cached)

        try:
            async with httpx.AsyncClient(timeout=self._timeout) as client:
                resp = await client.post(
                    _NPI_REGISTRY_URL,
                    json={
                        "jsonrpc": "2.0",
                        "id": 1,
                        "method": "tools/call",
                        "params": {
                            "name": "lookup_npi",
                            "arguments": {"npi": npi},
                        },
                    },
                    headers={"Content-Type": "application/json"},
                )
                resp.raise_for_status()
                data = resp.json()
                content = data.get("result", {}).get("content", [{}])
                result_data = content[0].get("text", {}) if content else {}

                if isinstance(result_data, str):
                    import json

                    result_data = json.loads(result_data)

                result = NPIResult(
                    npi=npi,
                    valid=bool(result_data.get("valid", False)),
                    provider_name=str(result_data.get("provider_name", "")),
                    specialty=str(result_data.get("specialty", "")),
                    state=str(result_data.get("state", "")),
                )
                self._set_cache(cache_key, result)
                logger.info(
                    f"NPI registry: {npi} → valid={result.valid}, name={result.provider_name}"
                )
                return result

        except (httpx.TimeoutException, httpx.HTTPError) as e:
            logger.warning(f"NPI MCP lookup failed for {npi}: {e}")
            return None
        except Exception as e:
            logger.error(f"Unexpected error in NPI MCP lookup: {e}")
            return None

    def clear_cache(self) -> None:
        """Clear the in-memory TTL cache (useful in tests)."""
        self._cache.clear()


# Module-level singleton — disabled by default
cms_mcp_client = CMSMCPClient()
