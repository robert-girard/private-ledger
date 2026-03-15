from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import User
from app.security.passwords import hash_password


@dataclass(frozen=True)
class BootstrapAdminInput:
    email: str
    display_name: str
    password: str


class BootstrapAdminError(RuntimeError):
    pass


def bootstrap_initial_admin(
    session: Session,
    admin: BootstrapAdminInput,
    pepper: str,
) -> User:
    existing_user = session.scalar(select(User.id).limit(1))
    if existing_user is not None:
        raise BootstrapAdminError("Bootstrap admin can only be created when no users exist.")

    password_record = hash_password(password=admin.password, pepper=pepper)
    user = User(
        email=admin.email,
        display_name=admin.display_name,
        password_hash=password_record.password_hash,
        password_salt=password_record.password_salt,
        is_admin=True,
        is_active=True,
    )
    session.add(user)
    session.commit()
    session.refresh(user)
    return user
