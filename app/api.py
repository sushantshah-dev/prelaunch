from flask import jsonify

from config import BASE_PATH


def register_api_routes(app):
    @app.get(f"{BASE_PATH}/api/health")
    def api_health():
        return jsonify({"status": "ok"}), 200
