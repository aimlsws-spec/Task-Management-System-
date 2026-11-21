import hashlib
import re
import secrets
import uuid
from datetime import UTC, timedelta

import jwt
from argon2 import PasswordHasher
from argon2.exceptions import InvalidHashError, VerificationError

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError

_ph = PasswordHasher()
_DUMMY_HASH = _ph.hash("dummy-password-for-constant-time")


def hash_password(password: str) -> str:
    return _ph.hash(password)


def verify_password(password: str, password_hash: str | None) -> bool:
    """Constant-ish time: verifies against a dummy hash when the user does not exist."""
    try:
        return _ph.verify(password_hash or _DUMMY_HASH, password) and password_hash is not None
    except (VerificationError, InvalidHashError):
        return False


def validate_password_policy(password: str) -> None:
    problems = []
    if len(password) < 10:
        problems.append("at least 10 characters")
    if not re.search(r"[a-z]", password) or not re.search(r"[A-Z]", password):
        problems.append("upper and lower case letters")
    if not re.search(r"\d", password):
        problems.append("a digit")
    if problems:
        raise AppError("WEAK_PASSWORD", "Password needs " + ", ".join(problems), 422)


def sha256(value: str) -> str:
    return hashlib.sha256(value.encode()).hexdigest()


def new_opaque_token() -> tuple[str, str]:
    """Returns (raw_token, sha256_hash). Only the hash is stored."""
    raw = secrets.token_urlsafe(48)
    return raw, sha256(raw)


def new_family_id() -> str:
    return str(uuid.uuid4())


def _ts(naive_utc) -> int:
    """Epoch seconds for a naive-UTC datetime (never interpret it as local time)."""
    return int(naive_utc.replace(tzinfo=UTC).timestamp())


def create_access_token(user_id: int, token_version: int) -> str:
    s = get_settings()
    now = clock.utcnow()
    payload = {
        "sub": str(user_id),
        "ver": token_version,
        "jti": uuid.uuid4().hex,
        "iat": _ts(now),
        "exp": _ts(now + timedelta(minutes=s.access_token_minutes)),
    }
    return jwt.encode(payload, s.secret_key, algorithm="HS256")


def decode_access_token(token: str) -> dict:
    s = get_settings()
    try:
        # Naive-UTC clock is used for issuance, so verify expiry manually against it.
        # exp/iat are checked against OUR clock (app.core.clock), not PyJWT's wall clock.
        payload = jwt.decode(token, s.secret_key, algorithms=["HS256"], options={"verify_exp": False, "verify_iat": False})
    except jwt.PyJWTError as exc:
        raise AppError("INVALID_TOKEN", "Invalid token", 401) from exc
    if payload.get("exp", 0) < _ts(clock.utcnow()):
        raise AppError("TOKEN_EXPIRED", "Access token expired", 401)
    return payload
