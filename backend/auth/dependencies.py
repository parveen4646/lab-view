"""
FastAPI auth dependencies.

Supports two token schemes:
  1. Neon Auth (EdDSA / Ed25519) — JWTs issued by the managed Neon Auth service.
     Verified via the JWKS endpoint; user rows are auto-provisioned on first use.
     This is the only scheme the frontend now generates.
  2. Legacy HS256 — JWTs issued by our own backend (email/password & Google OAuth
     routes).  The backend still verifies them, but the frontend login page no longer
     produces them, so existing user sessions are invalidated at deploy.  Users with
     old accounts must sign up via Neon Auth using the same email address — their
     reports are automatically linked on first Neon sign-in.

The correct scheme is detected from the JWT `alg` header; tokens cannot cross
the boundary (an EdDSA token cannot be accepted as HS256 and vice-versa).
"""
from __future__ import annotations

import logging
import secrets

import jwt as pyjwt  # PyJWT — used only to read the unverified JWT header
from fastapi import Depends, HTTPException, status
from fastapi.security import HTTPBearer, HTTPAuthorizationCredentials
from sqlalchemy.orm import Session

from config import Config
from db.database import get_db
from db.models import User

logger = logging.getLogger(__name__)
_bearer = HTTPBearer()


def _unusable_password_hash() -> str:
    """Generate a bcrypt hash of a random secret — satisfies the NOT NULL column
    constraint for accounts that authenticate exclusively via Neon Auth."""
    import bcrypt as _bcrypt
    return _bcrypt.hashpw(secrets.token_urlsafe(32).encode(), _bcrypt.gensalt()).decode()


def _token_algorithm(token: str) -> str:
    """Return the `alg` from the JWT header without verifying the signature."""
    try:
        return pyjwt.get_unverified_header(token).get("alg", "")
    except Exception:
        return ""


# ── Neon JWT path ─────────────────────────────────────────────────────────────

def _resolve_neon_user(token: str, db: Session) -> User:
    """Verify a Neon Auth JWT and return the matching local User, creating one if
    this is the first time this Neon account has accessed the API."""
    from auth.neon_jwt import decode_neon_token
    payload = decode_neon_token(token)
    neon_sub: str = payload["sub"]

    # Fast path: user already linked to this Neon account.
    user = db.query(User).filter(User.neon_sub == neon_sub, User.is_active == True).first()  # noqa: E712
    if user:
        return user

    # Require a positive email_verified claim — missing or False both block linking.
    # An attacker who signs up with a victim's email must not inherit their reports.
    email: str = payload.get("email") or ""
    if not payload.get("email_verified"):
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="Neon Auth account email is not verified",
        )

    # Check whether a password/Google account with the same email already exists.
    existing = db.query(User).filter(User.email == email).first()
    if existing is not None:
        existing.neon_sub = neon_sub
        existing.is_verified = True
        # Squatter registered first via email/password with this address and never
        # verified — invalidate their password so they can't keep using it.
        if not existing.hashed_password or existing.hashed_password.startswith("!"):
            existing.hashed_password = _unusable_password_hash()
        db.commit()
        db.refresh(existing)
        if not existing.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Account disabled")
        return existing

    # First time — create a local stub for this Neon user.
    from sqlalchemy.exc import IntegrityError
    user = User(
        email=email,
        full_name=payload.get("name"),
        hashed_password=_unusable_password_hash(),
        neon_sub=neon_sub,
        is_verified=True,
    )
    db.add(user)
    try:
        db.commit()
        db.refresh(user)
        logger.info("Auto-provisioned local user for Neon sub %s (email=%s)", neon_sub, email)
    except IntegrityError:
        db.rollback()
        # Race: another request provisioned this user between our lookup and insert.
        user = db.query(User).filter(User.neon_sub == neon_sub).first()
        if user:
            return user
        raise HTTPException(status_code=500, detail="Could not create user account")
    except Exception as exc:
        db.rollback()
        logger.error("Failed to create local user for Neon sub %s: %s", neon_sub, exc)
        raise HTTPException(status_code=500, detail="Could not create user account")
    return user


# ── Unified resolver ──────────────────────────────────────────────────────────

def _resolve_user(token: str, db: Session) -> User:
    """Route the token to the correct verifier based on its `alg` header."""
    alg = _token_algorithm(token)
    if alg == "EdDSA" and Config.NEON_AUTH_URL:
        return _resolve_neon_user(token, db)
    # Fall back to legacy HS256 issued by our own backend.
    from auth.jwt import decode_token
    user_id = decode_token(token)
    user = db.query(User).filter(User.id == user_id, User.is_active == True).first()  # noqa: E712
    if not user:
        raise HTTPException(
            status_code=status.HTTP_401_UNAUTHORIZED,
            detail="User not found or inactive",
        )
    return user


# ── FastAPI dependencies ───────────────────────────────────────────────────────

def get_current_user(
    credentials: HTTPAuthorizationCredentials = Depends(_bearer),
    db: Session = Depends(get_db),
) -> User:
    return _resolve_user(credentials.credentials, db)


