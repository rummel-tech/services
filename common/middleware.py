"""
Standard middleware for all services.

Uses the shared correlation_id_var from logging_config so that both
create_app() and add_standard_middleware() write to the same context.
"""

import time

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

from .logging_config import correlation_id_var, set_correlation_id


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id_var.get() or ""


def add_standard_middleware(
    app: FastAPI,
    cors_origins: list[str] = ["*"],
    enable_security_headers: bool = True,
    enable_request_logging: bool = True,
    environment: str = "development",
) -> None:
    """
    Add standard middleware to a FastAPI application.

    Args:
        app: FastAPI application instance
        cors_origins: List of allowed CORS origins
        enable_security_headers: Whether to add security headers
        enable_request_logging: Whether to log requests with correlation IDs
        environment: Current environment (development/production)
    """

    # Security headers middleware
    if enable_security_headers:
        @app.middleware("http")
        async def security_headers_middleware(request: Request, call_next):
            response = await call_next(request)
            response.headers["X-Content-Type-Options"] = "nosniff"
            response.headers["X-Frame-Options"] = "DENY"
            response.headers["X-XSS-Protection"] = "1; mode=block"
            response.headers["Referrer-Policy"] = "strict-origin-when-cross-origin"

            if environment == "production":
                response.headers["Strict-Transport-Security"] = "max-age=31536000; includeSubDomains"

            return response

    # Request logging and correlation ID middleware
    if enable_request_logging:
        @app.middleware("http")
        async def request_logging_middleware(request: Request, call_next):
            cid = set_correlation_id(request.headers.get("X-Request-ID"))

            start_time = time.time()

            response = await call_next(request)

            duration_ms = int((time.time() - start_time) * 1000)
            response.headers["X-Request-ID"] = cid
            response.headers["X-Response-Time-Ms"] = str(duration_ms)

            return response

    # CORS middleware (added last, executes first)
    app.add_middleware(
        CORSMiddleware,
        allow_origins=cors_origins,
        allow_credentials=True,
        allow_methods=["*"],
        allow_headers=["*"],
    )
