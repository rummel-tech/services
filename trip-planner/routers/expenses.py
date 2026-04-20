"""Expense tracking — log and summarize trip spending."""
import logging
import uuid
from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends, HTTPException

import sys, os
sys.path.insert(0, os.path.join(os.path.dirname(__file__), '..', '..'))

from common.database import get_connection, get_cursor, adapt_query, dict_from_row
from core.database import USE_SQLITE
from routers.auth import require_token, TokenData
from schemas.models import ExpenseCreate, ExpenseUpdate, ExpenseResponse, BudgetSummaryResponse

router = APIRouter(prefix="/trips", tags=["expenses"])
logger = logging.getLogger(__name__)

VALID_CATEGORIES = {"accommodation", "transport", "food", "activities", "shopping", "misc"}


def _assert_trip_owner(trip_id: str, user_id: str, conn):
    cur = get_cursor(conn)
    cur.execute(
        adapt_query("SELECT id, budget_cents FROM trips WHERE id = %s AND user_id = %s", USE_SQLITE),
        (trip_id, user_id),
    )
    row = cur.fetchone()
    if not row:
        raise HTTPException(404, "Trip not found")
    return dict_from_row(row, USE_SQLITE)


@router.get("/{trip_id}/expenses", response_model=List[ExpenseResponse])
async def list_expenses(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT * FROM trip_expenses WHERE trip_id = %s ORDER BY expense_date DESC, added_at DESC",
                USE_SQLITE,
            ),
            (trip_id,),
        )
        return [ExpenseResponse(**dict_from_row(r, USE_SQLITE)) for r in cur.fetchall()]


@router.get("/{trip_id}/budget", response_model=BudgetSummaryResponse)
async def get_budget_summary(trip_id: str, token: TokenData = Depends(require_token)):
    with get_connection() as conn:
        trip = _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "SELECT category, SUM(amount_cents) AS total FROM trip_expenses"
                " WHERE trip_id = %s GROUP BY category",
                USE_SQLITE,
            ),
            (trip_id,),
        )
        by_category = {
            dict_from_row(r, USE_SQLITE)["category"]: dict_from_row(r, USE_SQLITE)["total"]
            for r in cur.fetchall()
        }
        spent = sum(by_category.values())
        budget = trip.get("budget_cents", 0) or 0
        return BudgetSummaryResponse(
            budget_cents=budget,
            spent_cents=spent,
            remaining_cents=max(0, budget - spent),
            by_category=by_category,
        )


@router.post("/{trip_id}/expenses", response_model=ExpenseResponse, status_code=201)
async def add_expense(
    trip_id: str,
    body: ExpenseCreate,
    token: TokenData = Depends(require_token),
):
    if body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")

    expense_id = str(uuid.uuid4())
    now = datetime.now(timezone.utc).isoformat()

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "INSERT INTO trip_expenses (id, trip_id, category, description, amount_cents, expense_date, added_at)"
                " VALUES (%s,%s,%s,%s,%s,%s,%s)",
                USE_SQLITE,
            ),
            (expense_id, trip_id, body.category, body.description, body.amount_cents, body.expense_date, now),
        )
        conn.commit()
    return ExpenseResponse(
        id=expense_id, trip_id=trip_id, category=body.category,
        description=body.description, amount_cents=body.amount_cents,
        expense_date=body.expense_date, added_at=now,
    )


@router.patch("/{trip_id}/expenses/{expense_id}", response_model=ExpenseResponse)
async def update_expense(
    trip_id: str,
    expense_id: str,
    body: ExpenseUpdate,
    token: TokenData = Depends(require_token),
):
    if body.category and body.category not in VALID_CATEGORIES:
        raise HTTPException(400, f"category must be one of {sorted(VALID_CATEGORIES)}")

    updates = body.model_dump(exclude_none=True)
    if not updates:
        raise HTTPException(400, "No fields to update")

    set_clause = ", ".join(f"{k} = %s" for k in updates)
    values = list(updates.values()) + [expense_id, trip_id]

    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                f"UPDATE trip_expenses SET {set_clause} WHERE id = %s AND trip_id = %s",
                USE_SQLITE,
            ),
            values,
        )
        conn.commit()
        cur.execute(
            adapt_query("SELECT * FROM trip_expenses WHERE id = %s", USE_SQLITE), (expense_id,)
        )
        row = cur.fetchone()
        if not row:
            raise HTTPException(404, "Expense not found")
        return ExpenseResponse(**dict_from_row(row, USE_SQLITE))


@router.delete("/{trip_id}/expenses/{expense_id}", status_code=204)
async def delete_expense(
    trip_id: str, expense_id: str, token: TokenData = Depends(require_token)
):
    with get_connection() as conn:
        _assert_trip_owner(trip_id, token.user_id, conn)
        cur = get_cursor(conn)
        cur.execute(
            adapt_query(
                "DELETE FROM trip_expenses WHERE id = %s AND trip_id = %s", USE_SQLITE
            ),
            (expense_id, trip_id),
        )
        if cur.rowcount == 0:
            raise HTTPException(404, "Expense not found")
        conn.commit()
