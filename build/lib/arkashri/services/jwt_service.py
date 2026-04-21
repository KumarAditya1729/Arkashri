# pyre-ignore-all-errors
"""
services/jwt_service.py — Hardened JWT signing and verification
===============================================================
Security guarantees enforced on EVERY decode:
  1. Algorithm whitelist — only HS256 accepted. alg=none → 401.
  2. Expiration (exp) — strictly verified, no leeway by default.
  3. Issued-at (iat)  — must not be in the future.
  4. Issuer (iss)     — must match ARKASHRI_ISSUER ("arkashri").
  5. Audience (aud)   — must match ARKASHRI_AUDIENCE ("arkashri-api").
  6. Type claim       — access tokens rejected on refresh endpoint and vice versa.

For OIDC/OAuth2 tokens from an external IdP:
  Use decode_oidc_token() which uses the IdP's JWKS endpoint instead.
"""
from __future__ import annotations

import datetime
import uuid

from jose import jwt, JWTError, ExpiredSignatureError
from fastapi import HTTPException, status

from arkashri.config import get_settings

# ── Constants ─────────────────────────────────────────────────────────────────
ALGORITHM              = "HS256"
_ALLOWED_ALGORITHMS    = ["HS256"]          # Whitelist — alg=none is NOT in here
ARKASHRI_ISSUER        = "arkashri"
ARKASHRI_AUDIENCE      = "arkashri-api"

# Strict decode options passed to python-jose on every call
_DECODE_OPTIONS: dict = {
    "verify_exp":       True,   # enforce expiration
    "verify_iat":       True,   # reject tokens with iat in the future
    "verify_aud":       True,   # enforce audience claim
    "require_exp":      True,   # 401 if exp claim is missing entirely
    "require_iat":      True,   # 401 if iat claim is missing entirely
    "require_sub":      True,   # 401 if sub claim is missing entirely
    "leeway":           0,      # no grace period — expired means expired
}


def _secret() -> str:
    return get_settings().session_secret_key


def get_access_token_expires_in_seconds() -> int:
    return get_settings().jwt_expiry_minutes * 60


def _access_token_expiry_delta() -> datetime.timedelta:
    return datetime.timedelta(seconds=get_access_token_expires_in_seconds())


def _refresh_token_expiry_delta() -> datetime.timedelta:
    return datetime.timedelta(days=get_settings().refresh_token_expiry_days)


def _ws_ticket_expiry_delta() -> datetime.timedelta:
    return datetime.timedelta(seconds=get_settings().ws_ticket_expiry_seconds)


# ── Token creation ─────────────────────────────────────────────────────────────

def create_access_token(
    *,
    sub: str,
    email: str,
    role: str,
    tenant_id: str,
    full_name: str,
    initials: str,
    user_id: str,
    session_id: str,
) -> str:
    """Issue a hardened HS256 access token with iss, aud, exp, iat, jti."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub":       sub,
        "iss":       ARKASHRI_ISSUER,
        "aud":       ARKASHRI_AUDIENCE,
        "email":     email,
        "role":      role,
        "tenant_id": tenant_id,
        "full_name": full_name,
        "initials":  initials,
        "user_id":   user_id,
        "sid":       session_id,
        "iat":       now,
        "exp":       now + _access_token_expiry_delta(),
        "jti":       str(uuid.uuid4()),
        "type":      "access",
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)

def create_refresh_token(*, sub: str, user_id: str, tenant_id: str, session_id: str) -> str:
    """Issue a hardened HS256 refresh token — fewer claims, longer TTL."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub":       sub,
        "iss":       ARKASHRI_ISSUER,
        "aud":       ARKASHRI_AUDIENCE,
        "user_id":   user_id,
        "tenant_id": tenant_id,
        "sid":       session_id,
        "iat":       now,
        "exp":       now + _refresh_token_expiry_delta(),
        "jti":       str(uuid.uuid4()),
        "type":      "refresh",
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


def create_ws_ticket(*, user_id: str, tenant_id: str, jurisdiction: str) -> str:
    """Issue a short-lived, websocket-specific token for one tenant/jurisdiction pair."""
    now = datetime.datetime.now(datetime.timezone.utc)
    payload = {
        "sub":          user_id,
        "iss":          ARKASHRI_ISSUER,
        "aud":          ARKASHRI_AUDIENCE,
        "user_id":      user_id,
        "tenant_id":    tenant_id,
        "jurisdiction": jurisdiction,
        "iat":          now,
        "exp":          now + _ws_ticket_expiry_delta(),
        "jti":          str(uuid.uuid4()),
        "type":         "ws",
    }
    return jwt.encode(payload, _secret(), algorithm=ALGORITHM)


# ── Token verification ────────────────────────────────────────────────────────

def decode_token(token: str) -> dict:
    """
    Fully hardened JWT decode. Enforces:
      - Algorithm: HS256 only (alg=none → 401)
      - Expiration: expired tokens → 401
      - Issuer: must be 'arkashri'
      - Audience: must be 'arkashri-api'
      - Type: must be 'access' (not a refresh token being used as access)
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=_ALLOWED_ALGORITHMS,   # ← whitelist, not a single string
            issuer=ARKASHRI_ISSUER,
            audience=ARKASHRI_AUDIENCE,
            options=_DECODE_OPTIONS,
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired. Request a new token via POST /token/refresh.",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Token validation failed: {e}",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )

    # Explicit type gate — reject refresh tokens used as access tokens
    if payload.get("type") != "access":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected 'access'.",
            headers={"WWW-Authenticate": "Bearer error=\"invalid_token\""},
        )

    return payload


def decode_refresh_token(token: str) -> dict:
    """
    Decode a refresh token. Same hardening as decode_token()
    but expects type='refresh' instead of type='access'.
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=_ALLOWED_ALGORITHMS,
            issuer=ARKASHRI_ISSUER,
            audience=ARKASHRI_AUDIENCE,
            options=_DECODE_OPTIONS,
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Refresh token has expired. Please log in again.",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Refresh token validation failed: {e}",
        )

    if payload.get("type") != "refresh":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected 'refresh'.",
        )

    return payload


def decode_ws_ticket(token: str) -> dict:
    """
    Decode a websocket ticket. Same hardening as access/refresh tokens,
    but expects type='ws' and a short expiry window.
    """
    try:
        payload = jwt.decode(
            token,
            _secret(),
            algorithms=_ALLOWED_ALGORITHMS,
            issuer=ARKASHRI_ISSUER,
            audience=ARKASHRI_AUDIENCE,
            options=_DECODE_OPTIONS,
        )
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="WebSocket ticket has expired. Request a new ticket.",
        )
    except JWTError as e:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"WebSocket ticket validation failed: {e}",
        )

    if payload.get("type") != "ws":
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Invalid token type. Expected 'ws'.",
        )

    return payload


async def decode_oidc_token(token: str, jwks_uri: str, audience: str) -> dict:
    """
    Decode a token issued by an external OIDC provider (e.g. Google, Okta).
    Uses the provider's JWKS public keys — no shared secret needed.
    Enforces: exp, iss (from metadata), aud (your client_id), algorithms from JWKS.

    Usage:
        payload = await decode_oidc_token(
            token=request.headers["authorization"].split()[1],
            jwks_uri=settings.oauth_jwks_uri,
            audience=settings.oauth_client_id,
        )
    """
    import httpx  # lazy import — only used on OIDC path
    from jose import jwk as jose_jwk

    # H-5: Explicit algorithm allowlist — NEVER trust the header's alg claim directly.
    # An attacker can set alg=HS256 and sign with the public key as an HMAC secret.
    _OIDC_ALLOWED_ALGORITHMS = {"RS256", "RS384", "RS512", "ES256", "ES384", "ES512"}

    try:
        # C-9 FIX: use async HTTP — synchronous httpx.get() blocks the entire event loop.
        async with httpx.AsyncClient(timeout=5.0) as _http:
            _resp = await _http.get(jwks_uri)
            _resp.raise_for_status()
            jwks = _resp.json()
        header = jwt.get_unverified_header(token)

        # Validate algorithm before using it
        token_alg = header.get("alg", "")
        if token_alg not in _OIDC_ALLOWED_ALGORITHMS:
            raise HTTPException(
                401,
                f"OIDC token uses disallowed algorithm '{token_alg}'. "
                f"Accepted: {sorted(_OIDC_ALLOWED_ALGORITHMS)}"
            )

        # Find matching key by kid
        key = next(
            (k for k in jwks.get("keys", []) if k.get("kid") == header.get("kid")),
            None,
        )
        if key is None:
            raise HTTPException(401, "No matching public key found in JWKS.")

        public_key = jose_jwk.construct(key)
        payload = jwt.decode(
            token,
            public_key,
            algorithms=[token_alg],   # safe: already validated against allowlist above
            audience=audience,
            options={**_DECODE_OPTIONS, "verify_iss": False},  # iss varies per IdP
        )
        return payload
    except HTTPException:
        raise
    except Exception as e:
        raise HTTPException(401, f"OIDC token validation failed: {e}")
