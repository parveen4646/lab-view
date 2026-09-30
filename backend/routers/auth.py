import secrets

from fastapi import APIRouter, Depends, HTTPException, status
from google.auth.transport import requests as google_requests
from google.oauth2 import id_token as google_id_token
from pydantic import BaseModel, EmailStr
from sqlalchemy.orm import Session
import bcrypt as _bcrypt_lib

from auth.jwt import create_access_token
from auth.dependencies import get_current_user
from config import Config
from db.database import get_db
from db.models import User

router = APIRouter(prefix="/auth", tags=["auth"])


# ── Pydantic schemas ──────────────────────────────────────────────────────────

class RegisterRequest(BaseModel):
    email: EmailStr
    password: str
    full_name: str | None = None


class LoginRequest(BaseModel):
    email: EmailStr
    password: str


class GoogleLoginRequest(BaseModel):
    credential: str  # ID token JWT from Google Identity Services


class TokenResponse(BaseModel):
    access_token: str
    token_type: str = "bearer"


class UserResponse(BaseModel):
    id: str
    email: str
    full_name: str | None
    is_active: bool
    is_verified: bool

    model_config = {"from_attributes": True}


# ── Helpers ───────────────────────────────────────────────────────────────────

def _hash(password: str) -> str:
    return _bcrypt_lib.hashpw(password.encode(), _bcrypt_lib.gensalt()).decode()


def _verify(plain: str, hashed: str) -> bool:
    return _bcrypt_lib.checkpw(plain.encode(), hashed.encode())


def _unusable_password_hash() -> str:
    """Google-only accounts have no password; store a hash of a random
    value so the NOT NULL column is satisfied but no password can match it."""
    return _hash(secrets.token_urlsafe(32))


# ── Routes ────────────────────────────────────────────────────────────────────

@router.post("/register", response_model=TokenResponse, status_code=status.HTTP_201_CREATED)
def register(body: RegisterRequest, db: Session = Depends(get_db)):
    if db.query(User).filter(User.email == body.email).first():
        raise HTTPException(status_code=409, detail="Email already registered")
    if len(body.password) < 8:
        raise HTTPException(status_code=422, detail="Password must be at least 8 characters")

    user = User(
        email=body.email,
        full_name=body.full_name,
        hashed_password=_hash(body.password),
    )
    db.add(user)
    db.commit()
    db.refresh(user)

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/login", response_model=TokenResponse)
def login(body: LoginRequest, db: Session = Depends(get_db)):
    user = db.query(User).filter(User.email == body.email, User.is_active == True).first()
    if not user or not _verify(body.password, user.hashed_password):
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid credentials")

    return TokenResponse(access_token=create_access_token(user.id))


@router.post("/google", response_model=TokenResponse)
def google_login(body: GoogleLoginRequest, db: Session = Depends(get_db)):
    if not Config.GOOGLE_OAUTH_CLIENT_ID:
        raise HTTPException(status_code=503, detail="Google sign-in is not configured")

    try:
        payload = google_id_token.verify_oauth2_token(
            body.credential,
            google_requests.Request(),
            Config.GOOGLE_OAUTH_CLIENT_ID,
        )
    except ValueError:
        raise HTTPException(status_code=401, detail="Invalid Google credential")

    google_sub = payload["sub"]
    email = payload.get("email")
    if not email or not payload.get("email_verified"):
        raise HTTPException(status_code=401, detail="Google account email is not verified")

    user = db.query(User).filter(User.google_sub == google_sub).first()
    if user is None:
        # Link to an existing password account with the same email, else create one.
        user = db.query(User).filter(User.email == email).first()
        if user is not None:
            if not user.is_verified:
                # Unverified email means we can't trust that row's password owner is
                # this person — Google just proved they own the email, so this account
                # is theirs now. Kill the old password so a prior registrant can't
                # keep using it to read this person's reports.
                user.hashed_password = _unusable_password_hash()
                user.is_verified = True
            user.google_sub = google_sub
        else:
            user = User(
                email=email,
                full_name=payload.get("name"),
                hashed_password=_unusable_password_hash(),
                google_sub=google_sub,
                is_verified=True,
            )
            db.add(user)
        db.commit()
        db.refresh(user)

    if not user.is_active:
        raise HTTPException(status_code=401, detail="Account is disabled")

    return TokenResponse(access_token=create_access_token(user.id))


@router.get("/me", response_model=UserResponse)
def me(current_user: User = Depends(get_current_user)):
    return current_user
