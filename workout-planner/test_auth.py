"""Tests for authentication endpoints."""
import pytest
from fastapi.testclient import TestClient
from main import app
from database import init_sqlite
import os

client = TestClient(app)

@pytest.fixture(autouse=True)
def setup_test_db():
    """Reset database before each test."""
    test_db = "fitness_auth_test.db"
    if os.path.exists(test_db):
        os.remove(test_db)
    
    import database
    database.DATABASE_URL = f"sqlite:///{test_db}"
    init_sqlite()
    
    yield
    
    if os.path.exists(test_db):
        os.remove(test_db)


def test_register_success():
    """Test successful user registration."""
    response = client.post(
        "/auth/register",
        json={
            "email": "test@example.com",
            "password": "password123",
            "full_name": "Test User"
        }
    )
    assert response.status_code == 201
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data
    assert data["token_type"] == "bearer"


def test_register_duplicate_email():
    """Test registration with existing email."""
    # First registration
    client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "password123"
        }
    )
    
    # Duplicate registration
    response = client.post(
        "/auth/register",
        json={
            "email": "duplicate@example.com",
            "password": "newpassword"
        }
    )
    assert response.status_code == 400
    assert "already registered" in response.json()["detail"].lower()


def test_login_success():
    """Test successful login."""
    # Register user first
    client.post(
        "/auth/register",
        json={
            "email": "login@example.com",
            "password": "password123"
        }
    )
    
    # Login
    response = client.post(
        "/auth/login",
        json={
            "email": "login@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_login_wrong_password():
    """Test login with incorrect password."""
    # Register user
    client.post(
        "/auth/register",
        json={
            "email": "wrongpass@example.com",
            "password": "correctpass"
        }
    )
    
    # Try wrong password
    response = client.post(
        "/auth/login",
        json={
            "email": "wrongpass@example.com",
            "password": "wrongpass"
        }
    )
    assert response.status_code == 401


def test_login_nonexistent_user():
    """Test login with non-existent user."""
    response = client.post(
        "/auth/login",
        json={
            "email": "nonexistent@example.com",
            "password": "password123"
        }
    )
    assert response.status_code == 401


def test_get_current_user():
    """Test getting current user info."""
    # Register and get token
    register_response = client.post(
        "/auth/register",
        json={
            "email": "currentuser@example.com",
            "password": "password123",
            "full_name": "Current User"
        }
    )
    token = register_response.json()["access_token"]
    
    # Get user info
    response = client.get(
        "/auth/me",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert data["email"] == "currentuser@example.com"
    assert data["full_name"] == "Current User"
    assert "id" in data
    assert data["is_active"] is True


def test_get_current_user_no_token():
    """Test accessing protected endpoint without token."""
    response = client.get("/auth/me")
    assert response.status_code == 403  # FastAPI security returns 403 for missing auth


def test_get_current_user_invalid_token():
    """Test accessing protected endpoint with invalid token."""
    response = client.get(
        "/auth/me",
        headers={"Authorization": "Bearer invalid_token_here"}
    )
    assert response.status_code == 401


def test_refresh_token():
    """Test refreshing access token."""
    # Register and get tokens
    register_response = client.post(
        "/auth/register",
        json={
            "email": "refresh@example.com",
            "password": "password123"
        }
    )
    refresh_token = register_response.json()["refresh_token"]
    
    # Refresh token
    response = client.post(
        "/auth/refresh",
        headers={"Authorization": f"Bearer {refresh_token}"}
    )
    assert response.status_code == 200
    data = response.json()
    assert "access_token" in data
    assert "refresh_token" in data


def test_logout():
    """Test logout endpoint."""
    # Register and get token
    register_response = client.post(
        "/auth/register",
        json={
            "email": "logout@example.com",
            "password": "password123"
        }
    )
    token = register_response.json()["access_token"]
    
    # Logout
    response = client.post(
        "/auth/logout",
        headers={"Authorization": f"Bearer {token}"}
    )
    assert response.status_code == 200
    assert "message" in response.json()
