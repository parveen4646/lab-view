"""
Verify JWTs issued by Neon Auth (Better Auth managed service).

Neon Auth signs session tokens with an Ed25519 (EdDSA) key, published at:
  <NEON_AUTH_URL>/.well-known/jwks.json

python-jose does not support EdDSA; we use PyJWT (>=2.8) instead.
PyJWKClient handles JWKS fetching, kid-based key selection, and in-memory
caching (refreshed every 5 minutes).
"""
from __future__ import annotations

import logging
from typing import Any

import jwt as pyjwt  # PyJWT — not python-jose
from jwt import ExpiredSignatureError, InvalidTokenError, PyJWKClient
from fastapi import HTTPException, status

from config import Config

logger = logging.getLogger(__name__)

_jwks_client: PyJWKClient | None = None


def _get_jwks_client() -> PyJWKClient:
    global _jwks_client
    if _jwks_client is None:
        jwks_url = Config.NEON_AUTH_JWKS_URL or (
            Config.NEON_AUTH_URL.rstrip("/") + "/.well-known/jwks.json"
        )
        # cache_jwk_set=True keeps keys in memory; lifespan=300 refreshes every 5 min.
        _jwks_client = PyJWKClient(jwks_url, cache_jwk_set=True, lifespan=300)
        logger.info("Neon Auth JWKS client initialised: %s", jwks_url)
    return _jwks_client


def decode_neon_token(token: str) -> dict[str, Any]:
    """
    Verify a Neon Auth JWT and return its payload.

    Raises HTTPException 401 on any verification failure.
    Raises HTTPException 503 if Neon Auth is not configured.
    """
    if not Config.NEON_AUTH_URL:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Neon Auth is not configured on this server",
        )
    try:
        client = _get_jwks_client()
        signing_key = client.get_signing_key_from_jwt(token)
        payload = pyjwt.decode(
            token,
            signing_key.key,
            algorithms=["EdDSA"],
            options={"verify_aud": False, "require": ["exp", "sub"]},
        )
        return payload
    except ExpiredSignatureError:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token has expired",
        )
    except InvalidTokenError as exc:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail=f"Invalid token: {exc}",
        )
    except HTTPException:
        raise
    except Exception as exc:
        logger.warning("Neon JWT verification failed: %s", exc)
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Token verification failed",
        )
