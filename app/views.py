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


def billing_page_context(user, *, error="", status_message=""):
    return {
        "title": "Prelaunch Settings",
        "eyebrow": "Settings",
        "heading": "",
        "subtext": "",
        "user": user,
        "error": error,
        "status_message": status_message,
    }


def _extract_review_keywords(text, limit=3):
    keywords = []
    for word in text.replace("\n", " ").split():
        normalized = word.strip(".,!?;:()[]{}\"'").lower()
        if len(normalized) < 5 or normalized in keywords:
            continue
        keywords.append(normalized)
        if len(keywords) == limit:
            break
    return keywords


def _review_focus_phrase(text):
    keywords = _extract_review_keywords(text, limit=3)
    return ", ".join(keywords) if keywords else "the clearest user outcome"


def _infer_audience(text):
    lower = text.lower()
    audience_map = [
        ("founder", "Founders testing a clearer growth wedge"),
        ("developer", "Developers looking to remove repeated workflow friction"),
        ("marketer", "Marketers trying to tie the pitch to a measurable outcome"),
        ("designer", "Designers responding to polish, clarity, and trust"),
        ("student", "Students who engage only when the payoff is immediate"),
        ("creator", "Creators scanning for signal, novelty, and shareability"),
        ("team", "Small teams evaluating whether the promise feels concrete"),
    ]
    for needle, label in audience_map:
        if needle in lower:
            return label
    return "Early adopters who need the value to feel obvious on first read"


def _infer_channel(text):
    lower = text.lower()
    if "reddit" in lower:
        return "Reddit and community threads"
    if "search" in lower or "keyword" in lower:
        return "Search-driven intent"
    if "newsletter" in lower:
        return "Newsletter and creator channels"
    if "social" in lower or "viral" in lower or "share" in lower:
        return "Social and referral loops"
    if "community" in lower:
        return "Community-driven discovery"
    return "Search and founder communities"


def _infer_price_signal(text):
    lower = text.lower()
    if "$" in text or "price" in lower or "pricing" in lower:
        return "Pricing is already part of the pitch, which helps intent feel real."
    if "subscription" in lower or "monthly" in lower or "annual" in lower:
        return "A recurring-price frame is implied, but the value exchange needs to feel tighter."
    return "There is no price anchor yet, so intent may stay soft until the value is clearer."


def _infer_trust_signal(text):
    lower = text.lower()
    if any(phrase in lower for phrase in ("proof", "data", "results", "traction", "customers", "users", "pilot")):
        return "Concrete proof cues are present, which should raise trust for skeptical buyers."
    return "Trust still depends on the framing alone, so examples or proof would meaningfully improve response."


def _spread_chain(text):
    clean_text = " ".join(text.split())
    if not clean_text:
        clean_text = "An idea with an unclear payoff"
    words = clean_text.split()
    original = " ".join(words[:8]).strip(" ,.;") or clean_text[:48]
    promise = _review_focus_phrase(clean_text)
    return [
        ("Original", original),
        ("User A", f"It helps with {promise}."),
        ("User B", "It sounds useful, but the exact outcome is still fuzzy." if len(words) > 16 else "I get the outcome quickly."),
        ("User C", "The message starts to flatten into a generic category label." if len(words) > 20 else "The message survives retelling with minor drift."),
    ]


def _build_review_sections(review, latest_material):
    content = latest_material["content"]
    focus = _review_focus_phrase(content)
    audience = _infer_audience(content)
    channel = _infer_channel(content)
    price_signal = _infer_price_signal(content)
    trust_signal = _infer_trust_signal(content)

    if review["key"] == "idea":
        return {
            "layout": "idea",
            "rows": [
                ("Signal summary", review["summary"]),
                ("What to do next", review["detail"]),
                ("Focus area", f"Clarify the promise around {focus}."),
            ],
            "simulation_rows": [
                ("Audience", audience),
                ("Perception cue", f"The idea lands best when the payoff around {focus} is visible immediately."),
                ("Trust signal", trust_signal),
                ("Risk signal", "Generic AI framing will reduce urgency unless the message feels concrete, specific, and safe."),
            ],
            "note": "Simulation engine",
        }

    if review["key"] == "live_signals":
        return {
            "layout": "sources",
            "items": [
                ("Search result", f"People searching for {focus} are looking for a concrete before-and-after outcome, not a broad category pitch."),
                ("Community thread", f"{channel} is where this concept is most likely to surface early signal if the wording stays explicit."),
                ("Buyer intent", price_signal),
                ("Next query", f"Test demand language that pairs {focus} with a visible user payoff and a specific use case."),
            ],
            "footer": "Cross-source synthesis ready",
        }

    if review["key"] == "perception":
        return {
            "layout": "perception",
            "responses": [
                ("First read", f"\"This feels strongest for {focus}.\""),
                ("Skeptical response", "\"I need to know exactly what happens after I try it.\""),
                ("Interested response", "\"If the outcome is immediate, I would probably click.\""),
                ("Likely reaction", "-> Interest rises when the message sounds concrete, provable, and specific."),
            ],
        }

    spread_items = _spread_chain(content)
    return {
        "layout": "spread",
        "items": [
            spread_items[0],
            spread_items[1],
            spread_items[2],
            spread_items[3],
            ("Outcome", "Strong spread potential" if review["score"] and review["score"] >= 70 else "Low spread, weak clarity"),
            ("Suggested fix", "Sharpen the hook, add a clearer outcome, and make the differentiator easier to repeat."),
        ],
    }


def project_review_options(project, latest_material):
    if not latest_material:
        return []

    reviews = [
        {
            "key": "idea",
            "label": "Idea",
            "score": latest_material["idea_score"],
            "summary": latest_material["idea_summary"],
            "detail": "Use this read to tighten the core promise, audience, and outcome before investing more effort.",
        },
        {
            "key": "live_signals",
            "label": "Live Signals",
            "score": latest_material["live_signal_score"],
            "summary": latest_material["live_signal_summary"] or "Upgrade to Starter to unlock this review.",
            "detail": "Use this read to pressure-test demand language, search behavior, and channel fit.",
        },
        {
            "key": "perception",
            "label": "Perception",
            "score": latest_material["perception_score"],
            "summary": latest_material["perception_summary"] or "Upgrade to Pro to unlock this review.",
            "detail": "Use this read to refine how the idea feels to the audience, especially trust and positioning.",
        },
        {
            "key": "spread",
            "label": "Spread",
            "score": latest_material["spread_score"],
            "summary": latest_material["spread_summary"] or "Upgrade to Pro to unlock this review.",
            "detail": "Use this read to improve retellability and make the concept easier to carry from person to person.",
        },
    ]

    for review in reviews:
        review["href"] = f"{BASE_PATH}/projects/{project['id']}?review={review['key']}#project-review"
        review["sections"] = _build_review_sections(review, latest_material)

    return reviews


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
    return {
        "title": f"Prelaunch Test {test['id']}",
        "eyebrow": "Test Result",
        "heading": "Independent test result.",
        "subtext": "This result lives on its own until you turn it into a project.",
        "user": user,
        "test": test,
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
            material_id = create_project_material(user["id"], project_id, prompt, user["selected_plan"])
            if not material_id:
                raise ValueError("Project not found.")
        except ValueError as error:
            return redirect(f"{BASE_PATH}/projects/{project_id}?{urlencode({'error': str(error)})}")

        return redirect(
            f"{BASE_PATH}/projects/{project_id}?{urlencode({'status': 'Material added to project history.'})}#project-material-history"
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
