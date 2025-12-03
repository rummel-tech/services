"""
Pytest configuration for home-manager tests.
"""

import os
import sys
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

# Add paths for imports
test_file = Path(__file__).resolve()
service_root = test_file.parents[1]
services_root = test_file.parents[2]

sys.path.insert(0, str(service_root))
sys.path.insert(0, str(services_root))


@pytest.fixture(scope="module")
def client():
    """Create a test client for the home-manager API."""
    from main import app

    return TestClient(app)
