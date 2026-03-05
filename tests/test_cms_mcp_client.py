"""
Tests for the CMS MCP client.

All network calls are mocked — no real HTTP requests made.
Tests cover: coverage hit, coverage miss, NPI valid, NPI invalid,
timeout fallback, error fallback, and cache behaviour.
"""

import asyncio
import json
from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from care_orchestrator.cms_mcp_client import CMSMCPClient


@pytest.fixture
def enabled_client(monkeypatch):
    """CMSMCPClient with USE_CMS_MCP=true."""
    monkeypatch.setenv("USE_CMS_MCP", "true")
    client = CMSMCPClient(timeout=2.0)
    return client


@pytest.fixture
def disabled_client(monkeypatch):
    """CMSMCPClient with USE_CMS_MCP=false (default)."""
    monkeypatch.setenv("USE_CMS_MCP", "false")
    return CMSMCPClient()


def _mock_response(data: dict) -> MagicMock:
    """Build a mock httpx response wrapping JSON-RPC result."""
    resp = MagicMock()
    resp.raise_for_status = MagicMock()
    resp.json.return_value = {
        "jsonrpc": "2.0",
        "id": 1,
        "result": {"content": [{"text": json.dumps(data)}]},
    }
    return resp


class TestCMSCoverage:
    def test_disabled_returns_none(self, disabled_client):
        result = asyncio.run(disabled_client.check_coverage("73221"))
        assert result is None

    def test_coverage_hit(self, enabled_client):
        mock_resp = _mock_response(
            {
                "covered": True,
                "coverage_type": "LCD",
                "requires_prior_auth": True,
                "notes": "Requires MRI indication",
            }
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            result = asyncio.run(enabled_client.check_coverage("73221"))
        assert result is not None
        assert result.covered is True
        assert result.requires_auth is True
        assert result.coverage_type == "LCD"

    def test_coverage_miss(self, enabled_client):
        mock_resp = _mock_response(
            {
                "covered": False,
                "coverage_type": "unknown",
                "requires_prior_auth": False,
                "notes": "",
            }
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            result = asyncio.run(enabled_client.check_coverage("99999"))
        assert result is not None
        assert result.covered is False

    def test_timeout_returns_none(self, enabled_client):
        import httpx

        with patch(
            "httpx.AsyncClient.post",
            new=AsyncMock(side_effect=httpx.TimeoutException("timeout")),
        ):
            result = asyncio.run(enabled_client.check_coverage("73221"))
        assert result is None

    def test_result_cached(self, enabled_client):
        mock_resp = _mock_response(
            {
                "covered": True,
                "coverage_type": "NCD",
                "requires_prior_auth": False,
                "notes": "",
            }
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)) as mock_post:
            asyncio.run(enabled_client.check_coverage("73721"))
            asyncio.run(enabled_client.check_coverage("73721"))  # second call
        # Should only hit the network once
        assert mock_post.call_count == 1


class TestNPILookup:
    def test_disabled_returns_none(self, disabled_client):
        result = asyncio.run(disabled_client.validate_npi("1234567890"))
        assert result is None

    def test_npi_valid(self, enabled_client):
        mock_resp = _mock_response(
            {
                "valid": True,
                "provider_name": "Dr. Jane Smith",
                "specialty": "Orthopedic Surgery",
                "state": "CA",
            }
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)):
            result = asyncio.run(enabled_client.validate_npi("1234567890"))
        assert result is not None
        assert result.valid is True
        assert result.provider_name == "Dr. Jane Smith"

    def test_invalid_npi_format(self, enabled_client):
        result = asyncio.run(enabled_client.validate_npi("123"))  # too short
        assert result is not None
        assert result.valid is False

    def test_http_error_returns_none(self, enabled_client):
        import httpx

        with patch(
            "httpx.AsyncClient.post",
            new=AsyncMock(side_effect=httpx.HTTPError("server error")),
        ):
            result = asyncio.run(enabled_client.validate_npi("1234567890"))
        assert result is None


class TestCacheClearing:
    def test_clear_cache(self, enabled_client):
        mock_resp = _mock_response(
            {"covered": True, "coverage_type": "LCD", "requires_prior_auth": True, "notes": ""}
        )
        with patch("httpx.AsyncClient.post", new=AsyncMock(return_value=mock_resp)) as mock_post:
            asyncio.run(enabled_client.check_coverage("73221"))
            enabled_client.clear_cache()
            asyncio.run(enabled_client.check_coverage("73221"))
        # Both calls should hit network since cache was cleared
        assert mock_post.call_count == 2
