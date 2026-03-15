from __future__ import annotations

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel, ConfigDict
from sqlalchemy.orm import Session

from app.config import get_settings
from app.db.session import get_db_session
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


@router.post("/login", response_model=TokenResponse)
def login(payload: LoginRequest, session: Session = Depends(get_db_session)) -> TokenResponse:
    settings = get_settings()
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
        raise HTTPException(status_code=status.HTTP_401_UNAUTHORIZED, detail=str(exc)) from exc

    return _to_response(token_pair)


@router.post("/refresh", response_model=TokenResponse)
def refresh(payload: RefreshRequest, session: Session = Depends(get_db_session)) -> TokenResponse:
    settings = get_settings()
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
