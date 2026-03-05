"""
SMART on FHIR Authorization Server (Stub).

Implements the SMART App Launch Framework (v2.0) authorization protocol:
  - Client Credentials grant (system-to-system, M2M)
  - Authorization Code grant (EHR launch context)
  - Token introspection
  - SMART capability discovery (/.well-known/smart-configuration)

⚠️  STUB ONLY — for portfolio, integration testing, and EHR sandbox environments.
    Production deployments MUST use a proper IdP (Auth0, Okta, Epic FHIR sandbox).

Environment variables:
    SMART_AUTH_ENABLED : Set to "true" to enforce Bearer token auth on all
                         /prior-authorization and /fhir/validate endpoints.
                         Default: "false" (auth skipped, backward compatible).
    SMART_SECRET       : JWT signing secret. A dev-only default is used if unset.
                         Never use the default in production.
    SMART_TOKEN_TTL    : Access token TTL in seconds. Default: 3600 (1 hour).
"""

from __future__ import annotations

import os
import secrets
import time
from typing import Any

from fastapi import APIRouter, Depends, Form, HTTPException, Request, status
from fastapi.responses import JSONResponse
from fastapi.security import HTTPAuthorizationCredentials, HTTPBearer

from care_orchestrator.logging_config import logger

# ---------------------------------------------------------------------------
# JWT — optional dependency (python-jose)
# ---------------------------------------------------------------------------

try:
    from jose import JWTError
    from jose import jwt as _jose_jwt

    _JOSE_AVAILABLE = True
except ImportError:
    _JOSE_AVAILABLE = False
    logger.warning(
        "python-jose not installed — SMART auth will use opaque token fallback. "
        "Run: pip install 'python-jose[cryptography]'"
    )

# ---------------------------------------------------------------------------
# Configuration
# ---------------------------------------------------------------------------

_SECRET = os.getenv("SMART_SECRET", "dev-only-secret-change-me-in-production")
_TOKEN_TTL = int(os.getenv("SMART_TOKEN_TTL", "3600"))
_ALGORITHM = "HS256"

# Registered demo clients (in-memory — replace with DB in production)
_DEMO_CLIENTS: dict[str, str] = {
    "demo": "demo",
    "care-orchestrator-demo": "care-orchestrator-secret",
}

# In-memory opaque token store (fallback when python-jose not installed)
_OPAQUE_TOKENS: dict[str, dict[str, Any]] = {}


# ---------------------------------------------------------------------------
# Token utilities
# ---------------------------------------------------------------------------


def _issue_jwt(client_id: str, scopes: list[str]) -> str:
    """Issue a signed JWT access token."""
    now = int(time.time())
    payload = {
        "iss": "care-orchestrator",
        "sub": client_id,
        "iat": now,
        "exp": now + _TOKEN_TTL,
        "scope": " ".join(scopes),
        "client_id": client_id,
    }
    return _jose_jwt.encode(payload, _SECRET, algorithm=_ALGORITHM)


def _issue_opaque(client_id: str, scopes: list[str]) -> str:
    """Issue an opaque token (fallback when python-jose unavailable)."""
    token = secrets.token_urlsafe(32)
    _OPAQUE_TOKENS[token] = {
        "sub": client_id,
        "scope": " ".join(scopes),
        "exp": time.time() + _TOKEN_TTL,
        "iat": time.time(),
    }
    return token


def _verify_jwt(token: str) -> dict[str, Any] | None:
    """Verify a JWT and return its payload, or None if invalid."""
    try:
        payload = _jose_jwt.decode(
            token,
            _SECRET,
            algorithms=[_ALGORITHM],
            options={"verify_aud": False},
        )
        return payload
    except JWTError:
        return None


def _verify_opaque(token: str) -> dict[str, Any] | None:
    """Look up an opaque token and return its claims, or None if invalid."""
    claims = _OPAQUE_TOKENS.get(token)
    if claims and claims.get("exp", 0) > time.time():
        return claims
    return None


def issue_token(client_id: str, scopes: list[str]) -> str:
    """Issue a token using the best available method."""
    if _JOSE_AVAILABLE:
        return _issue_jwt(client_id, scopes)
    return _issue_opaque(client_id, scopes)


def verify_token(token: str) -> dict[str, Any] | None:
    """Verify a token and return its claims, or None if invalid/expired."""
    if _JOSE_AVAILABLE:
        return _verify_jwt(token)
    return _verify_opaque(token)


# ---------------------------------------------------------------------------
# FastAPI router
# ---------------------------------------------------------------------------

auth_router = APIRouter(tags=["SMART Auth"])

_bearer_scheme = HTTPBearer(auto_error=False)


@auth_router.get("/.well-known/smart-configuration")
async def smart_configuration() -> JSONResponse:
    """
    SMART on FHIR capability discovery endpoint.

    Returns the server's SMART authorization capabilities per
    the SMART App Launch Framework v2.0 specification.
    """
    config = {
        "issuer": "care-orchestrator",
        "authorization_endpoint": "/auth/authorize",
        "token_endpoint": "/auth/token",
        "introspection_endpoint": "/auth/introspect",
        "grant_types_supported": ["client_credentials", "authorization_code"],
        "scopes_supported": [
            "patient/*.read",
            "system/Patient.read",
            "system/Prior-Auth.write",
            "system/Observation.read",
            "launch/ehr",
            "offline_access",
        ],
        "response_types_supported": ["code"],
        "token_endpoint_auth_methods_supported": ["client_secret_post"],
        "capabilities": [
            "client-public",
            "client-confidential-symmetric",
            "sso-openid-connect",
            "permission-v2",
            "context-ehr-patient",
            "launch-ehr",
        ],
        "code_challenge_methods_supported": ["S256"],
    }
    return JSONResponse(content=config)


@auth_router.post("/auth/token")
async def token_endpoint(
    grant_type: str = Form(...),
    client_id: str = Form(...),
    client_secret: str = Form(...),
    scope: str = Form(default="system/Prior-Auth.write"),
    code: str | None = Form(default=None),
    redirect_uri: str | None = Form(default=None),
) -> JSONResponse:
    """
    OAuth 2.0 Token Endpoint (client_credentials + authorization_code).

    Returns a Bearer access token with the requested scopes.
    Accepted grant types: client_credentials, authorization_code.
    """
    if grant_type not in ("client_credentials", "authorization_code"):
        raise HTTPException(
            status_code=status.HTTP_400_BAD_REQUEST,
            detail={"error": "unsupported_grant_type"},
        )

    # Validate client credentials
    expected_secret = _DEMO_CLIENTS.get(client_id)
    if not expected_secret or not secrets.compare_digest(client_secret, expected_secret):
        logger.warning(f"SMART auth: invalid client credentials for '{client_id}'")
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail={"error": "invalid_client"},
        )

    requested_scopes = scope.split()
    access_token = issue_token(client_id, requested_scopes)

    logger.info(
        f"SMART token issued: client={client_id}, grant={grant_type}, scopes={requested_scopes}"
    )

    return JSONResponse(
        content={
            "access_token": access_token,
            "token_type": "Bearer",
            "expires_in": _TOKEN_TTL,
            "scope": scope,
        }
    )


@auth_router.post("/auth/introspect")
async def introspect(
    token: str = Form(...),
    client_id: str = Form(default=""),
    client_secret: str = Form(default=""),
) -> JSONResponse:
    """
    OAuth 2.0 Token Introspection (RFC 7662).

    Returns active=true with token claims if valid, active=false otherwise.
    """
    claims = verify_token(token)
    if not claims:
        return JSONResponse(content={"active": False})

    return JSONResponse(
        content={
            "active": True,
            "sub": claims.get("sub", ""),
            "scope": claims.get("scope", ""),
            "exp": claims.get("exp", 0),
            "iat": claims.get("iat", 0),
            "iss": claims.get("iss", "care-orchestrator"),
            "client_id": claims.get("client_id", claims.get("sub", "")),
        }
    )


# ---------------------------------------------------------------------------
# Auth dependency (used by protected endpoints)
# ---------------------------------------------------------------------------


async def require_smart_token(
    request: Request,
    credentials: HTTPAuthorizationCredentials | None = Depends(_bearer_scheme),  # noqa: B008
) -> dict[str, Any] | None:
    """
    FastAPI dependency that enforces SMART Bearer token auth.

    If SMART_AUTH_ENABLED=false (default), returns None (no-op).
    If enabled, raises 401 if token is missing or invalid.
    """
    if os.getenv("SMART_AUTH_ENABLED", "false").lower() != "true":
        return None  # auth disabled — pass through

    if not credentials:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Bearer token required",
            headers={"WWW-Authenticate": "Bearer"},
        )

    claims = verify_token(credentials.credentials)
    if not claims:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid or expired token",
            headers={"WWW-Authenticate": "Bearer"},
        )

    logger.info(f"SMART auth: granted access to {request.url.path} for client={claims.get('sub')}")
    return claims
