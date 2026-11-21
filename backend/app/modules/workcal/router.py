from datetime import date, timedelta

from fastapi import APIRouter, Depends, Request
from pydantic import Field
from sqlalchemy import select

from app.core.deps import get_principal, require
from app.core.errors import AppError, Conflict, NotFound
from app.core.schemas import Strict
from app.modules.audit import service as audit
from app.modules.audit.settings_service import DEFAULT_KEYS, get_setting, set_setting
from app.modules.rbac.policy import Principal
from app.modules.workcal import service
from app.modules.workcal.models import Holiday

router = APIRouter(tags=["work-calendar"])


class HolidayIn(Strict):
    date: date
    name: str = Field(min_length=2, max_length=150)
    is_working_override: bool = False


@router.get("/work-calendar")
def calendar(from_: date, to: date, p: Principal = Depends(get_principal)):
    if to < from_ or (to - from_).days > 400:
        raise AppError("INVALID_RANGE", "Range must be 0-400 days", 422)
    out, cur = [], from_
    while cur <= to:
        info = service.day_info(p.db, cur)
        out.append({
            "date": cur.isoformat(), "weekday": cur.weekday(), "is_working": info.is_working, "reason": info.reason,
            "holiday_name": info.holiday_name, "working_hours": info.working_hours,
            "windows": [[s.strftime("%H:%M"), e.strftime("%H:%M")] for s, e in info.windows],
        })  # fmt: skip
        cur += timedelta(days=1)
    return out


@router.get("/holidays")
def list_holidays(p: Principal = Depends(get_principal)):
    return [{"id": h.id, "date": h.date.isoformat(), "name": h.name, "is_working_override": h.is_working_override}
            for h in p.db.scalars(select(Holiday).order_by(Holiday.date))]  # fmt: skip


@router.post("/holidays", status_code=201)
def add_holiday(body: HolidayIn, request: Request, p: Principal = Depends(require("settings.manage"))):
    if p.db.scalar(select(Holiday.id).where(Holiday.date == body.date)):
        raise Conflict("HOLIDAY_EXISTS", "A holiday already exists on this date")
    h = Holiday(date=body.date, name=body.name, is_working_override=body.is_working_override)
    p.db.add(h)
    p.db.flush()
    audit.log(p.db, p.user.id, "HOLIDAY_CREATED", "holiday", h.id, after=body.model_dump(mode="json"), request=request)
    return {"id": h.id, "date": h.date.isoformat(), "name": h.name}


@router.delete("/holidays/{holiday_id}", status_code=204)
def delete_holiday(holiday_id: int, request: Request, p: Principal = Depends(require("settings.manage"))):
    h = p.db.get(Holiday, holiday_id)
    if h is None:
        raise NotFound("Holiday")
    audit.log(p.db, p.user.id, "HOLIDAY_DELETED", "holiday", h.id, before={"date": h.date.isoformat(), "name": h.name}, request=request)
    p.db.delete(h)


class SettingsIn(Strict):
    company_timezone: str | None = None
    eod_time: str | None = Field(None, pattern=r"^([01]\d|2[0-3]):[0-5]\d$")


@router.get("/admin/settings")
def get_settings_(p: Principal = Depends(require("settings.manage"))):
    return {k: get_setting(p.db, k) for k in DEFAULT_KEYS}


@router.put("/admin/settings")
def put_settings(body: SettingsIn, request: Request, p: Principal = Depends(require("settings.manage"))):
    from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

    data = body.model_dump(exclude_none=True)
    if "company_timezone" in data:
        try:
            ZoneInfo(data["company_timezone"])
        except (ZoneInfoNotFoundError, ValueError):
            raise AppError("INVALID_TIMEZONE", "Unknown IANA timezone", 422) from None
    before = {k: get_setting(p.db, k) for k in data}
    for k, v in data.items():
        set_setting(p.db, k, v, p.user.id)
    audit.log(p.db, p.user.id, "SETTINGS_CHANGED", "settings", ",".join(data), before=before, after=data, request=request)
    return {k: get_setting(p.db, k) for k in DEFAULT_KEYS}
