"""JWT helpers and FastAPI auth dependencies."""

from datetime import datetime, timedelta, timezone
from typing import Optional

from fastapi import Depends, HTTPException, Query, status
from fastapi.security import OAuth2PasswordBearer
from jose import JWTError, jwt
from pydantic import BaseModel

from src.core.config import settings

oauth2_scheme = OAuth2PasswordBearer(tokenUrl="/auth/token")


class TokenData(BaseModel):
    username: str
    token_type: str


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    expires_in: int


def _create_token(data: dict, expires_in: timedelta) -> str:
    now = datetime.now(tz=timezone.utc)
    payload = {**data, "iat": now, "exp": now + expires_in}
    return jwt.encode(payload, settings.jwt_signing_key, algorithm=settings.jwt_algorithm)


def create_access_token(username: str) -> str:
    return _create_token(
        {"sub": username, "type": "access"},
        timedelta(minutes=settings.jwt_access_token_expire_minutes),
    )


def create_refresh_token(username: str) -> str:
    return _create_token(
        {"sub": username, "type": "refresh"},
        timedelta(days=settings.jwt_refresh_token_expire_days),
    )


def decode_token(token: str, expected_type: str = "access") -> TokenData:
    credentials_exception = HTTPException(
        status_code=status.HTTP_401_UNAUTHORIZED,
        detail="Invalid or expired token",
        headers={"WWW-Authenticate": "Bearer"},
    )
    try:
        payload = jwt.decode(
            token,
            settings.jwt_signing_key,
            algorithms=[settings.jwt_algorithm],
        )
        username: Optional[str] = payload.get("sub")
        token_type: Optional[str] = payload.get("type")
        if username is None or token_type != expected_type:
            raise credentials_exception
        return TokenData(username=username, token_type=token_type)
    except JWTError as exc:
        raise credentials_exception from exc


async def get_current_user(token: str = Depends(oauth2_scheme)) -> str:
    return decode_token(token, expected_type="access").username


async def ws_get_current_user(token: str = Query(...)) -> str:
    return decode_token(token, expected_type="access").username
