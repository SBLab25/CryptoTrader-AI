"""Authentication routes for Phase 1."""

from fastapi import APIRouter, Depends, HTTPException, Request, status
from fastapi.security import OAuth2PasswordRequestForm
from pydantic import BaseModel

from src.api.auth.jwt import (
    TokenResponse,
    create_access_token,
    create_refresh_token,
    decode_token,
    get_current_user,
)
from src.api.middleware.audit_logger import audit_log
from src.api.middleware.rate_limiter import limiter
from src.core.config import settings
from src.db.database import get_db_session
from src.db.user_repository import UserRepository
from src.utils.logger import get_logger

logger = get_logger(__name__)
router = APIRouter(prefix="/auth", tags=["Authentication"])


class RefreshRequest(BaseModel):
    refresh_token: str


class UserInfo(BaseModel):
    username: str
    is_active: bool
    last_login: str | None


@router.post("/token", response_model=TokenResponse)
@limiter.limit("10/minute")
async def login(request: Request, form_data: OAuth2PasswordRequestForm = Depends()):
    async with get_db_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_username(form_data.username)
        if user is None or not user.verify_password(form_data.password):
            client_ip = request.client.host if request.client else "unknown"
            await audit_log(
                event_type="AUTH_FAILED",
                actor=form_data.username,
                details={"reason": "invalid credentials"},
                ip_address=client_ip,
            )
            raise HTTPException(
                status_code=status.HTTP_401_UNAUTHORIZED,
                detail="Invalid credentials",
                headers={"WWW-Authenticate": "Bearer"},
            )

        if not user.is_active:
            raise HTTPException(status_code=status.HTTP_403_FORBIDDEN, detail="Account is disabled")

        await repo.update_last_login(user.id)
        access_token = create_access_token(user.username)
        refresh_token = create_refresh_token(user.username)
        client_ip = request.client.host if request.client else "unknown"
        await audit_log(
            event_type="AUTH_LOGIN",
            actor=user.username,
            details={"ip": client_ip},
            ip_address=client_ip,
        )
        return TokenResponse(
            access_token=access_token,
            refresh_token=refresh_token,
            expires_in=settings.jwt_access_token_expire_minutes * 60,
        )


@router.post("/refresh", response_model=TokenResponse)
@limiter.limit("30/minute")
async def refresh_access_token(request: Request, body: RefreshRequest):
    token_data = decode_token(body.refresh_token, expected_type="refresh")
    async with get_db_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_username(token_data.username)
        if user is None or not user.is_active:
            raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail="User not found or disabled")

    return TokenResponse(
        access_token=create_access_token(token_data.username),
        refresh_token=create_refresh_token(token_data.username),
        expires_in=settings.jwt_access_token_expire_minutes * 60,
    )


@router.get("/me", response_model=UserInfo)
async def get_me(current_user: str = Depends(get_current_user)):
    async with get_db_session() as session:
        repo = UserRepository(session)
        user = await repo.get_by_username(current_user)
        if user is None:
            raise HTTPException(status_code=404, detail="User not found")
        last_login = user.last_login.isoformat() if user.last_login else None
        return UserInfo(username=user.username, is_active=user.is_active, last_login=last_login)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT)
async def logout(request: Request, current_user: str = Depends(get_current_user)):
    client_ip = request.client.host if request.client else "unknown"
    await audit_log(
        event_type="AUTH_LOGOUT",
        actor=current_user,
        details={},
        ip_address=client_ip,
    )
    logger.info(f"[AUTH] Logout: {current_user}")
