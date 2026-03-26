from flask import Flask

from api import register_api_routes
from config import PORT, SHOW_ROUTE_DEBUG
from db import ensure_schema, wait_for_db
from views import register_context, register_routes


def create_app():
    wait_for_db()
    ensure_schema()
    app = Flask(__name__, static_url_path="/app/static")
    register_context(app)
    register_routes(app)
    register_api_routes(app)
    if SHOW_ROUTE_DEBUG:
        print("Routes registered:")
        for rule in app.url_map.iter_rules():
            print(f"{rule} -> {rule.endpoint}")
    return app


app = create_app()


if __name__ == "__main__":
    app.run(host="0.0.0.0", port=PORT)
