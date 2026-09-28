from datetime import datetime, timedelta, timezone
from typing import Optional

from jose import jwt, JWTError
from fastapi import HTTPException, status

from config import Config

_ALGORITHM = "HS256"


def create_access_token(subject: str, expires_minutes: int = Config.ACCESS_TOKEN_EXPIRE_MINUTES) -> str:
    expire = datetime.now(timezone.utc) + timedelta(minutes=expires_minutes)
    return jwt.encode({"sub": subject, "exp": expire}, Config.JWT_SECRET, algorithm=_ALGORITHM)


def decode_token(token: str) -> str:
    try:
        payload = jwt.decode(token, Config.JWT_SECRET, algorithms=[_ALGORITHM])
        sub: Optional[str] = payload.get("sub")
        if sub is None:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid token")
        return sub
    except JWTError:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="Invalid or expired token")
