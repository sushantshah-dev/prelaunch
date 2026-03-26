from flask import jsonify, request

from auth import get_current_user
from config import BASE_PATH
from lemonsqueezy import LemonSqueezyError, sync_user_subscription
from projects import (
    convert_one_off_test_to_project,
    create_one_off_test,
    create_project,
    create_project_material,
    delete_project,
    get_one_off_test,
    get_project,
    list_project_materials,
    list_projects,
    list_recent_one_off_tests,
    normalize_test_mode,
    update_project,
)


PLAN_ORDER = {"Free": 0, "Starter": 1, "Pro": 2}


def _has_plan_access(user, minimum_plan):
    return PLAN_ORDER.get(user.get("selected_plan"), 0) >= PLAN_ORDER[minimum_plan]


def _json_error(message, status_code):
    return jsonify({"error": message}), status_code


def _serialize_datetime(value):
    return value.isoformat() if value else None


def _serialize_project(project):
    return {
        **project,
        "created_at": _serialize_datetime(project.get("created_at")),
        "updated_at": _serialize_datetime(project.get("updated_at")),
    }


def _serialize_material(material):
    return {
        **material,
        "created_at": _serialize_datetime(material.get("created_at")),
    }


def _serialize_test(test):
    return {
        **test,
        "created_at": _serialize_datetime(test.get("created_at")),
    }


def _require_user():
    user = get_current_user(request)
    if not user:
        return None, _json_error("Authentication required.", 401)
    return user, None


def _require_plan(user, minimum_plan, message):
    if not _has_plan_access(user, minimum_plan):
        return _json_error(message, 403)
    return None


def _payload():
    return request.get_json(silent=True) or {}


def _enforce_mode_access(user, mode):
    if mode == "live_signals" and not _has_plan_access(user, "Starter"):
        return _json_error("Live Signals requires the Starter plan.", 403)
    if mode in {"perception", "spread"} and not _has_plan_access(user, "Pro"):
        return _json_error("Perception and Spread tests require the Pro plan.", 403)
    return None


def register_api_routes(app):
    @app.get(f"{BASE_PATH}/api/health")
    def api_health():
        return jsonify({"status": "ok"}), 200

    @app.get(f"{BASE_PATH}/api/me")
    def api_me():
        user, error = _require_user()
        if error:
            return error

        try:
            synced_user = sync_user_subscription(user)
        except LemonSqueezyError:
            synced_user = user

        return jsonify(
            {
                "user": {
                    "id": synced_user["id"],
                    "name": synced_user["name"],
                    "email": synced_user["email"],
                    "selected_plan": synced_user["selected_plan"],
                    "credits_remaining": synced_user.get("credits_remaining", 0),
                    "credits_renews_at": _serialize_datetime(synced_user.get("credits_renews_at")),
                    "billing_enabled": synced_user.get("billing_enabled", False),
                    "subscription_status": synced_user.get("lemonsqueezy_subscription_status"),
                }
            }
        ), 200

    @app.get(f"{BASE_PATH}/api/projects")
    def api_projects_list():
        user, error = _require_user()
        if error:
            return error

        projects = [_serialize_project(project) for project in list_projects(user["id"])]
        return jsonify({"projects": projects}), 200

    @app.post(f"{BASE_PATH}/api/projects")
    def api_projects_create():
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Project management requires the Starter plan.")
        if plan_error:
            return plan_error

        data = _payload()
        try:
            project_id = create_project(
                user["id"],
                data.get("name", ""),
                data.get("description", ""),
                user["selected_plan"],
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return jsonify({"project": _serialize_project(get_project(user["id"], project_id))}), 201

    @app.get(f"{BASE_PATH}/api/projects/<int:project_id>")
    def api_projects_detail(project_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Projects require the Starter plan.")
        if plan_error:
            return plan_error

        project = get_project(user["id"], project_id)
        if not project:
            return _json_error("Project not found.", 404)

        materials = [_serialize_material(item) for item in list_project_materials(user["id"], project_id)]
        return jsonify({"project": _serialize_project(project), "materials": materials}), 200

    @app.patch(f"{BASE_PATH}/api/projects/<int:project_id>")
    def api_projects_update(project_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Project management requires the Starter plan.")
        if plan_error:
            return plan_error

        data = _payload()
        try:
            updated = update_project(
                user["id"],
                project_id,
                data.get("name", ""),
                data.get("description", ""),
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)

        if not updated:
            return _json_error("Project not found.", 404)

        return jsonify({"project": _serialize_project(get_project(user["id"], project_id))}), 200

    @app.delete(f"{BASE_PATH}/api/projects/<int:project_id>")
    def api_projects_delete(project_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Project management requires the Starter plan.")
        if plan_error:
            return plan_error

        deleted = delete_project(user["id"], project_id)
        if not deleted:
            return _json_error("Project not found.", 404)

        return jsonify({"deleted": True, "project_id": project_id}), 200

    @app.get(f"{BASE_PATH}/api/projects/<int:project_id>/materials")
    def api_project_materials_list(project_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Projects require the Starter plan.")
        if plan_error:
            return plan_error

        project = get_project(user["id"], project_id)
        if not project:
            return _json_error("Project not found.", 404)

        materials = [_serialize_material(item) for item in list_project_materials(user["id"], project_id)]
        return jsonify({"materials": materials}), 200

    @app.post(f"{BASE_PATH}/api/projects/<int:project_id>/materials")
    def api_project_materials_create(project_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Projects require the Starter plan.")
        if plan_error:
            return plan_error

        data = _payload()
        try:
            mode = normalize_test_mode(data.get("mode", "idea"))
            mode_error = _enforce_mode_access(user, mode)
            if mode_error:
                return mode_error
            material_id = create_project_material(
                user["id"],
                project_id,
                data.get("content", ""),
                user["selected_plan"],
                mode=mode,
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)

        if not material_id:
            return _json_error("Project not found.", 404)

        materials = list_project_materials(user["id"], project_id)
        material = next((item for item in materials if item["id"] == material_id), None)
        return jsonify({"material": _serialize_material(material)}), 201

    @app.get(f"{BASE_PATH}/api/tests")
    def api_tests_list():
        user, error = _require_user()
        if error:
            return error

        tests = [_serialize_test(test) for test in list_recent_one_off_tests(user["id"], limit=50)]
        return jsonify({"tests": tests}), 200

    @app.post(f"{BASE_PATH}/api/tests")
    def api_tests_create():
        user, error = _require_user()
        if error:
            return error

        data = _payload()
        try:
            mode = normalize_test_mode(data.get("mode", "idea"))
            mode_error = _enforce_mode_access(user, mode)
            if mode_error:
                return mode_error
            test_id = create_one_off_test(
                user["id"],
                data.get("prompt", ""),
                user["selected_plan"],
                mode,
            )
        except ValueError as exc:
            return _json_error(str(exc), 400)

        return jsonify({"test": _serialize_test(get_one_off_test(user["id"], test_id))}), 201

    @app.get(f"{BASE_PATH}/api/tests/<int:test_id>")
    def api_tests_detail(test_id):
        user, error = _require_user()
        if error:
            return error

        test = get_one_off_test(user["id"], test_id)
        if not test:
            return _json_error("Test not found.", 404)

        return jsonify({"test": _serialize_test(test)}), 200

    @app.post(f"{BASE_PATH}/api/tests/<int:test_id>/convert")
    def api_tests_convert(test_id):
        user, error = _require_user()
        if error:
            return error

        plan_error = _require_plan(user, "Starter", "Converting tests into projects requires the Starter plan.")
        if plan_error:
            return plan_error

        try:
            project_id = convert_one_off_test_to_project(user["id"], test_id, user["selected_plan"])
        except ValueError as exc:
            return _json_error(str(exc), 400)

        if not project_id:
            return _json_error("Test not found.", 404)

        return jsonify({"project": _serialize_project(get_project(user["id"], project_id))}), 201
