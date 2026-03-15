from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Request, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
from app.security.protection import auth_protection_store
from app.services.auth import (
    AuthenticationError,
    TokenPair,
    authenticate_user,
    logout_refresh_token,
    refresh_token_pair,
)

router = APIRouter(prefix="/api/auth", tags=["auth"])


class LoginRequest(BaseModel):
    email: str
    password: str


class RefreshRequest(BaseModel):
    refresh_token: str


class UserSummary(BaseModel):
    model_config = ConfigDict(from_attributes=True)

    id: str
    email: str
    display_name: str
    is_admin: bool


class TokenResponse(BaseModel):
    access_token: str
    refresh_token: str
    token_type: str = "bearer"
    user: UserSummary


def _to_response(token_pair: TokenPair) -> TokenResponse:
    return TokenResponse(
        access_token=token_pair.access_token,
        refresh_token=token_pair.refresh_token,
        user=UserSummary.model_validate(token_pair.user),
    )


def _client_host(request: Request) -> str:
    return request.client.host if request.client is not None else "unknown"


def _login_lockout_key(email: str, request: Request) -> str:
    return f"login-lockout:{email.strip().lower()}:{_client_host(request)}"


def _apply_rate_limit(*, bucket: str, request: Request, limit: int, window_seconds: int) -> None:
    result = auth_protection_store.check_rate_limit(
        key=f"{bucket}:{_client_host(request)}",
        limit=limit,
        window_seconds=window_seconds,
    )
    if result.allowed:
        return

    raise HTTPException(
        status_code=status.HTTP_429_TOO_MANY_REQUESTS,
        detail="Too many authentication requests. Try again shortly.",
        headers={"Retry-After": str(result.retry_after_seconds)},
    )


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, request: Request, session: Session = Depends(get_db_session)) -> TokenResponse:
    settings = get_settings()
    _apply_rate_limit(
        bucket="login",
        request=request,
        limit=settings.login_rate_limit_max_attempts,
        window_seconds=settings.login_rate_limit_window_seconds,
    )
    lockout_key = _login_lockout_key(payload.email, request)
    lockout = auth_protection_store.check_lockout(key=lockout_key)
    if lockout.locked:
        raise HTTPException(
            status_code=status.HTTP_423_LOCKED,
            detail="Too many failed login attempts. Try again after the temporary lockout expires.",
            headers={"Retry-After": str(lockout.retry_after_seconds)},
        )

    try:
        token_pair = authenticate_user(
            session=session,
            email=payload.email,
            password=payload.password,
            pepper=settings.password_pepper,
            secret_key=settings.auth_secret_key,
            access_token_ttl_minutes=settings.access_token_ttl_minutes,
            refresh_token_ttl_days=settings.refresh_token_ttl_days,
        )
    except AuthenticationError as exc:
        lockout = auth_protection_store.register_login_failure(
            key=lockout_key,
            threshold=settings.auth_lockout_threshold,
            window_seconds=settings.auth_lockout_window_seconds,
            lockout_seconds=settings.auth_lockout_duration_seconds,
        )
        if lockout.locked:
            raise HTTPException(
                status_code=status.HTTP_423_LOCKED,
                detail="Too many failed login attempts. Try again after the temporary lockout expires.",
                headers={"Retry-After": str(lockout.retry_after_seconds)},
            ) from exc
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    auth_protection_store.clear_login_failures(key=lockout_key)
    return _to_response(token_pair)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, request: Request, session: Session = Depends(get_db_session)) -> TokenResponse:
    settings = get_settings()
    _apply_rate_limit(
        bucket="refresh",
        request=request,
        limit=settings.refresh_rate_limit_max_attempts,
        window_seconds=settings.refresh_rate_limit_window_seconds,
    )
    try:
        token_pair = refresh_token_pair(
            session=session,
            refresh_token=payload.refresh_token,
            secret_key=settings.auth_secret_key,
            access_token_ttl_minutes=settings.access_token_ttl_minutes,
            refresh_token_ttl_days=settings.refresh_token_ttl_days,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return _to_response(token_pair)


@router.post("/logout", status_code=status.HTTP_204_NO_CONTENT, response_class=Response)
def logout(payload: RefreshRequest, session: Session = Depends(get_db_session)) -> Response:
    settings = get_settings()
    try:
        logout_refresh_token(
            session=session,
            refresh_token=payload.refresh_token,
            secret_key=settings.auth_secret_key,
        )
    except AuthenticationError as exc:
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return Response(status_code=status.HTTP_204_NO_CONTENT)
