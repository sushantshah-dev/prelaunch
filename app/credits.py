import calendar
from datetime import datetime, timezone

from config import (
    ALLOWED_PLANS,
    FREE_CREDITS_ONCE,
    PRO_CREDITS_MONTHLY,
    PROJECT_CREATION_CREDIT_COST,
    PROJECT_TEST_CREDIT_COST,
    STANDALONE_TEST_CREDIT_COST,
    STARTER_CREDITS_MONTHLY,
)
from db import db_connection


def normalize_credit_plan(value):
    return value if value in ALLOWED_PLANS else "Free"


def credit_allowance_for_plan(plan):
    normalized = normalize_credit_plan(plan)
    if normalized == "Starter":
        return STARTER_CREDITS_MONTHLY
    if normalized == "Pro":
        return PRO_CREDITS_MONTHLY
    return FREE_CREDITS_ONCE


def monthly_credits_reset(plan):
    return normalize_credit_plan(plan) in {"Starter", "Pro"}


def credit_error_message(plan):
    if monthly_credits_reset(plan):
        return "No credits remaining. Your balance will refresh on the next monthly reset."
    return "No credits remaining. Free credits are one-time only."


def add_one_month(value):
    year = value.year
    month = value.month + 1
    if month > 12:
        month = 1
        year += 1

    day = min(value.day, calendar.monthrange(year, month)[1])
    return value.replace(year=year, month=month, day=day)


def _apply_credit_policy(cur, user_id, plan):
    normalized_plan = normalize_credit_plan(plan)
    allowance = credit_allowance_for_plan(normalized_plan)
    now = datetime.now(timezone.utc)

    cur.execute(
        """
        SELECT credits_remaining, credits_renews_at, credits_plan
        FROM users
        WHERE id = %s
        FOR UPDATE
        """,
        (user_id,),
    )
    row = cur.fetchone()
    if not row:
        return None

    credits_remaining = row[0] if row[0] is not None else 0
    credits_renews_at = row[1]
    credits_plan = normalize_credit_plan(row[2]) if row[2] else None

    next_remaining = credits_remaining
    next_renews_at = credits_renews_at
    next_plan = normalized_plan

    if monthly_credits_reset(normalized_plan):
        if credits_plan != normalized_plan or credits_renews_at is None or now >= credits_renews_at:
            next_remaining = allowance
            next_renews_at = add_one_month(now)
    else:
        if credits_plan is None:
            next_remaining = allowance
        elif credits_plan != "Free":
            next_remaining = min(credits_remaining, allowance)
        next_renews_at = None

    if (
        next_remaining != credits_remaining
        or next_renews_at != credits_renews_at
        or next_plan != credits_plan
    ):
        cur.execute(
            """
            UPDATE users
            SET
                credits_remaining = %s,
                credits_renews_at = %s,
                credits_plan = %s
            WHERE id = %s
            """,
            (next_remaining, next_renews_at, next_plan, user_id),
        )

    return {
        "credits_remaining": next_remaining,
        "credits_renews_at": next_renews_at,
        "credits_plan": next_plan,
    }


def get_user_credit_state(user_id, plan):
    with db_connection() as conn:
        with conn.cursor() as cur:
            return _apply_credit_policy(cur, user_id, plan)


def project_creation_credit_cost():
    return PROJECT_CREATION_CREDIT_COST


def standalone_test_credit_cost():
    return STANDALONE_TEST_CREDIT_COST


def project_test_credit_cost():
    return PROJECT_TEST_CREDIT_COST


def consume_user_credit(user_id, plan, amount):
    with db_connection() as conn:
        with conn.cursor() as cur:
            return consume_user_credit_in_transaction(cur, user_id, plan, amount)


def consume_user_credit_in_transaction(cur, user_id, plan, amount):
    with db_connection() as conn:
        pass
    state = _apply_credit_policy(cur, user_id, plan)
    if not state:
        return None
    if state["credits_remaining"] < amount:
        return False

    next_remaining = state["credits_remaining"] - amount
    cur.execute(
        """
        UPDATE users
        SET credits_remaining = %s
        WHERE id = %s
        """,
        (next_remaining, user_id),
    )
    state["credits_remaining"] = next_remaining
    return state
