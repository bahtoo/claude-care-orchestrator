"""
Tests for all four EHR adapters + the registry.

All HTTP calls are mocked via pytest-httpx (or unittest.mock.patch) so
no real sandbox credentials are required for the test suite to pass.
"""

from __future__ import annotations

from unittest.mock import AsyncMock, MagicMock, patch

import pytest

from care_orchestrator.ehr.base import _bundle_entries
from care_orchestrator.ehr.epic import EpicAdapter
from care_orchestrator.ehr.intersystems import InterSystemsAdapter
from care_orchestrator.ehr.oracle_health import OracleHealthAdapter
from care_orchestrator.ehr.registry import get_ehr_adapter
from care_orchestrator.ehr.veradigm import VeradigmAdapter

# ---------------------------------------------------------------------------
# Shared FHIR fixtures
# ---------------------------------------------------------------------------

PATIENT_RESOURCE = {
    "resourceType": "Patient",
    "id": "12724066",
    "name": [{"use": "official", "family": "Smith", "given": ["John"]}],
}

CONDITION_BUNDLE = {
    "resourceType": "Bundle",
    "type": "searchset",
    "total": 1,
    "entry": [
        {
            "resource": {
                "resourceType": "Condition",
                "id": "cond-1",
                "subject": {"reference": "Patient/12724066"},
            }
        }
    ],
}

EMPTY_BUNDLE = {"resourceType": "Bundle", "type": "searchset", "total": 0, "entry": []}


# ---------------------------------------------------------------------------
# Helper: mock httpx response
# ---------------------------------------------------------------------------


def _mock_response(json_body: dict, status_code: int = 200):
    mock = MagicMock()
    mock.status_code = status_code
    mock.json.return_value = json_body
    mock.raise_for_status = MagicMock()
    return mock


# ---------------------------------------------------------------------------
# _bundle_entries unit tests
# ---------------------------------------------------------------------------


class TestBundleEntries:
    def test_extracts_resources(self):
        resources = _bundle_entries(CONDITION_BUNDLE)
        assert len(resources) == 1
        assert resources[0]["resourceType"] == "Condition"

    def test_empty_bundle(self):
        assert _bundle_entries(EMPTY_BUNDLE) == []

    def test_empty_dict(self):
        assert _bundle_entries({}) == []

    def test_skips_entries_without_resource(self):
        bundle = {"entry": [{"fullUrl": "http://example.com"}]}
        assert _bundle_entries(bundle) == []


# ---------------------------------------------------------------------------
# Token caching
# ---------------------------------------------------------------------------


class TestTokenCaching:
    @pytest.mark.asyncio
    async def test_token_cached_on_second_call(self):
        adapter = OracleHealthAdapter(base_url="http://test", token_url="http://token")
        adapter._fetch_token = AsyncMock(return_value=("tok123", 3600))

        t1 = await adapter.get_token()
        t2 = await adapter.get_token()

        assert t1 == t2 == "tok123"
        adapter._fetch_token.assert_called_once()  # only fetched once

    @pytest.mark.asyncio
    async def test_expired_token_is_refreshed(self):
        adapter = OracleHealthAdapter(base_url="http://test", token_url="http://token")
        adapter._fetch_token = AsyncMock(return_value=("fresh", 3600))

        # Force expiry
        adapter._token = "old"  # noqa: S105
        adapter._token_expires_at = 0  # already expired

        token = await adapter.get_token()
        assert token == "fresh"  # noqa: S105


# ---------------------------------------------------------------------------
# Oracle Health Adapter
# ---------------------------------------------------------------------------


class TestOracleHealthAdapter:
    @pytest.mark.asyncio
    async def test_open_sandbox_returns_sentinel(self):
        """Without token_url, _fetch_token returns sentinel without HTTP call."""
        adapter = OracleHealthAdapter(base_url="http://test", token_url="")
        token, ttl = await adapter._fetch_token()
        assert token == "open-sandbox"
        assert ttl == 3600

    @pytest.mark.asyncio
    async def test_secure_sandbox_posts_credentials(self):
        token_resp = {"access_token": "cerner-tok", "expires_in": 300}
        mock_resp = _mock_response(token_resp)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.post = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            adapter = OracleHealthAdapter(
                base_url="http://test",
                token_url="http://token",
                client_id="cid",
                client_secret="csec",
            )
            token, ttl = await adapter._fetch_token()

        assert token == "cerner-tok"  # noqa: S105
        assert ttl == 300

    @pytest.mark.asyncio
    async def test_get_patient_no_auth(self):
        """Open sandbox: get_patient should not set Authorization header."""
        mock_resp = _mock_response(PATIENT_RESOURCE)

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            adapter = OracleHealthAdapter(
                base_url="https://fhir-open.cerner.com/r4/tenant",
                token_url="",
            )
            patient = await adapter.get_patient("12724066")

        assert patient["resourceType"] == "Patient"

    @pytest.mark.asyncio
    async def test_404_returns_empty_dict(self):
        mock_resp = _mock_response({}, status_code=404)
        mock_resp.raise_for_status = MagicMock()

        with patch("httpx.AsyncClient") as mock_client_cls:
            mock_client = AsyncMock()
            mock_client.get = AsyncMock(return_value=mock_resp)
            mock_client_cls.return_value.__aenter__ = AsyncMock(return_value=mock_client)
            mock_client_cls.return_value.__aexit__ = AsyncMock(return_value=False)

            adapter = OracleHealthAdapter(base_url="http://test", token_url="")
            result = await adapter.get_patient("nonexistent")

        assert result == {}


# ---------------------------------------------------------------------------
# Epic Adapter
# ---------------------------------------------------------------------------


class TestEpicAdapter:
    @pytest.mark.asyncio
    async def test_no_key_returns_open_sandbox_sentinel(self):
        adapter = EpicAdapter(
            base_url="http://test",
            token_url="http://token",
            client_id="cid",
            private_key_path="",  # no key
        )
        token, ttl = await adapter._fetch_token()
        assert token == "open-sandbox"  # noqa: S105
        assert ttl == 3600

    def test_build_jwt_assertion_shape(self, tmp_path):
        """JWT assertion should have correct claims structure."""
        from cryptography.hazmat.primitives import serialization
        from cryptography.hazmat.primitives.asymmetric import rsa
        from jose import jwt

        private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        pem = private_key.private_bytes(
            encoding=serialization.Encoding.PEM,
            format=serialization.PrivateFormat.TraditionalOpenSSL,
            encryption_algorithm=serialization.NoEncryption(),
        )
        key_file = tmp_path / "test.pem"
        key_file.write_bytes(pem)

        adapter = EpicAdapter(
            base_url="http://base",
            token_url="http://token",
            client_id="test-client",
            private_key_path=str(key_file),
        )
        assertion = adapter._build_jwt_assertion(pem.decode())
        claims = jwt.get_unverified_claims(assertion)
        assert claims["iss"] == "test-client"
        assert claims["aud"] == "http://token"
        assert "jti" in claims
        assert "exp" in claims


# ---------------------------------------------------------------------------
# InterSystems Adapter
# ---------------------------------------------------------------------------


class TestInterSystemsAdapter:
    @pytest.mark.asyncio
    async def test_no_token_url_returns_sentinel(self):
        adapter = InterSystemsAdapter(base_url="http://test", token_url="")
        token, ttl = await adapter._fetch_token()
        assert token == "open-sandbox"

    @pytest.mark.asyncio
    async def test_health_check_true_when_capability_statement(self):
        meta = {"resourceType": "CapabilityStatement", "status": "active"}
        with patch.object(InterSystemsAdapter, "_get", new_callable=AsyncMock, return_value=meta):
            adapter = InterSystemsAdapter(base_url="http://test", token_url="")
            ok = await adapter.health_check()
        assert ok is True

    @pytest.mark.asyncio
    async def test_health_check_false_on_exception(self):
        with patch.object(
            InterSystemsAdapter, "_get", new_callable=AsyncMock, side_effect=Exception("net error")
        ):
            adapter = InterSystemsAdapter(base_url="http://test", token_url="")
            ok = await adapter.health_check()
        assert ok is False


# ---------------------------------------------------------------------------
# Veradigm Adapter
# ---------------------------------------------------------------------------


class TestVeradigmAdapter:
    @pytest.mark.asyncio
    async def test_no_client_id_returns_sentinel(self):
        adapter = VeradigmAdapter(base_url="http://test", token_url="http://token", client_id="")
        token, ttl = await adapter._fetch_token()
        assert token == "open-sandbox"

    @pytest.mark.asyncio
    async def test_get_conditions_returns_list(self):
        with patch.object(
            VeradigmAdapter, "_get", new_callable=AsyncMock, return_value=CONDITION_BUNDLE
        ):
            adapter = VeradigmAdapter(base_url="http://test", token_url="")
            conditions = await adapter.get_conditions("12724066")
        assert len(conditions) == 1
        assert conditions[0]["resourceType"] == "Condition"


# ---------------------------------------------------------------------------
# Registry
# ---------------------------------------------------------------------------


class TestEHRRegistry:
    def test_oracle_health_is_default(self):
        adapter = get_ehr_adapter("oracle_health")
        assert isinstance(adapter, OracleHealthAdapter)

    def test_epic_registry(self):
        adapter = get_ehr_adapter("epic")
        assert isinstance(adapter, EpicAdapter)

    def test_intersystems_registry(self):
        adapter = get_ehr_adapter("intersystems")
        assert isinstance(adapter, InterSystemsAdapter)

    def test_veradigm_registry(self):
        adapter = get_ehr_adapter("veradigm")
        assert isinstance(adapter, VeradigmAdapter)

    def test_unknown_vendor_raises(self):
        with pytest.raises(ValueError, match="Unknown EHR vendor"):
            get_ehr_adapter("nonexistent_ehr")
