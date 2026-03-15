from __future__ import annotations

from dataclasses import dataclass
from datetime import timedelta

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import RefreshTokenBlocklist, User
from app.security.passwords import verify_password
from app.security.tokens import create_token, decode_token


@dataclass(frozen=True)
class TokenPair:
    access_token: str
    refresh_token: str
    user: User


class AuthenticationError(RuntimeError):
    pass


def _issue_token_pair(
    *,
    user: User,
    secret_key: str,
    access_token_ttl_minutes: int,
    refresh_token_ttl_days: int,
) -> TokenPair:
    access_token = create_token(
        subject=user.id,
        token_type="access",
        secret_key=secret_key,
        expires_delta=timedelta(minutes=access_token_ttl_minutes),
    )
    refresh_token = create_token(
        subject=user.id,
        token_type="refresh",
        secret_key=secret_key,
        expires_delta=timedelta(days=refresh_token_ttl_days),
    )
    return TokenPair(access_token=access_token, refresh_token=refresh_token, user=user)


def _is_token_revoked(session: Session, token_id: str) -> bool:
    return session.scalar(
        select(RefreshTokenBlocklist.id).where(RefreshTokenBlocklist.token_id == token_id)
    ) is not None


def _revoke_refresh_token(session: Session, token_id: str, user_id: str, expires_at) -> None:
    if _is_token_revoked(session, token_id):
        raise AuthenticationError("Refresh token has been revoked.")

    session.add(
        RefreshTokenBlocklist(
            token_id=token_id,
            user_id=user_id,
            expires_at=expires_at,
        )
    )


def authenticate_user(
    *,
    session: Session,
    email: str,
    password: str,
    pepper: str,
    secret_key: str,
    access_token_ttl_minutes: int,
    refresh_token_ttl_days: int,
) -> TokenPair:
    user = session.scalar(select(User).where(User.email == email))
    if user is None or user.password_hash is None or user.password_salt is None:
        raise AuthenticationError("Invalid email or password.")
    if not user.is_active:
        raise AuthenticationError("User account is inactive.")

    if not verify_password(
        password=password,
        pepper=pepper,
        password_hash=user.password_hash,
        password_salt=user.password_salt,
    ):
        raise AuthenticationError("Invalid email or password.")

    return _issue_token_pair(
        user=user,
        secret_key=secret_key,
        access_token_ttl_minutes=access_token_ttl_minutes,
        refresh_token_ttl_days=refresh_token_ttl_days,
    )


def refresh_token_pair(
    *,
    session: Session,
    refresh_token: str,
    secret_key: str,
    access_token_ttl_minutes: int,
    refresh_token_ttl_days: int,
) -> TokenPair:
    payload = decode_token(refresh_token, secret_key, expected_type="refresh")
    if _is_token_revoked(session, payload.token_id):
        raise AuthenticationError("Refresh token has been revoked.")

    user = session.get(User, payload.subject)
    if user is None or not user.is_active:
        raise AuthenticationError("User account is unavailable.")

    _revoke_refresh_token(session, payload.token_id, payload.subject, payload.expires_at)
    token_pair = _issue_token_pair(
        user=user,
        secret_key=secret_key,
        access_token_ttl_minutes=access_token_ttl_minutes,
        refresh_token_ttl_days=refresh_token_ttl_days,
    )
    session.commit()
    return token_pair


def logout_refresh_token(*, session: Session, refresh_token: str, secret_key: str) -> None:
    payload = decode_token(refresh_token, secret_key, expected_type="refresh")
    _revoke_refresh_token(session, payload.token_id, payload.subject, payload.expires_at)
    session.commit()
