import time

import psycopg

from config import DATABASE_URL


SCHEMA_STATEMENTS = [
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS lemonsqueezy_customer_id BIGINT
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS lemonsqueezy_subscription_id BIGINT
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS lemonsqueezy_variant_id BIGINT
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS lemonsqueezy_subscription_status TEXT
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS lemonsqueezy_last_synced_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS credits_remaining INTEGER NOT NULL DEFAULT 0
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS credits_renews_at TIMESTAMPTZ
    """,
    """
    ALTER TABLE users
    ADD COLUMN IF NOT EXISTS credits_plan TEXT
    """,
    """
    CREATE TABLE IF NOT EXISTS lemonsqueezy_subscriptions (
        id BIGINT PRIMARY KEY,
        store_id BIGINT,
        customer_id BIGINT,
        order_id BIGINT,
        order_item_id BIGINT,
        product_id BIGINT,
        variant_id BIGINT,
        status TEXT,
        cancelled BOOLEAN,
        pause JSONB,
        product_name TEXT,
        variant_name TEXT,
        user_name TEXT,
        user_email TEXT,
        card_brand TEXT,
        card_last_four TEXT,
        renews_at TIMESTAMPTZ,
        ends_at TIMESTAMPTZ,
        trial_ends_at TIMESTAMPTZ,
        raw_attributes JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE TABLE IF NOT EXISTS lemonsqueezy_webhook_events (
        id BIGSERIAL PRIMARY KEY,
        event_name TEXT NOT NULL,
        subscription_id BIGINT,
        payload JSONB NOT NULL,
        processed_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS lemonsqueezy_webhook_events_subscription_id_idx
    ON lemonsqueezy_webhook_events (subscription_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS lemonsqueezy_subscription_invoices (
        id BIGINT PRIMARY KEY,
        subscription_id BIGINT NOT NULL,
        store_id BIGINT,
        customer_id BIGINT,
        user_name TEXT,
        user_email TEXT,
        billing_reason TEXT,
        card_brand TEXT,
        card_last_four TEXT,
        currency TEXT,
        status TEXT,
        refunded BOOLEAN,
        refunded_at TIMESTAMPTZ,
        subtotal INTEGER,
        discount_total INTEGER,
        tax INTEGER,
        tax_inclusive BOOLEAN,
        total INTEGER,
        refunded_amount INTEGER,
        subtotal_usd INTEGER,
        discount_total_usd INTEGER,
        tax_usd INTEGER,
        total_usd INTEGER,
        refunded_amount_usd INTEGER,
        raw_attributes JSONB NOT NULL,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS lemonsqueezy_subscription_invoices_subscription_id_idx
    ON lemonsqueezy_subscription_invoices (subscription_id)
    """,
    """
    CREATE TABLE IF NOT EXISTS subscription_change_requests (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        requested_plan TEXT NOT NULL,
        requested_variant_id BIGINT NOT NULL,
        previous_subscription_id BIGINT,
        previous_variant_id BIGINT,
        status TEXT NOT NULL DEFAULT 'pending',
        replacement_subscription_id BIGINT,
        requested_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        resolved_at TIMESTAMPTZ
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS subscription_change_requests_user_status_idx
    ON subscription_change_requests (user_id, status, requested_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS projects (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        name TEXT NOT NULL,
        description TEXT NOT NULL DEFAULT '',
        idea_score NUMERIC(5,2) NOT NULL DEFAULT 50,
        perception_score NUMERIC(5,2) NOT NULL DEFAULT 50,
        spread_score NUMERIC(5,2) NOT NULL DEFAULT 50,
        live_signal_score NUMERIC(5,2) NOT NULL DEFAULT 50,
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS projects_user_id_idx
    ON projects (user_id, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS project_pipeline_runs (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        stage TEXT NOT NULL,
        status TEXT NOT NULL DEFAULT 'pending',
        score NUMERIC(5,2),
        summary TEXT NOT NULL DEFAULT 'TODO: implement pipeline logic',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        updated_at TIMESTAMPTZ NOT NULL DEFAULT NOW(),
        UNIQUE (project_id, stage)
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS project_pipeline_runs_project_id_idx
    ON project_pipeline_runs (project_id, updated_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS project_materials (
        id BIGSERIAL PRIMARY KEY,
        project_id BIGINT NOT NULL REFERENCES projects(id) ON DELETE CASCADE,
        content TEXT NOT NULL,
        idea_score NUMERIC(5,2) NOT NULL DEFAULT 0,
        live_signal_score NUMERIC(5,2),
        perception_score NUMERIC(5,2),
        spread_score NUMERIC(5,2),
        idea_summary TEXT NOT NULL DEFAULT '',
        live_signal_summary TEXT NOT NULL DEFAULT '',
        perception_summary TEXT NOT NULL DEFAULT '',
        spread_summary TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS project_materials_project_id_idx
    ON project_materials (project_id, created_at DESC)
    """,
    """
    CREATE TABLE IF NOT EXISTS one_off_tests (
        id BIGSERIAL PRIMARY KEY,
        user_id INTEGER NOT NULL REFERENCES users(id) ON DELETE CASCADE,
        mode TEXT NOT NULL DEFAULT 'idea',
        prompt TEXT NOT NULL,
        idea_score NUMERIC(5,2) NOT NULL DEFAULT 0,
        live_signal_score NUMERIC(5,2),
        perception_score NUMERIC(5,2),
        spread_score NUMERIC(5,2),
        idea_summary TEXT NOT NULL DEFAULT '',
        live_signal_summary TEXT NOT NULL DEFAULT '',
        perception_summary TEXT NOT NULL DEFAULT '',
        spread_summary TEXT NOT NULL DEFAULT '',
        created_at TIMESTAMPTZ NOT NULL DEFAULT NOW()
    )
    """,
    """
    CREATE INDEX IF NOT EXISTS one_off_tests_user_id_idx
    ON one_off_tests (user_id, created_at DESC)
    """,
    """
    ALTER TABLE one_off_tests
    ADD COLUMN IF NOT EXISTS mode TEXT NOT NULL DEFAULT 'idea'
    """,
]


def db_connection():
    return psycopg.connect(DATABASE_URL)


def wait_for_db(attempts=20, delay_seconds=1.5):
    for attempt in range(attempts):
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except psycopg.Error:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)


def ensure_schema():
    with db_connection() as conn:
        with conn.cursor() as cur:
            for statement in SCHEMA_STATEMENTS:
                cur.execute(statement)
