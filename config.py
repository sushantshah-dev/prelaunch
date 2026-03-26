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


def env_required(name):
    value = os.environ.get(name, "").strip()
    if not value:
        raise RuntimeError(f"Missing required environment variable: {name}")
    return value


PORT = int(os.environ.get("PORT", "3000"))
DATABASE_URL = env_required("DATABASE_URL")
BASE_PATH = "/app"
SESSION_COOKIE_NAME = "prelaunch_session"
SESSION_COOKIE_SECURE = env_bool("SESSION_COOKIE_SECURE", default=False)
ALLOWED_PLANS = ["Free", "Starter", "Pro"]
SESSION_DAYS = 30
LEMONSQUEEZY_API_KEY = os.environ.get("LEMONSQUEEZY_API_KEY", "").strip()
LEMONSQUEEZY_STORE_ID = env_int("LEMONSQUEEZY_STORE_ID")
LEMONSQUEEZY_STARTER_VARIANT_ID = env_int("LEMONSQUEEZY_STARTER_VARIANT_ID")
LEMONSQUEEZY_PRO_VARIANT_ID = env_int("LEMONSQUEEZY_PRO_VARIANT_ID")
LEMONSQUEEZY_TEST_MODE = env_bool("LEMONSQUEEZY_TEST_MODE", default=False)
SHOW_ROUTE_DEBUG = env_bool("SHOW_ROUTE_DEBUG", default=False)
RUN_ANALYSIS_WORKER = env_bool("RUN_ANALYSIS_WORKER", default=True)
OPENROUTER_API_KEY = os.environ.get("OPENROUTER_API_KEY", "").strip()
OPENROUTER_BASE_URL = os.environ.get("OPENROUTER_BASE_URL", "https://openrouter.ai/api/v1").rstrip("/")
OPENROUTER_ANALYSIS_MODEL = os.environ.get("OPENROUTER_ANALYSIS_MODEL", "nvidia/nemotron-3-super-120b-a12b:free").strip()
OPENROUTER_LIVE_SIGNALS_MODEL = os.environ.get("OPENROUTER_LIVE_SIGNALS_MODEL", OPENROUTER_ANALYSIS_MODEL).strip()
OPENROUTER_APP_URL = os.environ.get("OPENROUTER_APP_URL", "").strip()
OPENROUTER_APP_NAME = os.environ.get("OPENROUTER_APP_NAME", "Prelaunch").strip()
FREE_CREDITS_ONCE = int(os.environ.get("FREE_CREDITS_ONCE", "5"))
STARTER_CREDITS_MONTHLY = int(os.environ.get("STARTER_CREDITS_MONTHLY", "100"))
PRO_CREDITS_MONTHLY = int(os.environ.get("PRO_CREDITS_MONTHLY", "250"))
PROJECT_CREATION_CREDIT_COST = int(os.environ.get("PROJECT_CREATION_CREDIT_COST", "5"))
STANDALONE_TEST_CREDIT_COST = int(os.environ.get("STANDALONE_TEST_CREDIT_COST", "5"))
PROJECT_TEST_CREDIT_COST = int(os.environ.get("PROJECT_TEST_CREDIT_COST", "1"))
FREE_PERSONAS_PER_TEST = int(os.environ.get("FREE_PERSONAS_PER_TEST", os.environ.get("FREE_PERSONAS_PER_RUN", "2")))
STARTER_PERSONAS_PER_TEST = int(os.environ.get("STARTER_PERSONAS_PER_TEST", os.environ.get("STARTER_PERSONAS_PER_RUN", "6")))
PRO_PERSONAS_PER_TEST = int(os.environ.get("PRO_PERSONAS_PER_TEST", os.environ.get("PRO_PERSONAS_PER_RUN", "12")))
