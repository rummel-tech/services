"""Entry point for the Artemis platform service."""
from artemis.api.main import app

if __name__ == "__main__":
    import uvicorn
    from artemis.core.settings import get_settings

    s = get_settings()
    uvicorn.run(app, host=s.host, port=s.port, reload=s.environment == "development", log_level=s.log_level)
