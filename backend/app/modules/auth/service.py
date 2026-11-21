import logging
from datetime import timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError, Unauthorized
from app.core.security import (
    create_access_token,
    hash_password,
    new_family_id,
    new_opaque_token,
    sha256,
    validate_password_policy,
    verify_password,
)
from app.modules.audit import service as audit
from app.modules.auth.models import PasswordResetToken, RefreshToken, User

log = logging.getLogger("tms.auth")
INVALID = "Invalid email or password"


def _issue_refresh(db: Session, user: User, family_id: str, request: Request | None) -> str:
    raw, hashed = new_opaque_token()
    db.add(
        RefreshToken(
            user_id=user.id,
            family_id=family_id,
            token_hash=hashed,
            expires_at=clock.utcnow() + timedelta(days=get_settings().refresh_token_days),
            ip=request.client.host if request and request.client else None,
            user_agent=((request.headers.get("user-agent") or "")[:255]) if request else None,
        )
    )
    return raw


def check_credentials(db: Session, email: str, password: str, request: Request | None = None) -> User:
    """Password check with lockout counting. Raises the same generic error for every failure (no account enumeration)."""
    s, now = get_settings(), clock.utcnow()
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    locked = bool(user and user.locked_until and user.locked_until > now)
    ok = verify_password(password, user.password_hash if user else None)
    if user is None or locked or not ok or not user.is_active:
        if user is not None and not locked and user.is_active:
            user.failed_logins += 1
            if user.failed_logins >= s.max_failed_logins:
                user.locked_until = now + timedelta(minutes=s.lockout_minutes)
                user.failed_logins = 0
                audit.log(db, user.id, "AUTH_LOCKOUT", "user", user.id, request=request)
        db.commit()  # persist counters even though we raise
        audit.log(db, user.id if user else None, "AUTH_LOGIN_FAILED", "user", user.id if user else "unknown", request=request)
        db.commit()
        raise Unauthorized(INVALID)
    return user


def issue_session(db: Session, user: User, request: Request | None = None) -> tuple[User, str, str]:
    """Tokens for a person who has passed every sign-in step (password, and the emailed code when it is switched on)."""
    user.failed_logins, user.locked_until, user.last_login_at = 0, None, clock.utcnow()
    access = create_access_token(user.id, user.token_version)
    refresh = _issue_refresh(db, user, new_family_id(), request)
    audit.log(db, user.id, "AUTH_LOGIN", "user", user.id, request=request)
    return user, access, refresh


def login(db: Session, email: str, password: str, request: Request | None = None) -> tuple[User, str, str]:
    """Password-only sign-in (used when the emailed code is switched off)."""
    return issue_session(db, check_credentials(db, email, password, request), request)


def _revoke_family(db: Session, family_id: str) -> None:
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.family_id == family_id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=clock.utcnow())
    )


def refresh(db: Session, raw_token: str | None, request: Request | None = None) -> tuple[User, str, str]:
    if not raw_token:
        raise Unauthorized("No refresh token")
    now = clock.utcnow()
    tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_token)))
    if tok is None:
        raise Unauthorized("Invalid refresh token")
    if tok.revoked_at is not None:
        # Reuse of a rotated/revoked token => assume theft, kill the whole family.
        _revoke_family(db, tok.family_id)
        audit.log(db, tok.user_id, "AUTH_REFRESH_REUSE_DETECTED", "user", tok.user_id, request=request)
        db.commit()
        raise Unauthorized("Invalid refresh token")
    user = db.get(User, tok.user_id)
    if tok.expires_at <= now or user is None or not user.is_active:
        raise Unauthorized("Refresh token expired")
    new_raw = _issue_refresh(db, user, tok.family_id, request)
    db.flush()
    new_row = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(new_raw)))
    tok.revoked_at, tok.replaced_by_id = now, new_row.id
    return user, create_access_token(user.id, user.token_version), new_raw


def logout(db: Session, raw_token: str | None) -> None:
    if not raw_token:
        return
    tok = db.scalar(select(RefreshToken).where(RefreshToken.token_hash == sha256(raw_token)))
    if tok is not None:
        _revoke_family(db, tok.family_id)


def revoke_all_sessions(db: Session, user: User) -> None:
    user.token_version += 1
    db.execute(
        update(RefreshToken)
        .where(RefreshToken.user_id == user.id, RefreshToken.revoked_at.is_(None))
        .values(revoked_at=clock.utcnow())
    )


def change_password(db: Session, user: User, current: str, new: str, request: Request | None = None) -> None:
    if not verify_password(current, user.password_hash):
        raise AppError("INVALID_CREDENTIALS", "Current password is incorrect", 400)
    if verify_password(new, user.password_hash):
        raise AppError("WEAK_PASSWORD", "New password must differ from the current one", 422)
    validate_password_policy(new)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    revoke_all_sessions(db, user)
    audit.log(db, user.id, "AUTH_PASSWORD_CHANGED", "user", user.id, request=request)


def forgot_password(db: Session, email: str, request: Request | None = None) -> None:
    """Always succeeds silently (no account enumeration). Email delivery arrives in Phase 6."""
    user = db.scalar(select(User).where(User.email == email.strip().lower()))
    if user is None or not user.is_active:
        return
    raw, hashed = new_opaque_token()
    db.add(
        PasswordResetToken(
            user_id=user.id,
            token_hash=hashed,
            expires_at=clock.utcnow() + timedelta(minutes=get_settings().reset_token_minutes),
        )
    )
    audit.log(db, user.id, "AUTH_PASSWORD_RESET_REQUESTED", "user", user.id, request=request)
    if get_settings().env == "dev":
        log.warning("DEV ONLY password reset token for %s: %s", user.email, raw)


def reset_password(db: Session, raw_token: str, new: str, request: Request | None = None) -> None:
    row = db.scalar(select(PasswordResetToken).where(PasswordResetToken.token_hash == sha256(raw_token)))
    if row is None or row.used_at is not None or row.expires_at <= clock.utcnow():
        raise AppError("INVALID_RESET_TOKEN", "Reset link is invalid or expired", 400)
    validate_password_policy(new)
    user = db.get(User, row.user_id)
    user.password_hash = hash_password(new)
    user.must_change_password = False
    user.failed_logins, user.locked_until = 0, None
    row.used_at = clock.utcnow()
    revoke_all_sessions(db, user)
    audit.log(db, user.id, "AUTH_PASSWORD_RESET", "user", user.id, request=request)
