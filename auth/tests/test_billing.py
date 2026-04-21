"""Tests for the Artemis Auth billing endpoints."""
import os
import uuid
from datetime import datetime, timezone
from unittest.mock import MagicMock, patch

# Set env vars before any imports so settings picks them up
os.environ["DATABASE_URL"] = "sqlite:///test_billing.db"
os.environ["REDIS_ENABLED"] = "false"
os.environ["ENVIRONMENT"] = "development"
os.environ["DISABLE_AUTH"] = "true"
# Leave STRIPE_SECRET_KEY unset to test the "not configured" path

import pytest
from fastapi.testclient import TestClient

from auth.api.main import app

TEST_DB = "test_billing.db"


@pytest.fixture(scope="module")
def client():
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)
    with TestClient(app) as c:
        yield c
    if os.path.exists(TEST_DB):
        os.remove(TEST_DB)


@pytest.fixture(scope="module")
def auth_token(client):
    """Register a user and return a valid access token."""
    email = "billing_test@example.com"
    r = client.post(
        "/auth/register",
        json={"email": email, "password": "testpass123", "full_name": "Billing User"},
    )
    assert r.status_code == 201
    return r.json()["access_token"]


@pytest.fixture(scope="module")
def auth_headers(auth_token):
    return {"Authorization": f"Bearer {auth_token}"}


# ---------------------------------------------------------------------------
# GET /billing/subscription — no subscription row exists
# ---------------------------------------------------------------------------

def test_subscription_returns_free_when_no_row(client, auth_headers):
    """GET /billing/subscription returns free plan defaults when no subscription row exists."""
    r = client.get("/billing/subscription", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["plan"] == "free"
    assert data["status"] == "active"
    assert data["current_period_end"] is None
    assert data["cancel_at_period_end"] is False


# ---------------------------------------------------------------------------
# POST /billing/checkout — 503 when Stripe not configured
# ---------------------------------------------------------------------------

def test_checkout_503_when_stripe_not_configured(client, auth_headers):
    """POST /billing/checkout returns 503 when STRIPE_SECRET_KEY is not set."""
    r = client.post("/billing/checkout", json={"plan": "pro"}, headers=auth_headers)
    assert r.status_code == 503
    body = r.json()
    # The common error handler wraps HTTPException as {error: {message: ...}}
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "Billing not configured" in msg


# ---------------------------------------------------------------------------
# GET /billing/portal — 503 when Stripe not configured
# ---------------------------------------------------------------------------

def test_portal_503_when_stripe_not_configured(client, auth_headers):
    """GET /billing/portal returns 503 when STRIPE_SECRET_KEY is not set."""
    r = client.get("/billing/portal", headers=auth_headers)
    assert r.status_code == 503
    body = r.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "Billing not configured" in msg


# ---------------------------------------------------------------------------
# POST /billing/webhook — 400 on invalid signature
# ---------------------------------------------------------------------------

def test_webhook_400_on_invalid_signature(client):
    """POST /billing/webhook returns 400 when the Stripe signature is invalid."""
    # Temporarily set a stripe key so the signature check is reached
    with patch("auth.routers.billing.settings") as mock_settings:
        mock_settings.stripe_secret_key = "sk_test_fake"
        mock_settings.stripe_webhook_secret = "whsec_fake"

        import stripe as _stripe

        with patch.object(_stripe.Webhook, "construct_event", side_effect=_stripe.error.SignatureVerificationError("bad", "sig")):
            r = client.post(
                "/billing/webhook",
                content=b'{"type": "checkout.session.completed"}',
                headers={
                    "stripe-signature": "t=bad,v1=bad",
                    "Content-Type": "application/json",
                },
            )
    assert r.status_code == 400
    body = r.json()
    msg = body.get("detail") or body.get("error", {}).get("message", "")
    assert "signature" in msg.lower()


# ---------------------------------------------------------------------------
# GET /billing/subscription — returns correct data after direct DB insert
# ---------------------------------------------------------------------------

def test_subscription_returns_correct_data_after_db_insert(client, auth_headers):
    """GET /billing/subscription returns real data when a subscription row exists in the DB."""
    from auth.core.database import get_cursor, get_db

    # Get the user ID from /auth/me
    me_r = client.get("/auth/me", headers=auth_headers)
    assert me_r.status_code == 200
    user_id = me_r.json()["id"]

    period_end = "2026-05-20T00:00:00+00:00"
    sub_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            """INSERT INTO subscriptions
               (id, user_id, stripe_customer_id, stripe_subscription_id,
                plan, status, current_period_end, cancel_at_period_end,
                created_at, updated_at)
               VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
            (
                sub_id,
                user_id,
                "cus_testcustomer123",
                "sub_testsubscription456",
                "pro",
                "active",
                period_end,
                0,
                now,
                now,
            ),
        )

    r = client.get("/billing/subscription", headers=auth_headers)
    assert r.status_code == 200
    data = r.json()
    assert data["plan"] == "pro"
    assert data["status"] == "active"
    assert data["current_period_end"] == period_end
    assert data["cancel_at_period_end"] is False
