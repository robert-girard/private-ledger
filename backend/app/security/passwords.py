from __future__ import annotations

import base64
import secrets
from dataclasses import dataclass
from hmac import compare_digest

from argon2.low_level import Type, hash_secret_raw

ARGON2_TIME_COST = 3
ARGON2_MEMORY_COST = 65536
ARGON2_PARALLELISM = 4
ARGON2_HASH_LENGTH = 32
ARGON2_SALT_LENGTH = 16


@dataclass(frozen=True)
class PasswordRecord:
    password_hash: str
    password_salt: str


def _encode_bytes(value: bytes) -> str:
    return base64.b64encode(value).decode("ascii")


def _decode_bytes(value: str) -> bytes:
    return base64.b64decode(value.encode("ascii"))


def _derive_hash(password: str, pepper: str, salt: bytes) -> bytes:
    secret = f"{password}{pepper}".encode("utf-8")
    return hash_secret_raw(
        secret=secret,
        salt=salt,
        time_cost=ARGON2_TIME_COST,
        memory_cost=ARGON2_MEMORY_COST,
        parallelism=ARGON2_PARALLELISM,
        hash_len=ARGON2_HASH_LENGTH,
        type=Type.ID,
    )


def hash_password(password: str, pepper: str) -> PasswordRecord:
    salt = secrets.token_bytes(ARGON2_SALT_LENGTH)
    password_hash = _derive_hash(password=password, pepper=pepper, salt=salt)
    return PasswordRecord(
        password_hash=_encode_bytes(password_hash),
        password_salt=_encode_bytes(salt),
    )


def verify_password(password: str, pepper: str, password_hash: str, password_salt: str) -> bool:
    expected_hash = _decode_bytes(password_hash)
    salt = _decode_bytes(password_salt)
    candidate_hash = _derive_hash(password=password, pepper=pepper, salt=salt)
    return compare_digest(expected_hash, candidate_hash)
