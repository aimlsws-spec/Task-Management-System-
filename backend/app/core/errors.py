from fastapi import FastAPI, Request
from fastapi.exceptions import RequestValidationError
from fastapi.responses import JSONResponse


class AppError(Exception):
    def __init__(self, code: str, message: str, status: int = 400, details: dict | None = None):
        self.code, self.message, self.status, self.details = code, message, status, details or {}


def NotFound(what: str = "Resource") -> AppError:  # noqa: N802
    # Also used for out-of-scope objects, so existence is not leaked.
    return AppError("NOT_FOUND", f"{what} not found", 404)


def Forbidden(message: str = "You are not allowed to perform this action") -> AppError:  # noqa: N802
    return AppError("FORBIDDEN_ACTION", message, 403)


def Unauthorized(message: str = "Authentication required") -> AppError:  # noqa: N802
    return AppError("UNAUTHENTICATED", message, 401)


def Conflict(code: str, message: str) -> AppError:  # noqa: N802
    return AppError(code, message, 409)


def _body(request: Request, code: str, message: str, details: dict | None = None) -> dict:
    return {
        "code": code,
        "message": message,
        "details": details or {},
        "request_id": getattr(request.state, "request_id", None),
    }


def install_error_handlers(app: FastAPI) -> None:
    @app.exception_handler(AppError)
    async def _app_error(request: Request, exc: AppError):
        return JSONResponse(_body(request, exc.code, exc.message, exc.details), status_code=exc.status)

    @app.exception_handler(RequestValidationError)
    async def _validation(request: Request, exc: RequestValidationError):
        errs = [{"loc": list(e["loc"]), "msg": e["msg"]} for e in exc.errors()]
        return JSONResponse(
            _body(request, "VALIDATION_ERROR", "Invalid request", {"errors": errs}), status_code=422
        )
