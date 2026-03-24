from flask import Flask

from config import PORT
from db import wait_for_db
from views import register_context, register_routes


def create_app():
    app = Flask(__name__, static_url_path="/app/static")
    register_context(app)
    register_routes(app)
    return app


app = create_app()


if __name__ == "__main__":
    wait_for_db()
    app.run(host="0.0.0.0", port=PORT)
