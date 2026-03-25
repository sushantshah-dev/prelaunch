import hashlib
import secrets
from datetime import datetime, timedelta, timezone

import psycopg
from werkzeug.security import check_password_hash, generate_password_hash

from config import ALLOWED_PLANS, SESSION_COOKIE_NAME, SESSION_DAYS
from credits import get_user_credit_state
from db import db_connection


def normalize_plan(value):
    return value if value in ALLOWED_PLANS else "Free"


def sha256(value):
    return hashlib.sha256(value.encode("utf-8")).hexdigest()


def set_session_cookie(response, token):
    response.set_cookie(
        SESSION_COOKIE_NAME,
        token,
        max_age=SESSION_DAYS * 24 * 60 * 60,
        httponly=True,
        samesite="Lax",
        path="/",
    )


def clear_session_cookie(response):
    response.set_cookie(
        SESSION_COOKIE_NAME,
        "",
        max_age=0,
        httponly=True,
        samesite="Lax",
        path="/",
    )


def create_session(user_id):
    token = secrets.token_hex(32)
    token_hash = sha256(token)
    expires_at = datetime.now(timezone.utc) + timedelta(days=SESSION_DAYS)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "INSERT INTO sessions (user_id, token_hash, expires_at) VALUES (%s, %s, %s)",
                (user_id, token_hash, expires_at),
            )

    return token


def get_current_user(request):
    token = request.cookies.get(SESSION_COOKIE_NAME)
    if not token:
        return None

    token_hash = sha256(token)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    users.id,
                    users.name,
                    users.email,
                    users.selected_plan,
                    users.lemonsqueezy_customer_id,
                    users.lemonsqueezy_subscription_id,
                    users.lemonsqueezy_variant_id,
                    users.lemonsqueezy_subscription_status,
                    users.lemonsqueezy_last_synced_at
                FROM sessions
                JOIN users ON users.id = sessions.user_id
                WHERE sessions.token_hash = %s AND sessions.expires_at > NOW()
                LIMIT 1
                """,
                (token_hash,),
            )
            row = cur.fetchone()

    if not row:
        return None

    credit_state = get_user_credit_state(row[0], row[3])

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "selected_plan": row[3],
        "lemonsqueezy_customer_id": row[4],
        "lemonsqueezy_subscription_id": row[5],
        "lemonsqueezy_variant_id": row[6],
        "lemonsqueezy_subscription_status": row[7],
        "lemonsqueezy_last_synced_at": row[8],
        "credits_remaining": credit_state["credits_remaining"] if credit_state else 0,
        "credits_renews_at": credit_state["credits_renews_at"] if credit_state else None,
        "credits_plan": credit_state["credits_plan"] if credit_state else row[3],
    }


def signup_user(name, email, password, plan):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO users (name, email, password_hash, selected_plan)
                VALUES (%s, %s, %s, %s)
                RETURNING id
                """,
                (name, email, generate_password_hash(password), plan),
            )
            return cur.fetchone()[0]


def authenticate_user(email, password):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "SELECT id, name, email, password_hash, selected_plan FROM users WHERE email = %s LIMIT 1",
                (email,),
            )
            row = cur.fetchone()

    if not row or not check_password_hash(row[3], password):
        return None

    return {
        "id": row[0],
        "name": row[1],
        "email": row[2],
        "selected_plan": row[4],
    }


def delete_session(token):
    if not token:
        return

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute("DELETE FROM sessions WHERE token_hash = %s", (sha256(token),))


def is_unique_violation(error):
    return isinstance(error, psycopg.errors.UniqueViolation)
