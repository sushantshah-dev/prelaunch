from flask import make_response, redirect, render_template, request

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


def register_context(app):
    @app.context_processor
    def inject_globals():
        return {
            "base_path": BASE_PATH,
            "current_user": get_current_user(request),
        }


def render_auth_page(mode, *, plan="Free", error="", values=None, subtext=None, status_code=200):
    values = values or {}

    if mode == "signup":
        heading = "Create an account and step into the app."
    else:
        heading = "Log back in to continue."

    subtext = ""

    return (
        render_template(
            "auth.html",
            title=f"Prelaunch {'Signup' if mode == 'signup' else 'Login'}",
            eyebrow="Authenticate",
            heading=heading,
            subtext=subtext,
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
        return redirect(f"{BASE_PATH}/dashboard" if user else f"{BASE_PATH}/signup")

    @app.get(f"{BASE_PATH}/signup")
    def signup_page():
        user = get_current_user(request)
        if user:
            return redirect(f"{BASE_PATH}/dashboard")
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
            response = make_response(redirect(f"{BASE_PATH}/dashboard"))
            set_session_cookie(response, token)
            return response
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
            return redirect(f"{BASE_PATH}/dashboard")
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
        response = make_response(redirect(f"{BASE_PATH}/dashboard"))
        set_session_cookie(response, token)
        return response

    @app.get(f"{BASE_PATH}/dashboard")
    def dashboard_page():
        user = get_current_user(request)
        if not user:
            return redirect(f"{BASE_PATH}/login")

        return render_template(
            "dashboard.html",
            title="Prelaunch Dashboard",
            eyebrow="",
            heading="",
            subtext="",
            user=user,
        )

    @app.post(f"{BASE_PATH}/logout")
    def logout_submit():
        delete_session(request.cookies.get(SESSION_COOKIE_NAME))
        response = make_response(redirect(f"{BASE_PATH}/login"))
        clear_session_cookie(response)
        return response
