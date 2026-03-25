import json
from datetime import datetime, timezone
from urllib import error, parse, request

from auth import normalize_plan
from config import (
    BASE_PATH,
    LEMONSQUEEZY_API_KEY,
    LEMONSQUEEZY_PRO_VARIANT_ID,
    LEMONSQUEEZY_STARTER_VARIANT_ID,
    LEMONSQUEEZY_STORE_ID,
    LEMONSQUEEZY_TEST_MODE,
)
from credits import get_user_credit_state
from db import db_connection


API_BASE_URL = "https://api.lemonsqueezy.com/v1"
PAID_STATUSES = {"active", "on_trial", "paused", "past_due", "unpaid", "cancelled"}
OPEN_SUBSCRIPTION_STATUSES = {"active", "on_trial", "paused", "past_due", "unpaid"}
STATUS_PRIORITY = {
    "active": 0,
    "on_trial": 1,
    "paused": 2,
    "past_due": 3,
    "unpaid": 4,
    "cancelled": 5,
    "expired": 6,
}
PLAN_VARIANT_IDS = {
    "Starter": LEMONSQUEEZY_STARTER_VARIANT_ID,
    "Pro": LEMONSQUEEZY_PRO_VARIANT_ID,
}
VARIANT_PLAN_IDS = {
    variant_id: plan for plan, variant_id in PLAN_VARIANT_IDS.items() if variant_id
}


class LemonSqueezyError(Exception):
    pass


def is_enabled():
    return bool(LEMONSQUEEZY_API_KEY and LEMONSQUEEZY_STORE_ID)


def is_paid_plan(plan):
    return bool(PLAN_VARIANT_IDS.get(plan))


def api_request(method, path, *, payload=None, query=None):
    if not is_enabled():
        raise LemonSqueezyError("Lemon Squeezy is not configured yet.")

    url = f"{API_BASE_URL}{path}"
    if query:
        url = f"{url}?{parse.urlencode(query)}"

    raw_payload = None
    headers = {
        "Accept": "application/vnd.api+json",
        "Authorization": f"Bearer {LEMONSQUEEZY_API_KEY}",
    }

    if payload is not None:
        raw_payload = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/vnd.api+json"

    req = request.Request(url, data=raw_payload, headers=headers, method=method)

    try:
        with request.urlopen(req, timeout=20) as response:
            body = response.read().decode("utf-8")
    except error.HTTPError as exc:
        body = exc.read().decode("utf-8", errors="replace")
        raise LemonSqueezyError(f"Lemon Squeezy API request failed ({exc.code}): {body}") from exc
    except error.URLError as exc:
        raise LemonSqueezyError("Unable to reach Lemon Squeezy.") from exc

    if not body:
        return {}

    return json.loads(body)


def get_variant_id_for_plan(plan):
    variant_id = PLAN_VARIANT_IDS.get(plan)
    if not variant_id:
        raise LemonSqueezyError(f"No Lemon Squeezy variant is configured for the {plan} plan.")
    return variant_id


def iso_to_datetime(value):
    if not value:
        return datetime.min.replace(tzinfo=timezone.utc)
    return datetime.fromisoformat(value.replace("Z", "+00:00"))


def select_subscription(items):
    if not items:
        return None

    def key(item):
        attributes = item.get("attributes") or {}
        status = attributes.get("status") or ""
        return (
            STATUS_PRIORITY.get(status, 99),
            -iso_to_datetime(attributes.get("updated_at")).timestamp(),
        )

    return sorted(items, key=key)[0]


def plan_from_subscription(item):
    if not item:
        return "Free"

    attributes = item.get("attributes") or {}
    status = attributes.get("status") or ""

    if status not in PAID_STATUSES:
        return "Free"

    variant_id = attributes.get("variant_id")
    if variant_id in VARIANT_PLAN_IDS:
        return VARIANT_PLAN_IDS[variant_id]

    return normalize_plan(attributes.get("variant_name"))


def get_customer_by_email(email):
    response = api_request(
        "GET",
        "/customers",
        query={
            "filter[store_id]": LEMONSQUEEZY_STORE_ID,
            "filter[email]": email,
            "page[size]": 1,
        },
    )
    data = response.get("data") or []
    return data[0] if data else None


def get_subscription_by_id(subscription_id):
    if not subscription_id:
        return None
    response = api_request("GET", f"/subscriptions/{subscription_id}")
    return response.get("data")


def list_subscriptions_by_email(email):
    response = api_request(
        "GET",
        "/subscriptions",
        query={
            "filter[store_id]": LEMONSQUEEZY_STORE_ID,
            "filter[user_email]": email,
            "page[size]": 100,
        },
    )
    return response.get("data") or []


def cancel_subscription(subscription_id):
    if not subscription_id:
        return None
    response = api_request("DELETE", f"/subscriptions/{subscription_id}")
    return response.get("data")


def build_return_url(app_url, suffix=""):
    base = f"{app_url.rstrip('/')}{BASE_PATH}/billing"
    return f"{base}{suffix}"


def create_checkout_url(user, plan, app_url):
    variant_id = get_variant_id_for_plan(plan)
    response = api_request(
        "POST",
        "/checkouts",
        payload={
            "data": {
                "type": "checkouts",
                "attributes": {
                    "checkout_data": {
                        "email": user["email"],
                        "name": user["name"] or user["email"].split("@", 1)[0],
                        "custom": {"user_id": str(user["id"]), "selected_plan": plan},
                    },
                    "checkout_options": {
                        "embed": False,
                        "media": False,
                        "logo": True,
                    },
                    "product_options": {
                        "enabled_variants": [variant_id],
                        "redirect_url": build_return_url(app_url, "?billing=return"),
                        "receipt_button_text": "Back to Prelaunch",
                        "receipt_link_url": build_return_url(app_url, "?billing=success"),
                    },
                    "expires_at": None,
                    "preview": False,
                    "test_mode": LEMONSQUEEZY_TEST_MODE,
                },
                "relationships": {
                    "store": {"data": {"type": "stores", "id": str(LEMONSQUEEZY_STORE_ID)}},
                    "variant": {"data": {"type": "variants", "id": str(variant_id)}},
                },
            }
        },
    )
    attributes = (response.get("data") or {}).get("attributes") or {}
    checkout_url = attributes.get("url")
    if not checkout_url:
        raise LemonSqueezyError("Lemon Squeezy did not return a checkout URL.")
    return checkout_url


def get_subscription_item_value(item, field):
    return (item.get("attributes") or {}).get(field)


def get_pending_subscription_change_request(user_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    requested_plan,
                    requested_variant_id,
                    previous_subscription_id,
                    previous_variant_id,
                    requested_at
                FROM subscription_change_requests
                WHERE user_id = %s AND status = 'pending'
                ORDER BY requested_at DESC
                LIMIT 1
                """,
                (user_id,),
            )
            row = cur.fetchone()

    if not row:
        return None

    return {
        "id": row[0],
        "requested_plan": row[1],
        "requested_variant_id": row[2],
        "previous_subscription_id": row[3],
        "previous_variant_id": row[4],
        "requested_at": row[5],
    }


def create_subscription_change_request(user, plan):
    requested_variant_id = get_variant_id_for_plan(plan)
    previous_subscription_id = user.get("lemonsqueezy_subscription_id")
    previous_variant_id = user.get("lemonsqueezy_variant_id")

    if not previous_subscription_id or previous_variant_id == requested_variant_id:
        return None

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscription_change_requests
                SET status = 'superseded', resolved_at = NOW()
                WHERE user_id = %s AND status = 'pending'
                """,
                (user["id"],),
            )
            cur.execute(
                """
                INSERT INTO subscription_change_requests (
                    user_id,
                    requested_plan,
                    requested_variant_id,
                    previous_subscription_id,
                    previous_variant_id
                )
                VALUES (%s, %s, %s, %s, %s)
                """,
                (
                    user["id"],
                    plan,
                    requested_variant_id,
                    previous_subscription_id,
                    previous_variant_id,
                ),
            )


def resolve_subscription_change_request(change_request_id, replacement_subscription_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE subscription_change_requests
                SET
                    status = 'completed',
                    replacement_subscription_id = %s,
                    resolved_at = NOW()
                WHERE id = %s
                """,
                (replacement_subscription_id, change_request_id),
            )


def find_replacement_subscription(change_request, subscriptions):
    matches = []
    for subscription in subscriptions:
        subscription_id = int(subscription["id"])
        attributes = subscription.get("attributes") or {}

        if subscription_id == change_request["previous_subscription_id"]:
            continue
        if attributes.get("variant_id") != change_request["requested_variant_id"]:
            continue
        if iso_to_datetime(attributes.get("created_at")) < change_request["requested_at"]:
            continue

        matches.append(subscription)

    return select_subscription(matches)


def cancel_other_subscriptions(replacement_subscription_id, subscriptions):
    for subscription in subscriptions:
        subscription_id = int(subscription["id"])
        if subscription_id == replacement_subscription_id:
            continue

        status = get_subscription_item_value(subscription, "status")
        if status not in OPEN_SUBSCRIPTION_STATUSES:
            continue

        cancel_subscription(subscription_id)


def reconcile_subscription_change(user, subscriptions):
    change_request = get_pending_subscription_change_request(user["id"])
    if not change_request:
        return None

    replacement = find_replacement_subscription(change_request, subscriptions)
    if not replacement:
        return {
            "status": "pending",
            "requested_plan": change_request["requested_plan"],
        }

    replacement_subscription_id = int(replacement["id"])
    cancel_other_subscriptions(replacement_subscription_id, subscriptions)
    resolve_subscription_change_request(change_request["id"], replacement_subscription_id)

    return {
        "status": "completed",
        "requested_plan": change_request["requested_plan"],
        "replacement_subscription_id": replacement_subscription_id,
    }


def update_user_billing_state(user_id, *, customer_id=None, subscription_id=None, variant_id=None, status=None, plan="Free"):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE users
                SET
                    selected_plan = %s,
                    lemonsqueezy_customer_id = %s,
                    lemonsqueezy_subscription_id = %s,
                    lemonsqueezy_variant_id = %s,
                    lemonsqueezy_subscription_status = %s,
                    lemonsqueezy_last_synced_at = NOW()
                WHERE id = %s
                """,
                (plan, customer_id, subscription_id, variant_id, status, user_id),
            )


def sync_user_subscription(user):
    if not is_enabled():
        return {
            **user,
            "billing_enabled": False,
            "billing_customer_portal_url": None,
            "billing_update_payment_url": None,
        }

    customer = get_customer_by_email(user["email"])
    subscriptions = list_subscriptions_by_email(user["email"])
    change_resolution = reconcile_subscription_change(user, subscriptions)
    if change_resolution and change_resolution["status"] == "completed":
        subscriptions = list_subscriptions_by_email(user["email"])

    subscription = None
    if user.get("lemonsqueezy_subscription_id"):
        existing = get_subscription_by_id(user["lemonsqueezy_subscription_id"])
        if existing and get_subscription_item_value(existing, "status") in OPEN_SUBSCRIPTION_STATUSES:
            subscription = existing

    if subscription is None:
        subscription = select_subscription(subscriptions)

    customer_attributes = (customer or {}).get("attributes") or {}
    subscription_attributes = (subscription or {}).get("attributes") or {}
    customer_id = int(customer["id"]) if customer else subscription_attributes.get("customer_id")
    subscription_id = int(subscription["id"]) if subscription else None
    variant_id = subscription_attributes.get("variant_id")
    status = subscription_attributes.get("status")
    plan = plan_from_subscription(subscription)
    customer_portal_url = (
        subscription_attributes.get("urls", {}).get("customer_portal")
        or customer_attributes.get("urls", {}).get("customer_portal")
    )
    update_payment_url = subscription_attributes.get("urls", {}).get("update_payment_method")

    update_user_billing_state(
        user["id"],
        customer_id=customer_id,
        subscription_id=subscription_id,
        variant_id=variant_id,
        status=status,
        plan=plan,
    )

    return {
        **user,
        "selected_plan": plan,
        "lemonsqueezy_customer_id": customer_id,
        "lemonsqueezy_subscription_id": subscription_id,
        "lemonsqueezy_variant_id": variant_id,
        "lemonsqueezy_subscription_status": status,
        "billing_enabled": True,
        "billing_customer_portal_url": customer_portal_url,
        "billing_update_payment_url": update_payment_url,
        "billing_change_request": change_resolution,
        **(get_user_credit_state(user["id"], plan) or {}),
    }
