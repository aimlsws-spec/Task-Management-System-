"""Email one-time codes for sign-in and sign-up (ADR 008).

Password first, then a 6-digit code mailed to the registered address. Only SHA-256 hashes are stored (never the code); a
challenge lives `otp_minutes`, allows `otp_max_attempts` wrong codes, can be resent after `otp_resend_seconds` (at most
`otp_max_sends` times). The email is sent straight away from the request (not through the queue): a code must not wait
for a cron pass, and is never kept in the email log."""

import hmac
import logging
import secrets
from datetime import timedelta
from email.message import EmailMessage
from email.utils import formatdate, make_msgid, parseaddr

from fastapi import Request
from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core import clock
from app.core.config import get_settings
from app.core.errors import AppError, Unauthorized
from app.core.security import new_opaque_token, sha256
from app.modules.audit import service as audit
from app.modules.auth.models import LoginOtp, User
from app.modules.notifications import mailer

log = logging.getLogger("tms.otp")
BAD = "That code is not correct or has expired. Sign in again to get a new one."


def enabled() -> bool:
    return get_settings().otp_enabled


def mask(email: str) -> str:
    name, _, dom = email.partition("@")
    return (name[:1] + "***" if len(name) > 1 else "*") + "@" + dom


def _code_hash(challenge_hash: str, code: str) -> str:
    return sha256(f"{challenge_hash}:{code.strip()}:{get_settings().secret_key}")


def _send(user: User, code: str, minutes: int) -> None:
    s = get_settings()
    base_url = s.app_base_url.rstrip("/")
    base_url_display = base_url.replace("https://", "").replace("http://", "")
    logo_url = f"{base_url}/seawind-logo.png"

    msg = EmailMessage()
    msg["From"] = s.email_from
    msg["To"] = user.email
    msg["Subject"] = f"[SeaWind] Your sign-in code is {code}"
    sender = parseaddr(s.email_from)[1]
    msg["Date"] = formatdate(localtime=False)
    msg["Message-ID"] = make_msgid(domain=sender.rpartition("@")[2] or "seawind.co.in")
    msg["Auto-Submitted"] = "auto-generated"
    msg["Importance"] = "high"
    msg["X-Mailer"] = "SeaWind-TMS"

    text = (
        f"Your SeaWind Task Management sign-in verification code is:\n\n"
        f"      {code}\n\n"
        f"This code works for {minutes} minutes.\n"
        f"If you did not try to sign in, ignore this email and contact your administrator.\n\n"
        f"— SeaWind Solution · Regeneration of IT Services\n{base_url}"
    )
    msg.set_content(text)

    html = f'''<!DOCTYPE html>
<html lang="en">
<head>
  <meta charset="utf-8">
  <meta name="viewport" content="width=device-width, initial-scale=1.0">
  <title>SeaWind Sign-In Code</title>
</head>
<body style="margin:0;padding:0;background-color:#f1f5f9;font-family:-apple-system,BlinkMacSystemFont,'Segoe UI',Roboto,Helvetica,Arial,sans-serif;color:#1e293b;-webkit-font-smoothing:antialiased;">
  <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="background-color:#f1f5f9;padding:32px 16px;">
    <tr>
      <td align="center">
        <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0" style="max-width:540px;background-color:#ffffff;border-radius:14px;border:1px solid #e2e8f0;overflow:hidden;box-shadow:0 4px 12px rgba(15,23,42,0.06);">
          
          <!-- Top Brand Accent Bar -->
          <tr>
            <td style="height:4px;background:linear-gradient(90deg,#1e3a8a 0%,#1f55c4 50%,#0284c7 100%);line-height:4px;font-size:4px;">&nbsp;</td>
          </tr>

          <!-- Header with SeaWind Logo -->
          <tr>
            <td style="padding:24px 32px 18px;border-bottom:1px solid #f1f5f9;background:linear-gradient(180deg,#ffffff 0%,#f8fafc 100%);">
              <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                <tr>
                  <td align="left" style="vertical-align:middle;">
                    <a href="{base_url}" target="_blank" style="text-decoration:none;display:inline-block;">
                      <img src="{logo_url}" alt="SeaWind - Regeneration of IT Services" width="165" style="display:block;width:165px;max-width:165px;height:auto;border:0;outline:none;" />
                    </a>
                  </td>
                  <td align="right" style="vertical-align:middle;">
                    <span style="display:inline-block;background-color:#eff6ff;color:#1d4ed8;font-size:10px;font-weight:700;letter-spacing:0.08em;text-transform:uppercase;padding:4px 10px;border-radius:9999px;border:1px solid #bfdbfe;">
                      Authentication
                    </span>
                  </td>
                </tr>
              </table>
            </td>
          </tr>

          <!-- Body -->
          <tr>
            <td style="padding:32px 32px 28px;text-align:center;">
              <h1 style="margin:0 0 10px;font-size:22px;font-weight:700;color:#0f172a;">
                Sign-In Verification Code
              </h1>
              <p style="margin:0 0 24px;font-size:14px;line-height:1.5;color:#475569;">
                Enter this 6-digit one-time code to authenticate your sign-in to SeaWind Task Management:
              </p>

              <!-- OTP Block -->
              <div style="background-color:#f8fafc;border:2px dashed #93c5fd;border-radius:12px;padding:18px 16px;margin:0 auto 24px;max-width:300px;">
                <span style="font-family:'Courier New',Courier,monospace,sans-serif;font-size:36px;font-weight:800;letter-spacing:10px;color:#1f55c4;display:inline-block;padding-left:10px;">
                  {code}
                </span>
              </div>

              <!-- Security Info -->
              <div style="background-color:#f0fdf4;border:1px solid #bbf7d0;border-radius:8px;padding:12px 16px;text-align:left;margin-bottom:20px;">
                <table role="presentation" width="100%" cellpadding="0" cellspacing="0" border="0">
                  <tr>
                    <td style="font-size:12px;line-height:1.5;color:#166534;">
                      <strong>Security Notice:</strong> This code is valid for <strong>{minutes} minutes</strong>. SeaWind employees will never ask you for this code. Do not share it with anyone.
                    </td>
                  </tr>
                </table>
              </div>

              <p style="margin:0;font-size:12px;line-height:1.5;color:#64748b;">
                If you did not initiate this sign-in attempt, someone may be trying to access your account. Please notify your administrator immediately.
              </p>
            </td>
          </tr>

          <!-- Footer -->
          <tr>
            <td style="padding:20px 32px;background-color:#f8fafc;border-top:1px solid #e2e8f0;text-align:center;">
              <p style="margin:0 0 6px;font-size:12px;line-height:1.5;color:#64748b;">
                <strong style="color:#334155;">SeaWind Solution</strong> &bull; Regeneration of IT Services
              </p>
              <p style="margin:0;font-size:11px;line-height:1.5;color:#94a3b8;">
                <a href="{base_url}" target="_blank" style="color:#1f55c4;text-decoration:none;">{base_url_display}</a> &bull; Automated Identity Verification
              </p>
            </td>
          </tr>

        </table>
      </td>
    </tr>
  </table>
</body>
</html>'''
    msg.add_alternative(html, subtype="html")
    if mailer.real_mail_server() and mailer.is_reserved_recipient(user.email):
        raise AppError("EMAIL_UNDELIVERABLE", "The email address on this account cannot receive mail. Ask the administrator to fix it.", 422)
    try:
        mailer.send_message(msg)
    except Exception as exc:  # noqa: BLE001
        log.error("OTP email to user %s failed: %s", user.id, exc)
        raise AppError("OTP_EMAIL_FAILED", "We could not send the code to your email. Please try again in a moment.", 503) from exc


def _new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def start(db: Session, user: User, purpose: str = "login", request: Request | None = None) -> dict:
    """Create a challenge and mail the code. Returns what the browser needs to show the code box."""
    s, now = get_settings(), clock.utcnow()
    for old in db.scalars(select(LoginOtp).where(LoginOtp.user_id == user.id, LoginOtp.used_at.is_(None))):
        old.used_at = now  # one live challenge per person
    raw, ch = new_opaque_token()
    code = _new_code()
    row = LoginOtp(user_id=user.id, challenge_hash=ch, code_hash=_code_hash(ch, code), purpose=purpose,
                   expires_at=now + timedelta(minutes=s.otp_minutes), last_sent_at=now)  # fmt: skip
    db.add(row)
    db.flush()
    _send(user, code, s.otp_minutes)
    audit.log(db, user.id, "AUTH_OTP_SENT", "user", user.id, request=request)
    return _out(user, raw, s.otp_minutes * 60, s.otp_resend_seconds)


def _out(user: User, raw: str, expires_in: int, resend_after: int) -> dict:
    return {"otp_required": True, "challenge": raw, "email_hint": mask(user.email), "expires_in": expires_in, "resend_after": resend_after}


def _row(db: Session, challenge: str) -> LoginOtp | None:
    return db.scalar(select(LoginOtp).where(LoginOtp.challenge_hash == sha256(challenge)).with_for_update())


def verify(db: Session, challenge: str, code: str, request: Request | None = None) -> tuple[User, str]:
    """Check the code. Returns (user, purpose). Wrong codes are counted; too many kills the challenge."""
    s, now = get_settings(), clock.utcnow()
    row = _row(db, challenge)
    if row is None or row.used_at is not None or row.expires_at <= now or row.attempts >= s.otp_max_attempts:
        raise Unauthorized(BAD)
    user = db.get(User, row.user_id)
    if user is None or not user.is_active:
        raise Unauthorized(BAD)
    if not hmac.compare_digest(row.code_hash, _code_hash(row.challenge_hash, code)):
        row.attempts += 1
        if row.attempts >= s.otp_max_attempts:
            row.used_at = now
            audit.log(db, user.id, "AUTH_OTP_LOCKED", "user", user.id, request=request)
        audit.log(db, user.id, "AUTH_OTP_FAILED", "user", user.id, request=request)
        db.commit()  # keep the counter although we raise
        raise Unauthorized(BAD)
    row.used_at = now
    return user, row.purpose


def resend(db: Session, challenge: str, request: Request | None = None) -> dict:
    s, now = get_settings(), clock.utcnow()
    row = _row(db, challenge)
    if row is None or row.used_at is not None or row.expires_at <= now:
        raise Unauthorized(BAD)
    wait = s.otp_resend_seconds - int((now - row.last_sent_at).total_seconds())
    if wait > 0:
        raise AppError("OTP_TOO_SOON", f"Please wait {wait} seconds before asking for another code", 429)
    if row.sends >= s.otp_max_sends:
        raise AppError("OTP_RESEND_LIMIT", "Too many codes requested. Sign in again.", 429)
    user = db.get(User, row.user_id)
    code = _new_code()
    row.code_hash, row.attempts, row.sends, row.last_sent_at = _code_hash(row.challenge_hash, code), 0, row.sends + 1, now
    row.expires_at = now + timedelta(minutes=s.otp_minutes)
    db.flush()
    _send(user, code, s.otp_minutes)
    audit.log(db, user.id, "AUTH_OTP_RESENT", "user", user.id, request=request)
    return _out(user, challenge, s.otp_minutes * 60, s.otp_resend_seconds)
