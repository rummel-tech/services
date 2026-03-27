"""Entry point for the Artemis Auth service."""
from auth.api.main import app

if __name__ == "__main__":
    import uvicorn
    from auth.core.settings import get_settings

    settings = get_settings()
    uvicorn.run(
        app,
        host=settings.host,
        port=settings.port,
        reload=settings.environment == "development",
        log_level=settings.log_level,
    )
