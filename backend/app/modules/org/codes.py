"""Employee codes (ADR 008): random, unique, always letters AND digits (e.g. SW-7K2QX9). Never sequential like EMP-0001."""

import re
import secrets

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.core.errors import AppError, Conflict
from app.modules.org.models import Employee

_LETTERS, _DIGITS = "ABCDEFGHJKLMNPQRSTUVWXYZ", "23456789"  # no I/O/0/1: easy to read out loud
_SHAPE = re.compile(r"^[A-Z0-9][A-Z0-9-]{2,28}[A-Z0-9]$")
_SEQUENTIAL = re.compile(r"^(EMP|EMPLOYEE|ID|E)-?0*\d{1,6}$")


def _candidate() -> str:
    chars = [secrets.choice(_LETTERS) for _ in range(3)] + [secrets.choice(_DIGITS) for _ in range(3)]
    secrets.SystemRandom().shuffle(chars)
    return "SW-" + "".join(chars)


def generate(db: Session) -> str:
    for _ in range(50):
        code = _candidate()
        if not db.scalar(select(Employee.id).where(Employee.employee_code == code)):
            return code
    raise AppError("CODE_GENERATION_FAILED", "Could not create an employee ID, please try again", 500)


def check_custom(db: Session, raw: str) -> str:
    """Validate an Admin-typed code: letters and digits, not a simple counter, not taken. Returns the normalised code."""
    code = raw.strip().upper()
    if not _SHAPE.match(code) or not re.search(r"[A-Z]", code) or not re.search(r"\d", code):
        raise AppError("INVALID_EMPLOYEE_CODE", "Employee ID must be 4-30 characters of letters and digits (a dash is allowed), with at least one of each", 422)
    if _SEQUENTIAL.match(code):
        raise AppError("INVALID_EMPLOYEE_CODE", "Employee ID must not be a simple number like EMP-001; leave it empty to get a unique one", 422)
    if db.scalar(select(Employee.id).where(Employee.employee_code == code)):
        raise Conflict("EMPLOYEE_CODE_EXISTS", "Employee code already exists")
    return code
