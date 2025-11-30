"""
Standard middleware for all services.
"""

import time
import uuid
from typing import Optional
from contextvars import ContextVar

from fastapi import FastAPI, Request
from fastapi.middleware.cors import CORSMiddleware

# Context variable for request correlation ID
correlation_id_var: ContextVar[str] = ContextVar("correlation_id", default="")


def get_correlation_id() -> str:
    """Get the current request's correlation ID."""
    return correlation_id_var.get()


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
            # Generate or extract correlation ID
            cid = request.headers.get("X-Request-ID", str(uuid.uuid4()))
            correlation_id_var.set(cid)

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
