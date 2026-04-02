"""
Standard error handlers for all services.

Provides consistent JSON error responses with correlation IDs,
timestamps, and structured error information.
"""

import time
from typing import Any, Optional

from fastapi import FastAPI, Request, HTTPException
from fastapi.responses import JSONResponse
from fastapi.exceptions import RequestValidationError
from starlette.exceptions import HTTPException as StarletteHTTPException

from .logging_config import get_correlation_id


def _error_payload(
    error_type: str,
    message: str,
    request: Request,
    status_code: int,
    details: Optional[Any] = None,
) -> dict:
    """Build a standardized error response payload."""
    correlation_id = get_correlation_id()
    payload = {
        "timestamp": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime()),
        "path": request.url.path,
        "method": request.method,
        "status_code": status_code,
        "correlation_id": correlation_id,
        "error": {
            "type": error_type,
            "message": message,
        },
    }
    if details is not None:
        payload["error"]["details"] = details
    return payload


def install_error_handlers(app: FastAPI) -> None:
    """
    Install standard error handlers on a FastAPI application.

    Provides handlers for:
    - HTTP exceptions (4xx, 5xx)
    - Request validation errors (422)
    - Unhandled exceptions (500)
    """

    @app.exception_handler(StarletteHTTPException)
    async def http_exception_handler(
        request: Request, exc: StarletteHTTPException
    ) -> JSONResponse:
        """Handle HTTP exceptions with structured response."""
        payload = _error_payload(
            error_type="http_exception",
            message=str(exc.detail),
            request=request,
            status_code=exc.status_code,
        )
        return JSONResponse(status_code=exc.status_code, content=payload)

    @app.exception_handler(RequestValidationError)
    async def validation_exception_handler(
        request: Request, exc: RequestValidationError
    ) -> JSONResponse:
        """Handle validation errors with detailed field information."""
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

        payload = _error_payload(
            error_type="validation_error",
            message="Request validation failed",
            request=request,
            status_code=422,
            details=serializable_errors,
        )
        return JSONResponse(status_code=422, content=payload)

    @app.exception_handler(Exception)
    async def unhandled_exception_handler(
        request: Request, exc: Exception
    ) -> JSONResponse:
        """Handle unhandled exceptions with generic error response."""
        payload = _error_payload(
            error_type="internal_error",
            message="Internal Server Error",
            request=request,
            status_code=500,
        )
        return JSONResponse(status_code=500, content=payload)
