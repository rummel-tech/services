"""Pytest configuration for content-planner tests."""
import os
import sys
import tempfile
from pathlib import Path

os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/content_test.db")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DISABLE_AUTH", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
