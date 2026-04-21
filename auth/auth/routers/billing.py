"""Billing router: Stripe subscription checkout, portal, status, and webhooks."""
import uuid
from datetime import datetime, timezone
from typing import Optional

import stripe
from fastapi import APIRouter, Depends, Header, HTTPException, Request, status
from pydantic import BaseModel

from auth.core.database import get_cursor, get_db
from auth.core.settings import get_settings
from auth.routers.auth import get_current_user

settings = get_settings()

router = APIRouter(prefix="/billing", tags=["billing"])

_FREE_SUBSCRIPTION = {
    "plan": "free",
    "status": "active",
    "current_period_end": None,
    "cancel_at_period_end": False,
}


def _require_stripe() -> None:
    """Raise 503 if Stripe is not configured."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured",
        )
    stripe.api_key = settings.stripe_secret_key


def _get_subscription(user_id: str) -> Optional[dict]:
    """Fetch the subscription row for a user, or None if not found."""
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT * FROM subscriptions WHERE user_id = ?",
            (user_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _get_subscription_by_customer(stripe_customer_id: str) -> Optional[dict]:
    with get_db() as conn:
        cur = get_cursor(conn)
        cur.execute(
            "SELECT * FROM subscriptions WHERE stripe_customer_id = ?",
            (stripe_customer_id,),
        )
        row = cur.fetchone()
        return dict(row) if row else None


def _upsert_subscription(
    user_id: str,
    stripe_customer_id: Optional[str],
    stripe_subscription_id: Optional[str],
    plan: str,
    sub_status: str,
    current_period_end: Optional[str],
    cancel_at_period_end: int,
) -> None:
    now = datetime.now(timezone.utc).isoformat()
    existing = _get_subscription(user_id)
    with get_db() as conn:
        cur = get_cursor(conn)
        if existing:
            cur.execute(
                """UPDATE subscriptions
                   SET stripe_customer_id = ?,
                       stripe_subscription_id = ?,
                       plan = ?,
                       status = ?,
                       current_period_end = ?,
                       cancel_at_period_end = ?,
                       updated_at = ?
                   WHERE user_id = ?""",
                (
                    stripe_customer_id,
                    stripe_subscription_id,
                    plan,
                    sub_status,
                    current_period_end,
                    cancel_at_period_end,
                    now,
                    user_id,
                ),
            )
        else:
            sub_id = str(uuid.uuid4())
            cur.execute(
                """INSERT INTO subscriptions
                   (id, user_id, stripe_customer_id, stripe_subscription_id,
                    plan, status, current_period_end, cancel_at_period_end,
                    created_at, updated_at)
                   VALUES (?, ?, ?, ?, ?, ?, ?, ?, ?, ?)""",
                (
                    sub_id,
                    user_id,
                    stripe_customer_id,
                    stripe_subscription_id,
                    plan,
                    sub_status,
                    current_period_end,
                    cancel_at_period_end,
                    now,
                    now,
                ),
            )


def _plan_from_price_id(price_id: Optional[str]) -> str:
    """Map a Stripe Price ID to a plan name."""
    if price_id == settings.stripe_pro_price_id and price_id:
        return "pro"
    if price_id == settings.stripe_team_price_id and price_id:
        return "team"
    return "free"


# ---------------------------------------------------------------------------
# Request/response models
# ---------------------------------------------------------------------------

class CheckoutRequest(BaseModel):
    plan: str  # 'pro' | 'team'


# ---------------------------------------------------------------------------
# Endpoints
# ---------------------------------------------------------------------------

@router.post("/checkout")
async def create_checkout_session(
    body: CheckoutRequest,
    current_user: dict = Depends(get_current_user),
):
    """Create a Stripe Checkout session for upgrading to a paid plan."""
    _require_stripe()

    if body.plan not in ("pro", "team"):
        raise HTTPException(status_code=400, detail="Invalid plan. Choose 'pro' or 'team'.")

    price_id = (
        settings.stripe_pro_price_id
        if body.plan == "pro"
        else settings.stripe_team_price_id
    )
    if not price_id:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured",
        )

    # Resolve or create a Stripe customer for this user
    existing_sub = _get_subscription(current_user["id"])
    stripe_customer_id = existing_sub.get("stripe_customer_id") if existing_sub else None

    if not stripe_customer_id:
        customer = stripe.Customer.create(
            email=current_user["email"],
            name=current_user.get("full_name") or "",
            metadata={"user_id": current_user["id"]},
        )
        stripe_customer_id = customer.id

    session = stripe.checkout.Session.create(
        customer=stripe_customer_id,
        payment_method_types=["card"],
        line_items=[{"price": price_id, "quantity": 1}],
        mode="subscription",
        success_url="https://app.artemisplatform.com/billing/success",
        cancel_url="https://app.artemisplatform.com/billing/cancel",
        metadata={"user_id": current_user["id"]},
    )

    return {"checkout_url": session.url}


@router.get("/portal")
async def customer_portal(
    current_user: dict = Depends(get_current_user),
):
    """Return a Stripe Customer Portal URL for managing the subscription."""
    _require_stripe()

    existing_sub = _get_subscription(current_user["id"])
    stripe_customer_id = existing_sub.get("stripe_customer_id") if existing_sub else None

    if not stripe_customer_id:
        raise HTTPException(
            status_code=status.HTTP_404_NOT_FOUND,
            detail="No billing account found. Subscribe first.",
        )

    portal = stripe.billing_portal.Session.create(
        customer=stripe_customer_id,
        return_url="https://app.artemisplatform.com/billing",
    )

    return {"portal_url": portal.url}


@router.get("/subscription")
async def get_subscription(
    current_user: dict = Depends(get_current_user),
):
    """Return the current subscription status for the authenticated user."""
    sub = _get_subscription(current_user["id"])

    if not sub:
        return _FREE_SUBSCRIPTION

    return {
        "plan": sub.get("plan", "free"),
        "status": sub.get("status", "active"),
        "current_period_end": sub.get("current_period_end"),
        "cancel_at_period_end": bool(sub.get("cancel_at_period_end", 0)),
    }


@router.post("/webhook")
async def stripe_webhook(
    request: Request,
    stripe_signature: Optional[str] = Header(None, alias="stripe-signature"),
):
    """Handle Stripe webhook events. Stripe is the source of truth for subscription state."""
    if not settings.stripe_secret_key:
        raise HTTPException(
            status_code=status.HTTP_503_SERVICE_UNAVAILABLE,
            detail="Billing not configured",
        )

    stripe.api_key = settings.stripe_secret_key
    payload = await request.body()

    try:
        event = stripe.Webhook.construct_event(
            payload, stripe_signature, settings.stripe_webhook_secret
        )
    except stripe.error.SignatureVerificationError:
        raise HTTPException(status_code=400, detail="Invalid signature")
    except Exception:
        raise HTTPException(status_code=400, detail="Invalid payload")

    event_type = event["type"]
    data = event["data"]["object"]

    if event_type == "checkout.session.completed":
        user_id = data.get("metadata", {}).get("user_id")
        stripe_customer_id = data.get("customer")
        stripe_subscription_id = data.get("subscription")

        if user_id and stripe_subscription_id:
            # Retrieve the subscription object from Stripe to get plan details
            stripe_sub = stripe.Subscription.retrieve(stripe_subscription_id)
            price_id = None
            if stripe_sub.get("items") and stripe_sub["items"]["data"]:
                price_id = stripe_sub["items"]["data"][0]["price"]["id"]

            plan = _plan_from_price_id(price_id)
            sub_status = stripe_sub.get("status", "active")
            period_end_ts = stripe_sub.get("current_period_end")
            period_end = (
                datetime.fromtimestamp(period_end_ts, tz=timezone.utc).isoformat()
                if period_end_ts
                else None
            )
            cancel_at_period_end = int(stripe_sub.get("cancel_at_period_end", False))

            _upsert_subscription(
                user_id=user_id,
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                plan=plan,
                sub_status=sub_status,
                current_period_end=period_end,
                cancel_at_period_end=cancel_at_period_end,
            )

    elif event_type == "customer.subscription.updated":
        stripe_customer_id = data.get("customer")
        stripe_subscription_id = data.get("id")

        price_id = None
        if data.get("items") and data["items"]["data"]:
            price_id = data["items"]["data"][0]["price"]["id"]

        plan = _plan_from_price_id(price_id)
        sub_status = data.get("status", "active")
        period_end_ts = data.get("current_period_end")
        period_end = (
            datetime.fromtimestamp(period_end_ts, tz=timezone.utc).isoformat()
            if period_end_ts
            else None
        )
        cancel_at_period_end = int(data.get("cancel_at_period_end", False))

        existing = _get_subscription_by_customer(stripe_customer_id)
        if existing:
            _upsert_subscription(
                user_id=existing["user_id"],
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=stripe_subscription_id,
                plan=plan,
                sub_status=sub_status,
                current_period_end=period_end,
                cancel_at_period_end=cancel_at_period_end,
            )

    elif event_type == "customer.subscription.deleted":
        stripe_customer_id = data.get("customer")

        existing = _get_subscription_by_customer(stripe_customer_id)
        if existing:
            _upsert_subscription(
                user_id=existing["user_id"],
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=data.get("id"),
                plan="free",
                sub_status="canceled",
                current_period_end=None,
                cancel_at_period_end=0,
            )

    elif event_type == "invoice.payment_failed":
        stripe_customer_id = data.get("customer")

        existing = _get_subscription_by_customer(stripe_customer_id)
        if existing:
            _upsert_subscription(
                user_id=existing["user_id"],
                stripe_customer_id=stripe_customer_id,
                stripe_subscription_id=existing.get("stripe_subscription_id"),
                plan=existing.get("plan", "free"),
                sub_status="past_due",
                current_period_end=existing.get("current_period_end"),
                cancel_at_period_end=existing.get("cancel_at_period_end", 0),
            )

    return {"received": True}
