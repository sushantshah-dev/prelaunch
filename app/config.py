import os

PORT = int(os.environ.get("PORT", "3000"))
DATABASE_URL = os.environ["DATABASE_URL"]
BASE_PATH = "/app"
SESSION_COOKIE_NAME = "prelaunch_session"
ALLOWED_PLANS = ["Free", "Starter", "Pro"]
SESSION_DAYS = 30
