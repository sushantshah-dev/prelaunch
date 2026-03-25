import os

from dotenv import load_dotenv


load_dotenv()


def env_int(name):
    value = os.environ.get(name, "").strip()
    return int(value) if value else None


def env_bool(name, default=False):
    value = os.environ.get(name)
    if value is None:
        return default
    return value.strip().lower() in {"1", "true", "yes", "on"}

PORT = int(os.environ.get("PORT", "3000"))
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_PATH = "/app"
SESSION_COOKIE_NAME = "prelaunch_session"
ALLOWED_PLANS = ["Free", "Starter", "Pro"]
SESSION_DAYS = 30
LEMONSQUEEZY_API_KEY = os.environ.get("LEMONSQUEEZY_API_KEY", "").strip()
LEMONSQUEEZY_STORE_ID = env_int("LEMONSQUEEZY_STORE_ID")
LEMONSQUEEZY_STARTER_VARIANT_ID = env_int("LEMONSQUEEZY_STARTER_VARIANT_ID")
LEMONSQUEEZY_PRO_VARIANT_ID = env_int("LEMONSQUEEZY_PRO_VARIANT_ID")
LEMONSQUEEZY_TEST_MODE = env_bool("LEMONSQUEEZY_TEST_MODE", default=False)
FREE_CREDITS_ONCE = int(os.environ.get("FREE_CREDITS_ONCE", "5"))
STARTER_CREDITS_MONTHLY = int(os.environ.get("STARTER_CREDITS_MONTHLY", "100"))
PRO_CREDITS_MONTHLY = int(os.environ.get("PRO_CREDITS_MONTHLY", "250"))
PROJECT_CREATION_CREDIT_COST = int(os.environ.get("PROJECT_CREATION_CREDIT_COST", "5"))
STANDALONE_TEST_CREDIT_COST = int(os.environ.get("STANDALONE_TEST_CREDIT_COST", "5"))
PROJECT_TEST_CREDIT_COST = int(os.environ.get("PROJECT_TEST_CREDIT_COST", "1"))
