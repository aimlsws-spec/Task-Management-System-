import logging
import uuid
from pathlib import Path

from fastapi import APIRouter, FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import FileResponse, JSONResponse
from starlette.middleware.base import BaseHTTPMiddleware

from app import models_registry as _models  # noqa: F401  (registers every model)
from app.core import dbguard
from app.core.config import get_settings
from app.core.errors import install_error_handlers
from app.modules.ai.router import router as ai_router
from app.modules.audit.router import router as audit_router
from app.modules.auth.router import router as auth_router
from app.modules.collab.router import router as collab_router
from app.modules.notifications.router import router as notifications_router
from app.modules.org.companies_router import router as companies_router
from app.modules.org.router import router as org_router
from app.modules.rbac.router import router as rbac_router
from app.modules.reports.router import router as reports_router
from app.modules.tasks.accountability_router import router as accountability_router
from app.modules.tasks.projects_router import router as projects_router
from app.modules.tasks.router import router as tasks_router
from app.modules.timetracking.router import router as time_router
from app.modules.workcal.router import router as workcal_router

logging.basicConfig(level=logging.INFO, format="%(asctime)s %(levelname)s %(name)s %(message)s")


def create_app() -> FastAPI:
    s = get_settings()
    if s.env not in ("dev", "test") and (s.secret_key.startswith("dev-only") or len(s.secret_key) < 32):
        raise RuntimeError("TMS_SECRET_KEY must be a strong random value (>= 32 chars) outside dev/test")
    if s.env not in ("dev", "test") and s.dev_multi_session:
        raise RuntimeError("TMS_DEV_MULTI_SESSION must not be enabled outside dev")
    if "CPANEL_DB_" in s.database_url:  # the shipped .env carries placeholders: fail with a clear sentence, not a database error
        raise RuntimeError("Edit TMS_DATABASE_URL in .env: replace CPANEL_DB_USER, CPANEL_DB_PASSWORD and CPANEL_DB_NAME with the cPanel MySQL values")
    # No lifespan hook and no background threads: Passenger (WSGI) cannot run them. Jobs run from cron: app/jobs/run_once.py
    app = FastAPI(title="Task Management System API", version="0.1.0")
    install_error_handlers(app)
    app.add_middleware(BaseHTTPMiddleware, dispatch=dbguard.guard)  # added before CORS = runs inside it, so its answers carry CORS headers
    app.add_middleware(
        CORSMiddleware,
        allow_origins=[o.strip() for o in s.cors_origins.split(",") if o.strip()],
        allow_origin_regex=r"^https://([a-zA-Z0-9-]+\.)*(seawind\.co\.in|seawindsolution\.com)(:\d+)?$|^http://localhost(:\d+)?$",
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )

    @app.middleware("http")
    async def request_context(request: Request, call_next):
        request.state.request_id = request.headers.get("x-request-id") or uuid.uuid4().hex
        response = await call_next(request)
        response.headers["X-Request-ID"] = request.state.request_id
        response.headers["X-Content-Type-Options"] = "nosniff"
        path = request.url.path
        if path.startswith("/api"):
            response.headers["Cache-Control"] = "no-store"
        if (s.mail_after_request and request.method in ("POST", "PUT", "PATCH", "DELETE") and response.status_code < 400
                and path.startswith("/api/v1") and not path.startswith(("/api/v1/auth", "/api/v1/notifications"))):
            from starlette.background import BackgroundTask

            from app.jobs.kick import kick

            response.background = BackgroundTask(kick)  # ADR 007: mail goes out now, after the response, not at the next cron run
        return response

    api = APIRouter(prefix="/api/v1")
    for r in (ai_router, auth_router, org_router, companies_router, rbac_router, workcal_router, audit_router, tasks_router, projects_router, accountability_router, time_router, notifications_router, collab_router, reports_router):
        api.include_router(r)
    app.include_router(api)

    @app.get("/healthz", include_in_schema=False)
    def healthz():
        ok, msg = dbguard.check()
        return {"status": "ok", "database": "ok" if ok else "outdated", **({} if ok else {"message": msg})}

    # One address for everything: when a `frontend/` folder (the built website) sits next to `app/`, this app serves it too.
    default_site = Path(__file__).resolve().parents[1] / "frontend"
    _serve_website(app, s.frontend_dir or (str(default_site) if (default_site / "index.html").is_file() else ""))
    return app


def _serve_website(app: FastAPI, frontend_dir: str) -> None:
    """Serve the built website from the same address as the API: real files (assets, config.js, logo) are returned as they are,
    every other page URL (/tasks/5, /login ...) gets index.html so a browser refresh works. API typos are never answered with the website."""
    root = Path(frontend_dir).resolve() if frontend_dir else None
    index = root / "index.html" if root else None
    if index is None or not index.is_file():
        return

    @app.get("/{path:path}", include_in_schema=False)
    def website(path: str):
        if path.split("/", 1)[0] in ("api", "docs", "redoc", "openapi.json", "healthz"):
            return JSONResponse({"error": {"code": "NOT_FOUND", "message": "Not found"}}, status_code=404)
        if path and not any(part.startswith(".") for part in path.split("/")):
            f = (root / path).resolve()
            if f.is_file() and root in f.parents:  # never outside the website folder
                hashed = path.startswith("assets/")  # build output has a content hash in its name: cache for a year
                return FileResponse(f, headers={"Cache-Control": "public, max-age=31536000, immutable" if hashed else "no-cache"})
        return FileResponse(index, headers={"Cache-Control": "no-cache"})


app = create_app()
