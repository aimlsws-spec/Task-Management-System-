from fastapi import APIRouter, Cookie, Depends, Request, Response
from pydantic import EmailStr, Field
from sqlalchemy.orm import Session

from app.core import ratelimit
from app.core.config import get_settings
from app.core.db import DB
from app.core.deps import get_principal
from app.core.errors import AppError
from app.core.schemas import Strict
from app.modules.auth import otp, service
from app.modules.rbac.policy import Principal

router = APIRouter(prefix="/auth", tags=["auth"])
COOKIE = "tms_refresh"


class LoginIn(Strict):
    email: EmailStr
    password: str = Field(min_length=1, max_length=200)


class PasswordChangeIn(Strict):
    current_password: str
    new_password: str = Field(max_length=200)


class ForgotIn(Strict):
    email: EmailStr


class ResetIn(Strict):
    token: str
    new_password: str = Field(max_length=200)


class SignupIn(Strict):
    full_name: str = Field(min_length=2, max_length=150)
    email: EmailStr
    password: str = Field(max_length=200)
    company_id: int | None = None


@router.post("/signup", status_code=201)
def signup(body: SignupIn, request: Request, db: Session = DB):
    """Self sign-up for company email domains. With the emailed code on (default) the reply carries the code challenge:
    the person proves the mailbox is theirs, and is then signed in to finish setup (department + designation)."""
    from app.modules.org import admin_service

    ratelimit.check(f"signup:{request.client.host if request.client else '?'}", 5)
    emp = admin_service.signup(db, body.full_name, body.email, body.password, request, company_id=body.company_id)
    if otp.enabled():
        user = db.get(service.User, emp.user_id)
        db.commit()  # the account exists even if the mail provider is down; they can sign in later
        return otp.start(db, user, "signup", request)
    msg = (
        "Your request to join the company has been submitted and is pending leadership approval."
        if emp.status == "pending_approval"
        else "Account created. Sign in to finish setting up your profile."
    )
    return {"message": msg}


class RefreshIn(Strict):
    refresh_token: str | None = None


def _multi() -> bool:
    """Dev-only per-tab sessions. Never active outside env=dev, whatever the flag says."""
    s = get_settings()
    return s.dev_multi_session and s.env == "dev"


def _set_cookie(response: Response, raw: str) -> None:
    s = get_settings()
    response.set_cookie(
        COOKIE, raw, max_age=s.refresh_token_days * 86400, httponly=True, secure=s.cookie_secure,
        samesite="strict", path="/api/v1/auth",
    )  # fmt: skip


def _token_body(user, access: str) -> dict:
    return {
        "access_token": access,
        "token_type": "bearer",
        "expires_in": get_settings().access_token_minutes * 60,
        "must_change_password": user.must_change_password,
    }


def _session_reply(response: Response, user, access: str, refresh: str) -> dict:
    out = _token_body(user, access)
    if _multi():
        out["refresh_token"] = refresh  # kept per tab by the SPA; no shared cookie
    else:
        _set_cookie(response, refresh)
    return out


@router.post("/login")
def login(body: LoginIn, request: Request, response: Response, db: Session = DB):
    """Step 1: password. With the emailed code on (default) the reply is {otp_required, challenge, ...} and NO session yet."""
    ratelimit.check(f"login:{request.client.host if request.client else '?'}", get_settings().login_rate_limit_per_minute)
    if otp.enabled():
        user = service.check_credentials(db, body.email, body.password, request)
        db.commit()
        return otp.start(db, user, "login", request)
    user, access, refresh = service.login(db, body.email, body.password, request)
    return _session_reply(response, user, access, refresh)


class OtpVerifyIn(Strict):
    challenge: str = Field(min_length=10, max_length=200)
    code: str = Field(min_length=6, max_length=6, pattern=r"^[0-9]{6}$")


class OtpResendIn(Strict):
    challenge: str = Field(min_length=10, max_length=200)


@router.post("/verify-otp")
def verify_otp(body: OtpVerifyIn, request: Request, response: Response, db: Session = DB):
    """Step 2: the 6-digit code from the email. Success returns the same body as a normal sign-in."""
    ratelimit.check(f"otp:{request.client.host if request.client else '?'}", 20)
    user, _purpose = otp.verify(db, body.challenge, body.code, request)
    user, access, refresh = service.issue_session(db, user, request)
    return _session_reply(response, user, access, refresh)


@router.post("/resend-otp")
def resend_otp(body: OtpResendIn, request: Request, db: Session = DB):
    ratelimit.check(f"otp-resend:{request.client.host if request.client else '?'}", 10)
    return otp.resend(db, body.challenge, request)


@router.post("/refresh")
def refresh(
    request: Request, response: Response, body: RefreshIn | None = None,
    db: Session = DB, tms_refresh: str | None = Cookie(None),
):  # fmt: skip
    # CSRF defence in depth on top of SameSite=Strict: require a custom header browsers won't send cross-site.
    if request.headers.get("x-requested-with") != "XMLHttpRequest":
        raise AppError("CSRF_CHECK_FAILED", "Missing X-Requested-With header", 403)
    body_token = body.refresh_token if (body and _multi()) else None
    user, access, raw = service.refresh(db, body_token or tms_refresh, request)
    out = _token_body(user, access)
    if body_token:
        out["refresh_token"] = raw
    else:
        _set_cookie(response, raw)
    return out


@router.post("/logout", status_code=204)
def logout(
    response: Response, body: RefreshIn | None = None, db: Session = DB,
    tms_refresh: str | None = Cookie(None),
):  # fmt: skip
    body_token = body.refresh_token if (body and _multi()) else None
    service.logout(db, body_token or tms_refresh)
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.post("/logout-all", status_code=204)
def logout_all(response: Response, p: Principal = Depends(get_principal)):
    service.revoke_all_sessions(p.db, p.user)
    response.delete_cookie(COOKIE, path="/api/v1/auth")


@router.post("/forgot-password", status_code=202)
def forgot(body: ForgotIn, request: Request, db: Session = DB):
    ratelimit.check(f"forgot:{request.client.host if request.client else '?'}", 5)
    service.forgot_password(db, body.email, request)
    return {"message": "If that account exists, a reset link has been sent."}


@router.post("/reset-password", status_code=204)
def reset(body: ResetIn, request: Request, db: Session = DB):
    service.reset_password(db, body.token, body.new_password, request)


@router.post("/change-password", status_code=204)
def change_password(body: PasswordChangeIn, request: Request, p: Principal = Depends(get_principal)):
    service.change_password(p.db, p.user, body.current_password, body.new_password, request)


def _team_info(db, e) -> dict:
    """Who my department and head are (shown on the employee dashboard). Names only: no scope-sensitive data."""
    from app.modules.org.models import Department, Employee
    from app.modules.org.service import current_manager_id

    dept = db.get(Department, e.department_id)
    head = db.get(Employee, dept.head_employee_id) if dept is not None and dept.head_employee_id else None
    sub_head = db.get(Employee, getattr(dept, "sub_head_employee_id", None)) if dept is not None and getattr(dept, "sub_head_employee_id", None) else None
    boss = db.get(Employee, current_manager_id(db, e.id)) if current_manager_id(db, e.id) else None
    qa = db.get(Employee, dept.qa_employee_id) if dept is not None and dept.qa_employee_id else None
    return {
        "department": dept.name if dept else None,
        "head": {"id": head.id, "full_name": head.full_name} if head and head.id != e.id else None,
        "sub_head": {"id": sub_head.id, "full_name": sub_head.full_name} if sub_head and sub_head.id != e.id else None,
        "reports_to": {"id": boss.id, "full_name": boss.full_name} if boss else None,
        "qa": {"id": qa.id, "full_name": qa.full_name} if qa and qa.id != e.id else None,
    }


@router.get("/me")
def me(p: Principal = Depends(get_principal)):
    e = p.employee
    comp_name = None
    if e is not None and getattr(e, "company_id", None):
        from app.modules.org.models import Company
        comp = p.db.get(Company, e.company_id)
        if comp:
            comp_name = comp.name
    return {
        "user": {
            "id": p.user.id,
            "email": p.user.email,
            "timezone": p.user.timezone,
            "must_change_password": p.user.must_change_password,
        },
        "employee": None
        if e is None
        else {
            "id": e.id,
            "employee_code": e.employee_code,
            "full_name": e.full_name,
            "job_title": e.job_title,
            "department_id": e.department_id,
            "company_id": getattr(e, "company_id", 1),
            "company_name": comp_name,
            "status": e.status,
            **_team_info(p.db, e),
        },
        "roles": p.roles,
        "rank": p.rank,
        "permissions": p.permissions,
    }
