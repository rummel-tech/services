"""Pytest configuration for work-planner tests."""
import os
import sys
import tempfile
from pathlib import Path

# Set up environment before any imports
os.environ.setdefault("DATABASE_URL", f"sqlite:///{tempfile.gettempdir()}/work_test.db")
os.environ.setdefault("REDIS_ENABLED", "false")
os.environ.setdefault("ENVIRONMENT", "development")
os.environ.setdefault("DISABLE_AUTH", "true")

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
os.environ.setdefault("ENABLE_METRICS", "false")
