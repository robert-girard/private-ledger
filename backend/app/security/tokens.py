from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime, timedelta
from uuid import uuid4

import jwt
from jwt import InvalidTokenError


@dataclass(frozen=True)
class TokenPayload:
    token_id: str
    subject: str
    token_type: str
    issued_at: datetime
    expires_at: datetime


def create_token(
    *,
    subject: str,
    token_type: str,
    secret_key: str,
    expires_delta: timedelta,
) -> str:
    now = datetime.now(UTC)
    payload = {
        "jti": str(uuid4()),
        "sub": subject,
        "type": token_type,
        "iat": int(now.timestamp()),
        "exp": int((now + expires_delta).timestamp()),
    }
    return jwt.encode(payload, secret_key, algorithm="HS256")


def decode_token(token: str, secret_key: str, expected_type: str) -> TokenPayload:
    try:
        payload = jwt.decode(token, secret_key, algorithms=["HS256"])
    except InvalidTokenError as exc:
        raise ValueError("Invalid token.") from exc

    token_type = payload.get("type")
    if token_type != expected_type:
        raise ValueError("Invalid token type.")

    subject = payload.get("sub")
    token_id = payload.get("jti")
    issued_at = payload.get("iat")
    expires_at = payload.get("exp")
    if not isinstance(subject, str) or not isinstance(token_id, str):
        raise ValueError("Invalid token payload.")
    if not isinstance(issued_at, int) or not isinstance(expires_at, int):
        raise ValueError("Invalid token timestamps.")

    return TokenPayload(
        token_id=token_id,
        subject=subject,
        token_type=token_type,
        issued_at=datetime.fromtimestamp(issued_at, UTC),
        expires_at=datetime.fromtimestamp(expires_at, UTC),
    )
