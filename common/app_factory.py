"""
Factory for creating standardized FastAPI applications.
"""

import os
from dataclasses import dataclass, field
from typing import Optional

from fastapi import FastAPI

from .middleware import add_standard_middleware
from .error_handlers import install_error_handlers


@dataclass
class ServiceConfig:
    """Configuration for a service."""

    name: str
    title: str
    version: str = "0.1.0"
    description: str = ""
    port: int = 8000
    root_path: Optional[str] = None
    cors_origins: list[str] = field(default_factory=lambda: ["*"])
    environment: str = field(default_factory=lambda: os.getenv("ENVIRONMENT", "development"))
    enable_security_headers: bool = True
    enable_request_logging: bool = True
    enable_error_handlers: bool = True

    def __post_init__(self):
        # Allow root_path override from environment
        env_root_path = os.getenv("ROOT_PATH", "")
        if env_root_path:
            self.root_path = env_root_path


def create_app(config: ServiceConfig) -> FastAPI:
    """
    Create a FastAPI application with standard configuration.

    Args:
        config: Service configuration

    Returns:
        Configured FastAPI application
    """
    app = FastAPI(
        title=config.title,
        version=config.version,
        description=config.description,
        root_path=config.root_path or "",
    )

    # Add standard middleware
    add_standard_middleware(
        app,
        cors_origins=config.cors_origins,
        enable_security_headers=config.enable_security_headers,
        enable_request_logging=config.enable_request_logging,
        environment=config.environment,
    )

    # Add standard error handlers
    if config.enable_error_handlers:
        install_error_handlers(app)

    # Add standard health endpoints
    @app.get("/health", tags=["Health"])
    async def health():
        """Basic health check endpoint."""
        return {"status": "ok", "service": config.name}

    @app.get("/ready", tags=["Health"])
    async def ready():
        """Readiness check endpoint."""
        return {"status": "ready", "service": config.name}

    @app.get("/", tags=["Root"])
    async def root():
        """Service information endpoint."""
        return {
            "service": config.name,
            "title": config.title,
            "version": config.version,
            "status": "operational",
            "environment": config.environment,
            "endpoints": {
                "health": "/health",
                "readiness": "/ready",
                "documentation": "/docs",
            },
        }

    return app
