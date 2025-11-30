from fastapi import Request
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException
from logging_config import get_logger, correlation_id_var
import metrics
import time


def _base_payload(error_type: str, message: str, request: Request, correlation_id: str, details=None, status_code: int = 500):
    return {
        "timestamp": time.strftime('%Y-%m-%dT%H:%M:%SZ', time.gmtime()),
        "path": request.url.path,
        "method": request.method,
        "status_code": status_code,
        "correlation_id": correlation_id,
        "error": {
            "type": error_type,
            "message": message,
            "details": details,
        }
    }


def install_error_handlers(app):
    logger = get_logger("app.error")

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(request: Request, exc: StarletteHTTPException):
        cid = correlation_id_var.get()
        payload = _base_payload("http_exception", exc.detail, request, cid, status_code=exc.status_code)
        logger.warning("http_exception", extra={"correlation_id": cid, "status_code": exc.status_code, "detail": exc.detail})
        metrics.record_error("http_exception")
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(request: Request, exc: RequestValidationError):
        cid = correlation_id_var.get()
        errors = exc.errors()

        # Convert errors to JSON-serializable format
        serializable_errors = []
        for error in errors:
            error_dict = {
                "type": error.get("type"),
                "loc": error.get("loc"),
                "msg": error.get("msg"),
                "input": error.get("input"),
            }
            # Convert ctx error to string if present
            if "ctx" in error and "error" in error["ctx"]:
                error_dict["ctx"] = {"error": str(error["ctx"]["error"])}
            serializable_errors.append(error_dict)

        payload = _base_payload("validation_error", "Request validation failed", request, cid, details=serializable_errors, status_code=422)
        logger.warning("validation_error", extra={"correlation_id": cid, "errors": serializable_errors})
        metrics.record_error("validation_error")
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(request: Request, exc: Exception):
        cid = correlation_id_var.get()
        payload = _base_payload("internal_error", "Internal Server Error", request, cid, status_code=500)
        logger.error("unhandled_exception", extra={"correlation_id": cid, "error_type": type(exc).__name__, "error": str(exc)})
        metrics.record_error("internal_error")
        return JSONResponse(status_code=500, content=payload)
