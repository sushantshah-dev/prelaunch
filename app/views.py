from flask import make_response, redirect, render_template, request
from urllib.parse import urlencode

from auth import (
    authenticate_user,
    clear_session_cookie,
    create_session,
    delete_session,
    get_current_user,
    is_unique_violation,
    normalize_plan,
    set_session_cookie,
    signup_user,
)
from config import BASE_PATH, SESSION_COOKIE_NAME
from config import FREE_CREDITS_ONCE, PRO_CREDITS_MONTHLY, STARTER_CREDITS_MONTHLY
from lemonsqueezy import (
    LemonSqueezyError,
    create_subscription_change_request,
    create_checkout_url,
    is_enabled as billing_enabled,
    is_paid_plan,
    sync_user_subscription,
)
from projects import (
    convert_one_off_test_to_project,
    create_project,
    create_project_material,
    create_one_off_test,
    delete_project as remove_project,
    get_one_off_test,
    get_project,
    get_project_stats,
    list_project_materials,
    list_projects,
    list_recent_one_off_tests,
    normalize_test_mode,
    update_project,
)


PLAN_ORDER = {"Free": 0, "Starter": 1, "Pro": 2}


def has_plan_access(user, minimum_plan):
    return PLAN_ORDER.get(user.get("selected_plan"), 0) >= PLAN_ORDER[minimum_plan]


def project_values_from_request(form):
    name = form.get("name", "").strip()
    description = form.get("description", "").strip()

    if not name:
        raise ValueError("Project name is required.")

    return {
        "name": name,
        "description": description,
    }


def prompt_value_from_request(form, field_name="prompt"):
    prompt = form.get(field_name, "").strip()
    if not prompt:
        raise ValueError("Enter some text before continuing.")
    return prompt


def test_mode_value_from_request(form):
    return normalize_test_mode(form.get("mode"))


def review_key_from_request(form_or_args):
    review = (form_or_args.get("review") or "").strip().lower()
    return review if review in {"idea", "live_signals", "perception", "spread"} else ""


def billing_page_context(user, *, error="", status_message=""):
    return {
        "title": "Prelaunch Settings",
        "eyebrow": "Settings",
        "heading": "",
        "subtext": "",
        "user": user,
        "free_credits_once": FREE_CREDITS_ONCE,
        "starter_credits_monthly": STARTER_CREDITS_MONTHLY,
        "pro_credits_monthly": PRO_CREDITS_MONTHLY,
        "error": error,
        "status_message": status_message,
    }


def _analysis_payload(item):
    payload = item.get("analysis_payload") or {}
    return payload if isinstance(payload, dict) else {}


def _payload_field_value(value):
    if isinstance(value, dict) and "value" in value and "status" in value:
        return value.get("value")
    return value


def _payload_is_pending(payload):
    return payload.get("status") in {"pending", "processing"}


def _truncate_text(value, limit=220):
    text = " ".join(str(value or "").split())
    if len(text) <= limit:
        return text
    return f"{text[: limit - 1].rstrip()}..."


def _pipeline_score_text(score, summary):
    if score is None:
        return f"Loading... {summary or ''}".strip()
    return f"{round(float(score))}: {summary or ''}"


def pipeline_sections_for_item(item):
    payload = _analysis_payload(item)
    if not payload:
        return []

    sections = []

    target_audience = _payload_field_value(payload.get("target_audience"))
    if target_audience:
        sections.append({"title": "1. Target audience", "items": [("Audience", target_audience)]})

    personas = _payload_field_value(payload.get("personas")) or []
    if personas:
        sections.append(
            {
                "title": "2. Personas",
                "items": [
                    (
                        persona.get("display_name") or persona.get("id") or "Persona",
                        _truncate_text(
                            (
                                f"{persona.get('age_band', '')} • "
                                f"{persona.get('occupation', '')} • "
                                f"{persona.get('income_band', '')}. "
                                f"Current workaround: {persona.get('current_workaround', '')}."
                            )
                        ),
                    )
                    for persona in personas[:4]
                ],
            }
        )

    questionnaire_responses = _payload_field_value(payload.get("questionnaire_responses")) or []
    if questionnaire_responses:
        sections.append(
            {
                "title": "3. Persona questionnaire",
                "items": [
                    (
                        response.get("persona_name") or response.get("persona_id") or "Persona",
                        _truncate_text(
                            next(
                                (
                                    answer.get("answer")
                                    for answer in (response.get("answers") or [])
                                    if answer.get("question") == "How would you describe this to someone else in one sentence?"
                                ),
                                "",
                            )
                            or next(
                                (
                                    answer.get("answer")
                                    for answer in (response.get("answers") or [])
                                    if answer.get("answer")
                                ),
                                "",
                            ),
                            limit=200,
                        ),
                    )
                    for response in questionnaire_responses[:4]
                ],
            }
        )

    idea_review = _payload_field_value(payload.get("idea_review")) or {}
    if idea_review:
        sections.append(
            {
                "title": "4. Idea evaluation",
                "items": [
                    ("Signal summary", idea_review.get("signal_summary") or ""),
                    ("What to do next", idea_review.get("what_to_do_next") or ""),
                    ("Focus area", idea_review.get("focus_area") or ""),
                ],
            }
        )

    perception = _payload_field_value(payload.get("perception")) or {}
    if perception:
        response_items = [
            (
                response.get("persona_name") or "Persona",
                _truncate_text(
                    (
                        f"Use/buy: {response.get('would_use_or_buy', '')}. "
                        f"Expected price: {response.get('expected_price', '')}. "
                        f"Worth it: {response.get('worth_it_assessment', '')}."
                    ),
                    limit=200,
                ),
            )
            for response in (perception.get("responses") or [])[:4]
        ]
        if perception.get("summary"):
            response_items.append(("Summary", perception["summary"]))
        sections.append({"title": "5. Perception", "items": response_items})

    word_of_mouth = _payload_field_value(payload.get("word_of_mouth")) or {}
    if word_of_mouth:
        chain_items = [
            (
                entry.get("persona_id") or f"Hop {index + 1}",
                _truncate_text(entry.get("retold_gist") or entry.get("received_message") or ""),
            )
            for index, entry in enumerate((word_of_mouth.get("chain") or [])[:4])
        ]
        if word_of_mouth.get("summary"):
            chain_items.append(("Summary", word_of_mouth["summary"]))
        sections.append({"title": "6. Word of mouth", "items": chain_items})

    summaries = _payload_field_value(payload.get("summaries")) or {}
    scores = _payload_field_value(payload.get("scores")) or {}
    if summaries or scores:
        sections.append(
            {
                "title": "7. Scores and summaries",
                "items": [
                    (
                        "Idea",
                        _pipeline_score_text(scores.get("idea_score"), summaries.get("idea_summary")),
                    ),
                    (
                        "Perception",
                        _pipeline_score_text(scores.get("perception_score"), summaries.get("perception_summary")),
                    ),
                    (
                        "Spread",
                        _pipeline_score_text(scores.get("spread_score"), summaries.get("spread_summary")),
                    ),
                ],
            }
        )

    return [section for section in sections if section["items"]]


def _build_review_sections(review, latest_material):
    payload = _analysis_payload(latest_material)

    if review["key"] == "idea":
        idea_review = _payload_field_value(payload.get("idea_review")) or {}
        return {
            "layout": "idea",
            "rows": [
                ("Signal summary", idea_review.get("signal_summary") or ""),
                ("What to do next", idea_review.get("what_to_do_next") or ""),
                ("Focus area", idea_review.get("focus_area") or ""),
            ],
            "simulation_rows": [
                ("Audience", idea_review.get("audience") or ""),
                ("Perception cue", idea_review.get("perception_cue") or ""),
                ("Trust signal", idea_review.get("trust_signal") or ""),
                ("Risk signal", idea_review.get("risk_signal") or ""),
            ],
            "note": "Simulation engine",
        }

    if review["key"] == "live_signals":
        live_signals = _payload_field_value(payload.get("live_signals")) or {}
        results = live_signals.get("results") or []
        return {
            "layout": "sources",
            "items": [
                (
                    f"{result.get('source', 'Source').title()}: {result.get('title', 'Signal')}",
                    result.get("snippet") or result.get("signal_strength") or "",
                )
                for result in results[:4]
            ],
            "footer": live_signals.get("synthesis") or "",
        }

    if review["key"] == "perception":
        perception = _payload_field_value(payload.get("perception")) or {}
        responses = perception.get("responses") or []
        return {
            "layout": "perception",
            "responses": [
                (
                    response.get("persona_name") or "Persona",
                    (
                        f"Use/buy: {response.get('would_use_or_buy', '')}. "
                        f"Price: {response.get('expected_price', '')}. "
                        f"Worth it: {response.get('worth_it_assessment', '')}."
                    ),
                )
                for response in responses[:4]
            ],
        }

    word_of_mouth = _payload_field_value(payload.get("word_of_mouth")) or {}
    chain = word_of_mouth.get("chain") or []
    return {
        "layout": "spread",
        "items": [
            (
                item.get("persona_id") or f"Hop {index + 1}",
                item.get("retold_gist") or item.get("received_message") or "",
            )
            for index, item in enumerate(chain[:4])
        ]
        + ([("Outcome", word_of_mouth.get("summary"))] if word_of_mouth.get("summary") else []),
    }


def _score_or_fallback(value, fallback):
    return float(value) if value is not None else float(fallback)


def review_options_for_analysis(analysis_item, *, review_base_href=""):
    if not analysis_item:
        return []

    payload = _analysis_payload(analysis_item)
    is_pending = _payload_is_pending(payload)
    reviews = [
        {
            "key": "idea",
            "label": "Idea",
            "score": None if is_pending else analysis_item["idea_score"],
            "summary": analysis_item["idea_summary"],
            "pending": is_pending,
        },
        {
            "key": "live_signals",
            "label": "Live Signals",
            "score": None if is_pending else analysis_item["live_signal_score"],
            "summary": analysis_item["live_signal_summary"] or "",
            "pending": is_pending,
        },
        {
            "key": "perception",
            "label": "Perception",
            "score": None if is_pending else analysis_item["perception_score"],
            "summary": analysis_item["perception_summary"] or "",
            "pending": is_pending,
        },
        {
            "key": "spread",
            "label": "Spread",
            "score": None if is_pending else analysis_item["spread_score"],
            "summary": analysis_item["spread_summary"] or "",
            "pending": is_pending,
        },
    ]

    for review in reviews:
        if review_base_href:
            review["href"] = f"{review_base_href}?review={review['key']}#project-review"
        review["sections"] = _build_review_sections(review, analysis_item)

    return reviews


def build_signal_snapshot(analysis_item):
    if not analysis_item:
        return None

    payload = _analysis_payload(analysis_item)
    if _payload_is_pending(payload):
        return {
            "interest": 0,
            "summary": "Analysis pending.",
            "bars": [
                {"label": "Willingness to pay", "value": 0},
                {"label": "Initial clarity", "value": 0},
                {"label": "Skepticism risk", "value": 0},
            ],
            "note": "Queued for processing.",
        }

    idea_score = _score_or_fallback(analysis_item.get("idea_score"), 0)
    live_signal_score = _score_or_fallback(analysis_item.get("live_signal_score"), idea_score)
    perception_score = _score_or_fallback(analysis_item.get("perception_score"), idea_score)
    spread_score = _score_or_fallback(analysis_item.get("spread_score"), idea_score)

    interest = round((idea_score + perception_score + spread_score) / 3)
    willingness = round((perception_score + live_signal_score) / 2)
    clarity = round((idea_score + spread_score) / 2)
    skepticism = round(max(0, min(100, 100 - perception_score)))

    summary = analysis_item.get("idea_summary") or ""

    return {
        "interest": interest,
        "summary": summary,
        "bars": [
            {"label": "Willingness to pay", "value": willingness},
            {"label": "Initial clarity", "value": clarity},
            {"label": "Skepticism risk", "value": skepticism},
        ],
        "note": "",
    }


def project_review_options(project, latest_material):
    return review_options_for_analysis(
        latest_material,
        review_base_href=f"{BASE_PATH}/projects/{project['id']}",
    )


def dashboard_page_context(user):
    stats = get_project_stats(user["id"])
    projects = list_projects(user["id"], limit=5)
    return {
        "title": "Prelaunch Dashboard",
        "eyebrow": "Dashboard",
        "heading": "Average perception across your projects.",
        "subtext": "Track the combined signal for the ideas you are actively shaping and jump into project management when something needs attention.",
        "user": user,
        "stats": stats,
        "projects": projects,
    }


def projects_page_context(user, *, error="", status_message=""):
    projects = list_projects(user["id"])
    recent_tests = list_recent_one_off_tests(user["id"])

    return {
        "title": "Prelaunch Projects",
        "eyebrow": "Projects",
        "heading": "Saved projects for the ideas worth keeping.",
        "subtext": "Use the test workspace for independent reads, then convert strong tests into projects with their own material history.",
        "user": user,
        "projects": projects,
        "recent_tests": recent_tests,
        "error": error,
        "status_message": status_message,
        "can_manage_projects": has_plan_access(user, "Starter"),
        "content_panel": False,
    }


def test_new_page_context(user, *, error="", status_message=""):
    return {
        "title": "Prelaunch New Test",
        "eyebrow": "Test Workspace",
        "heading": "",
        "subtext": "",
        "user": user,
        "error": error,
        "status_message": status_message,
        "selected_mode": request.args.get("mode", "idea"),
        "has_live_signals": has_plan_access(user, "Starter"),
        "has_pro_features": has_plan_access(user, "Pro"),
        "content_panel": False,
    }


def test_result_page_context(user, test, *, error="", status_message=""):
    reviews = review_options_for_analysis(test, review_base_href=f"{BASE_PATH}/test/{test['id']}")
    initial_review_key = request.args.get("review", "idea")
    if reviews and not any(review["key"] == initial_review_key for review in reviews):
        initial_review_key = reviews[0]["key"]
    return {
        "title": f"Prelaunch Test {test['id']}",
        "eyebrow": "Test Result",
        "heading": "Independent test result.",
        "subtext": "This result lives on its own until you turn it into a project.",
        "user": user,
        "test": test,
        "reviews": reviews,
        "initial_review_key": initial_review_key,
        "pipeline_sections": pipeline_sections_for_item(test),
        "signal_snapshot": build_signal_snapshot(test),
        "error": error,
        "status_message": status_message,
        "can_manage_projects": has_plan_access(user, "Starter"),
        "has_live_signals": has_plan_access(user, "Starter"),
        "has_pro_features": has_plan_access(user, "Pro"),
        "content_panel": False,
    }


def project_detail_page_context(user, project, *, error="", status_message=""):
    materials = list_project_materials(user["id"], project["id"])
    latest_material = materials[0] if materials else None
    reviews = project_review_options(project, latest_material)
    initial_review_key = request.args.get("review", "idea")
    if reviews and not any(review["key"] == initial_review_key for review in reviews):
        initial_review_key = reviews[0]["key"]
    return {
        "title": f"Prelaunch {project['name']}",
        "eyebrow": "Project Workspace",
        "heading": project["name"],
        "subtext": project["description"] or "Add material over time to build a running history for this project.",
        "user": user,
        "project": project,
        "materials": materials,
        "latest_material": latest_material,
        "pipeline_sections": pipeline_sections_for_item(latest_material) if latest_material else [],
        "signal_snapshot": build_signal_snapshot(latest_material),
        "reviews": reviews,
        "initial_review_key": initial_review_key,
        "error": error,
        "status_message": status_message,
        "can_manage_projects": has_plan_access(user, "Starter"),
        "has_live_signals": has_plan_access(user, "Starter"),
        "has_pro_features": has_plan_access(user, "Pro"),
        "content_panel": False,
    }


def register_context(app):
    @app.context_processor
    def inject_globals():
        current_user = get_current_user(request)
        sidebar_projects = list_projects(current_user["id"], limit=8) if current_user else []
        sidebar_recent_tests = list_recent_one_off_tests(current_user["id"], limit=24) if current_user else []
        return {
            "base_path": BASE_PATH,
            "current_user": current_user,
            "sidebar_projects": sidebar_projects,
            "sidebar_recent_tests": sidebar_recent_tests,
        }


def render_auth_page(mode, *, plan="Free", error="", values=None, subtext=None, status_code=200):
    values = values or {}

    heading = "Join Prelaunch" if mode == "signup" else "Welcome back"

    subtext = ""

    return (
        render_template(
            "auth.html",
            title=f"Prelaunch {'Signup' if mode == 'signup' else 'Login'}",
            eyebrow="Authenticate",
            heading=heading,
            subtext=subtext,
            body_class="auth-page",
            wrap_class="wrap-auth",
            mode=mode,
            plan=plan,
            error=error,
            values=values,
        ),
        status_code,
    )


def register_routes(app):
    @app.get(BASE_PATH)
    @app.get(f"{BASE_PATH}/")
    def app_root():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/signup")

        return render_template("dashboard_home.html", **dashboard_page_context(user))

    @app.get(f"{BASE_PATH}/dashboard")
    def legacy_dashboard_page():
        return redirect(BASE_PATH)

    @app.get(f"{BASE_PATH}/signup")
    def signup_page():
        user = get_current_user(request)
        if user:
            return redirect(BASE_PATH)
        plan = normalize_plan(request.args.get("plan"))
        return render_auth_page("signup", plan=plan)

    @app.post(f"{BASE_PATH}/signup")
    def signup_submit():
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        plan = normalize_plan(request.form.get("plan"))
        name = email.split("@", 1)[0] if email else ""

        if not email or len(password) < 8:
            return render_auth_page(
                "signup",
                plan=plan,
                error="Enter a valid email and a password with at least 8 characters.",
                values={"email": email},
                subtext="Complete the required fields to continue.",
                status_code=400,
            )

        try:
            user_id = signup_user(name, email, password, plan)
            token = create_session(user_id)
            destination = BASE_PATH

            if plan != "Free" and is_paid_plan(plan) and billing_enabled():
                checkout_url = create_checkout_url(
                    {"id": user_id, "name": name, "email": email},
                    plan,
                    request.url_root,
                )
                destination = checkout_url

            response = make_response(redirect(destination))
            set_session_cookie(response, token)
            return response
        except LemonSqueezyError as error:
            return render_auth_page(
                "signup",
                plan=plan,
                error=str(error),
                values={"email": email},
                status_code=400,
            )
        except Exception as error:
            if is_unique_violation(error):
                return render_auth_page(
                    "signup",
                    plan=plan,
                    error="An account with that email already exists.",
                    values={"email": email},
                    status_code=400,
                )
            raise

    @app.get(f"{BASE_PATH}/login")
    def login_page():
        user = get_current_user(request)
        if user:
            return redirect(BASE_PATH)
        return render_auth_page("login")

    @app.post(f"{BASE_PATH}/login")
    def login_submit():
        email = request.form.get("email", "").strip().lower()
        password = request.form.get("password", "")
        user = authenticate_user(email, password)

        if not user:
            return render_auth_page(
                "login",
                error="Incorrect email or password.",
                values={"email": email},
                status_code=400,
            )

        token = create_session(user["id"])
        response = make_response(redirect(BASE_PATH))
        set_session_cookie(response, token)
        return response

    @app.get(f"{BASE_PATH}/settings")
    def settings_page():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        dashboard_error = ""
        try:
            user = sync_user_subscription(user)
        except LemonSqueezyError as error:
            user = {**user, "billing_enabled": False}
            dashboard_error = str(error)

        status_message = (
            "Subscription change completed and older subscriptions were cancelled."
            if (user.get("billing_change_request") or {}).get("status") == "completed"
            else "Waiting for your new subscription to appear before cleaning up the old one."
            if (user.get("billing_change_request") or {}).get("status") == "pending"
            else "Billing details refreshed."
            if request.args.get("billing") == "success"
            else ""
        )

        return render_template(
            "billing.html",
            **billing_page_context(
                user,
                error=dashboard_error or request.args.get("error", ""),
                status_message=status_message,
            ),
        )

    @app.get(f"{BASE_PATH}/billing")
    def billing_page_redirect():
        return redirect(f"{BASE_PATH}/settings")

    @app.get(f"{BASE_PATH}/projects")
    def projects_page():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        return render_template(
            "projects.html",
            **projects_page_context(
                user,
                error=request.args.get("error", ""),
                status_message=request.args.get("status", ""),
            ),
        )

    @app.get(f"{BASE_PATH}/test/new")
    def test_new_page():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        return render_template(
            "test_new.html",
            **test_new_page_context(
                user,
                error=request.args.get("error", ""),
                status_message=request.args.get("status", ""),
            ),
        )

    @app.post(f"{BASE_PATH}/projects")
    def projects_create():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Project management requires the Starter plan.'})}"
            )

        try:
            values = project_values_from_request(request.form)
            project_id = create_project(user["id"], plan=user["selected_plan"], **values)
        except ValueError as error:
            return redirect(f"{BASE_PATH}/projects?{urlencode({'error': str(error)})}")

        return redirect(f"{BASE_PATH}/projects/{project_id}?{urlencode({'status': 'Project created.'})}")

    @app.get(f"{BASE_PATH}/projects/<int:project_id>")
    def project_detail_page(project_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Projects require the Starter plan.'})}"
            )

        project = get_project(user["id"], project_id)
        if not project:
            return redirect(f"{BASE_PATH}/projects?{urlencode({'error': 'Project not found.'})}")

        return render_template(
            "project.html",
            **project_detail_page_context(
                user,
                project,
                error=request.args.get("error", ""),
                status_message=request.args.get("status", ""),
            ),
        )

    @app.post(f"{BASE_PATH}/projects/<int:project_id>/update")
    def project_update(project_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Project management requires the Starter plan.'})}"
            )

        try:
            values = project_values_from_request(request.form)
            updated = update_project(user["id"], project_id, **values)
            if not updated:
                raise ValueError("Project not found.")
        except ValueError as error:
            return redirect(f"{BASE_PATH}/projects/{project_id}?{urlencode({'error': str(error)})}")

        return redirect(f"{BASE_PATH}/projects/{project_id}?{urlencode({'status': 'Project updated.'})}")

    @app.post(f"{BASE_PATH}/projects/<int:project_id>/materials")
    def project_material_create(project_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Projects require the Starter plan.'})}"
            )

        try:
            prompt = prompt_value_from_request(request.form, "content")
            review = review_key_from_request(request.form)
            material_id = create_project_material(user["id"], project_id, prompt, user["selected_plan"])
            if not material_id:
                raise ValueError("Project not found.")
        except ValueError as error:
            return redirect(f"{BASE_PATH}/projects/{project_id}?{urlencode({'error': str(error)})}")

        params = {"status": "Material added to project history."}
        if review:
            params["review"] = review
        return redirect(
            f"{BASE_PATH}/projects/{project_id}?{urlencode(params)}#project-material-history"
        )

    @app.post(f"{BASE_PATH}/projects/<int:project_id>/delete")
    def project_delete(project_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Project management requires the Starter plan.'})}"
            )

        remove_project(user["id"], project_id)
        return redirect(f"{BASE_PATH}/projects?{urlencode({'status': 'Project deleted.'})}")

    @app.post(f"{BASE_PATH}/tests")
    def one_off_test_create():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        try:
            prompt = prompt_value_from_request(request.form)
            mode = test_mode_value_from_request(request.form)
            if mode == "live_signals" and not has_plan_access(user, "Starter"):
                return redirect(
                    f"{BASE_PATH}/settings?{urlencode({'error': 'Live Signals requires the Starter plan.'})}"
                )
            if mode in {"perception", "spread"} and not has_plan_access(user, "Pro"):
                return redirect(
                    f"{BASE_PATH}/settings?{urlencode({'error': 'Perception and Spread tests require the Pro plan.'})}"
                )
            test_id = create_one_off_test(user["id"], prompt, user["selected_plan"], mode)
        except ValueError as error:
            return redirect(
                f"{BASE_PATH}/test/new?{urlencode({'error': str(error), 'mode': request.form.get('mode', 'idea')})}"
            )

        return redirect(f"{BASE_PATH}/test/{test_id}?{urlencode({'status': 'Independent test created.'})}")

    @app.get(f"{BASE_PATH}/test/<int:test_id>")
    def one_off_test_result_page(test_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        test = get_one_off_test(user["id"], test_id)
        if not test:
            return redirect(f"{BASE_PATH}/projects?{urlencode({'error': 'Test not found.'})}")

        return render_template(
            "test_result.html",
            **test_result_page_context(
                user,
                test,
                error=request.args.get("error", ""),
                status_message=request.args.get("status", ""),
            ),
        )

    @app.post(f"{BASE_PATH}/tests/<int:test_id>/convert")
    def one_off_test_convert(test_id):
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")
        if not has_plan_access(user, "Starter"):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Converting tests into projects requires the Starter plan.'})}"
            )

        try:
            project_id = convert_one_off_test_to_project(user["id"], test_id, user["selected_plan"])
        except ValueError as error:
            return redirect(f"{BASE_PATH}/test/{test_id}?{urlencode({'error': str(error)})}")
        if not project_id:
            return redirect(f"{BASE_PATH}/projects?{urlencode({'error': 'Test not found.'})}")

        return redirect(
            f"{BASE_PATH}/projects/{project_id}?{urlencode({'status': 'Test converted into a project.'})}"
        )

    @app.post(f"{BASE_PATH}/settings/checkout")
    @app.post(f"{BASE_PATH}/billing/checkout")
    def billing_checkout():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        plan = normalize_plan(request.form.get("plan"))
        if plan == "Free" or not is_paid_plan(plan):
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'Choose a paid plan to start checkout.'})}"
            )

        try:
            user = sync_user_subscription(user)
            create_subscription_change_request(user, plan)
            checkout_url = create_checkout_url(user, plan, request.url_root)
        except LemonSqueezyError as error:
            return redirect(f"{BASE_PATH}/settings?{urlencode({'error': str(error)})}")

        return redirect(checkout_url)

    @app.post(f"{BASE_PATH}/settings/portal")
    @app.post(f"{BASE_PATH}/billing/portal")
    def billing_portal():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        try:
            user = sync_user_subscription(user)
        except LemonSqueezyError as error:
            return redirect(f"{BASE_PATH}/settings?{urlencode({'error': str(error)})}")

        portal_url = user.get("billing_customer_portal_url")
        if not portal_url:
            return redirect(
                f"{BASE_PATH}/settings?{urlencode({'error': 'No customer portal is available for this account yet.'})}"
            )

        return redirect(portal_url)

    @app.post(f"{BASE_PATH}/logout")
    def logout_submit():
        delete_session(request.cookies.get(SESSION_COOKIE_NAME))
        response = make_response(redirect(f"{BASE_PATH}/login"))
        clear_session_cookie(response)
        return response
