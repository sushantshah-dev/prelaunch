import json

from db import db_connection
from credits import (
    consume_user_credit_in_transaction,
    credit_error_message,
    project_creation_credit_cost,
    project_test_credit_cost,
    standalone_test_credit_cost,
)
from analysis_queue import enqueue_analysis_job


def _project_from_row(row):
    return {
        "id": row[0],
        "name": row[1],
        "description": row[2],
        "idea_score": float(row[3]),
        "perception_score": float(row[4]),
        "spread_score": float(row[5]),
        "live_signal_score": float(row[6]),
        "created_at": row[7],
        "updated_at": row[8],
    }


def _project_name_from_prompt(prompt):
    clean_prompt = " ".join(prompt.split())
    if not clean_prompt:
        return "Untitled Project"

    trimmed = clean_prompt[:48].strip(" .,!?:;")
    words = trimmed.split()
    if len(words) > 6:
        trimmed = " ".join(words[:6])
    return trimmed.title() or "Untitled Project"


def _validate_project_fields(name, description):
    cleaned_name = " ".join((name or "").split())
    cleaned_description = " ".join((description or "").split())

    if not cleaned_name:
        raise ValueError("Project name is required.")
    if len(cleaned_name) > 80:
        raise ValueError("Project name must be 80 characters or fewer.")
    if len(cleaned_description) > 280:
        raise ValueError("Project description must be 280 characters or fewer.")

    return cleaned_name, cleaned_description


def _validate_prompt_content(content, *, field_label="Prompt"):
    cleaned_content = " ".join((content or "").split())
    if not cleaned_content:
        raise ValueError(f"{field_label} is required.")
    if len(cleaned_content) > 4000:
        raise ValueError(f"{field_label} must be 4000 characters or fewer.")
    return cleaned_content


def _pending_field(value):
    return {"status": "pending", "value": value}


def build_analysis(prompt, plan, *, mode="idea", context_label="this concept", target_type, target_id):
    clean_prompt = " ".join((prompt or "").split())
    if not clean_prompt:
        raise ValueError("Prompt is required.")

    queue_job = enqueue_analysis_job(
        target_type=target_type,
        target_id=target_id,
        prompt=clean_prompt,
        plan=plan,
        mode=mode,
        context_label=context_label,
    )
    print(
        "[projects] build_analysis queued "
        f"job_id={queue_job['id']} target_type={target_type} target_id={target_id} "
        f"plan={plan} mode={mode}",
        flush=True,
    )

    return {
        "idea_score": 0,
        "idea_summary": "",
        "live_signal_score": None,
        "live_signal_summary": "",
        "perception_score": None,
        "perception_summary": "",
        "spread_score": None,
        "spread_summary": "",
        "prompt_preview": clean_prompt[:180],
        "persona_count_per_test": 0,
        "analysis_payload": {
            "status": "pending",
            "job": queue_job,
            "target_audience": _pending_field(""),
            "personas": _pending_field([]),
            "questionnaire_responses": _pending_field([]),
            "idea_review": _pending_field({}),
            "perception": _pending_field({"responses": [], "summary": ""}),
            "word_of_mouth": _pending_field({"order": [], "chain": [], "summary": ""}),
            "scores": _pending_field(
                {
                    "idea_score": None,
                    "perception_score": None,
                    "spread_score": None,
                }
            ),
            "summaries": _pending_field(
                {
                    "idea_summary": "",
                    "perception_summary": "",
                    "spread_summary": "",
                }
            ),
            "live_signals": _pending_field(None),
        },
    }


def _material_from_row(row):
    return {
        "id": row[0],
        "project_id": row[1],
        "content": row[2],
        "idea_score": float(row[3]),
        "live_signal_score": float(row[4]) if row[4] is not None else None,
        "perception_score": float(row[5]) if row[5] is not None else None,
        "spread_score": float(row[6]) if row[6] is not None else None,
        "idea_summary": row[7],
        "live_signal_summary": row[8],
        "perception_summary": row[9],
        "spread_summary": row[10],
        "analysis_payload": row[11] or {},
        "created_at": row[12],
    }


def _one_off_test_from_row(row):
    return {
        "id": row[0],
        "user_id": row[1],
        "mode": row[2],
        "prompt": row[3],
        "idea_score": float(row[4]),
        "live_signal_score": float(row[5]) if row[5] is not None else None,
        "perception_score": float(row[6]) if row[6] is not None else None,
        "spread_score": float(row[7]) if row[7] is not None else None,
        "idea_summary": row[8],
        "live_signal_summary": row[9],
        "perception_summary": row[10],
        "spread_summary": row[11],
        "analysis_payload": row[12] or {},
        "created_at": row[13],
    }


def normalize_test_mode(mode):
    normalized = (mode or "idea").strip().lower().replace(" ", "_")
    if normalized not in {"idea", "live_signals", "perception", "spread"}:
        raise ValueError("Choose a valid test mode.")
    return normalized


def list_projects(user_id, limit=None):
    query = """
        SELECT
            id,
            name,
            description,
            idea_score,
            perception_score,
            spread_score,
            live_signal_score,
            created_at,
            updated_at
        FROM projects
        WHERE user_id = %s
        ORDER BY created_at DESC
    """
    params = [user_id]

    if limit:
        query += " LIMIT %s"
        params.append(limit)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(query, params)
            rows = cur.fetchall()

    return [_project_from_row(row) for row in rows]


def get_project(user_id, project_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    name,
                    description,
                    idea_score,
                    perception_score,
                    spread_score,
                    live_signal_score,
                    created_at,
                    updated_at
                FROM projects
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (project_id, user_id),
            )
            row = cur.fetchone()

    if not row:
        return None

    return _project_from_row(row)


def get_project_stats(user_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    COUNT(*),
                    COALESCE(AVG(idea_score), 0),
                    COALESCE(AVG(perception_score), 0),
                    COALESCE(AVG(spread_score), 0),
                    COALESCE(AVG(live_signal_score), 0)
                FROM projects
                WHERE user_id = %s
                """,
                (user_id,),
            )
            row = cur.fetchone()

    return {
        "count": row[0],
        "idea_score": float(row[1]),
        "perception_score": float(row[2]),
        "spread_score": float(row[3]),
        "live_signal_score": float(row[4]),
    }


def create_project(user_id, name, description, plan, charge_credit=True):
    cleaned_name, cleaned_description = _validate_project_fields(name, description)
    with db_connection() as conn:
        with conn.cursor() as cur:
            if charge_credit:
                credit_state = consume_user_credit_in_transaction(
                    cur,
                    user_id,
                    plan,
                    project_creation_credit_cost(),
                )
                if credit_state is False:
                    raise ValueError(credit_error_message(plan))
            cur.execute(
                """
                INSERT INTO projects (
                    user_id,
                    name,
                    description,
                    idea_score,
                    perception_score,
                    spread_score,
                    live_signal_score
                )
                VALUES (%s, %s, %s, 0, 0, 0, 0)
                RETURNING id
                """,
                (
                    user_id,
                    cleaned_name,
                    cleaned_description,
                ),
            )
            return cur.fetchone()[0]


def update_project(user_id, project_id, name, description):
    cleaned_name, cleaned_description = _validate_project_fields(name, description)
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE projects
                SET
                    name = %s,
                    description = %s,
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (
                    cleaned_name,
                    cleaned_description,
                    project_id,
                    user_id,
                ),
            )
            return cur.rowcount > 0


def delete_project(user_id, project_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                "DELETE FROM projects WHERE id = %s AND user_id = %s",
                (project_id, user_id),
            )
            return cur.rowcount > 0


def list_project_materials(user_id, project_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    project_materials.id,
                    project_materials.project_id,
                    project_materials.content,
                    project_materials.idea_score,
                    project_materials.live_signal_score,
                    project_materials.perception_score,
                    project_materials.spread_score,
                    project_materials.idea_summary,
                    project_materials.live_signal_summary,
                    project_materials.perception_summary,
                    project_materials.spread_summary,
                    project_materials.analysis_payload,
                    project_materials.created_at
                FROM project_materials
                JOIN projects ON projects.id = project_materials.project_id
                WHERE project_materials.project_id = %s AND projects.user_id = %s
                ORDER BY project_materials.created_at DESC
                """,
                (project_id, user_id),
            )
            rows = cur.fetchall()

    return [_material_from_row(row) for row in rows]


def create_project_material(user_id, project_id, content, plan, mode="idea", charge_credit=True):
    cleaned_content = _validate_prompt_content(content, field_label="Material")
    print(
        "[projects] create_project_material "
        f"user_id={user_id} project_id={project_id} plan={plan} mode={mode} "
        f"charge_credit={charge_credit} content={cleaned_content[:180]!r}",
        flush=True,
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT name
                FROM projects
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (project_id, user_id),
            )
            row = cur.fetchone()
            if not row:
                return None

            if charge_credit:
                credit_state = consume_user_credit_in_transaction(
                    cur,
                    user_id,
                    plan,
                    project_test_credit_cost(),
                )
                if credit_state is False:
                    raise ValueError(credit_error_message(plan))

            cur.execute(
                """
                INSERT INTO project_materials (
                    project_id,
                    content,
                    idea_score,
                    live_signal_score,
                    perception_score,
                    spread_score,
                    idea_summary,
                    live_signal_summary,
                    perception_summary,
                    spread_summary,
                    analysis_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    project_id,
                    cleaned_content,
                    0,
                    None,
                    None,
                    None,
                    "pending",
                    "pending",
                    "pending",
                    "pending",
                    json.dumps({"status": "pending"}),
                ),
            )
            material_id = cur.fetchone()[0]
            analysis = build_analysis(
                cleaned_content,
                plan,
                mode=mode,
                context_label="this project",
                target_type="project_material",
                target_id=material_id,
            )

            cur.execute(
                """
                UPDATE project_materials
                SET
                    idea_score = %s,
                    live_signal_score = %s,
                    perception_score = %s,
                    spread_score = %s,
                    idea_summary = %s,
                    live_signal_summary = %s,
                    perception_summary = %s,
                    spread_summary = %s,
                    analysis_payload = %s
                WHERE id = %s
                """,
                (
                    analysis["idea_score"],
                    analysis["live_signal_score"],
                    analysis["perception_score"],
                    analysis["spread_score"],
                    analysis["idea_summary"],
                    analysis["live_signal_summary"],
                    analysis["perception_summary"],
                    analysis["spread_summary"],
                    json.dumps(analysis["analysis_payload"]),
                    material_id,
                ),
            )

            cur.execute(
                """
                UPDATE projects
                SET
                    idea_score = %s,
                    live_signal_score = COALESCE(%s, live_signal_score),
                    perception_score = COALESCE(%s, perception_score),
                    spread_score = COALESCE(%s, spread_score),
                    updated_at = NOW()
                WHERE id = %s AND user_id = %s
                """,
                (
                    analysis["idea_score"],
                    analysis["live_signal_score"],
                    analysis["perception_score"],
                    analysis["spread_score"],
                    project_id,
                    user_id,
                ),
            )

    return material_id


def create_one_off_test(user_id, prompt, plan, mode):
    normalized_mode = normalize_test_mode(mode)
    cleaned_prompt = _validate_prompt_content(prompt)
    print(
        "[projects] create_one_off_test "
        f"user_id={user_id} plan={plan} mode={normalized_mode} prompt={cleaned_prompt[:180]!r}",
        flush=True,
    )
    with db_connection() as conn:
        with conn.cursor() as cur:
            credit_state = consume_user_credit_in_transaction(
                cur,
                user_id,
                plan,
                standalone_test_credit_cost(),
            )
            if credit_state is False:
                raise ValueError(credit_error_message(plan))
            cur.execute(
                """
                INSERT INTO one_off_tests (
                    user_id,
                    mode,
                    prompt,
                    idea_score,
                    live_signal_score,
                    perception_score,
                    spread_score,
                    idea_summary,
                    live_signal_summary,
                    perception_summary,
                    spread_summary,
                    analysis_payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    normalized_mode,
                    cleaned_prompt,
                    0,
                    None,
                    None,
                    None,
                    "pending",
                    "pending",
                    "pending",
                    "pending",
                    json.dumps({"status": "pending"}),
                ),
            )
            test_id = cur.fetchone()[0]
            analysis = build_analysis(
                cleaned_prompt,
                plan,
                mode=normalized_mode,
                target_type="one_off_test",
                target_id=test_id,
            )
            cur.execute(
                """
                UPDATE one_off_tests
                SET
                    idea_score = %s,
                    live_signal_score = %s,
                    perception_score = %s,
                    spread_score = %s,
                    idea_summary = %s,
                    live_signal_summary = %s,
                    perception_summary = %s,
                    spread_summary = %s,
                    analysis_payload = %s
                WHERE id = %s
                """,
                (
                    analysis["idea_score"],
                    analysis["live_signal_score"],
                    analysis["perception_score"],
                    analysis["spread_score"],
                    analysis["idea_summary"],
                    analysis["live_signal_summary"],
                    analysis["perception_summary"],
                    analysis["spread_summary"],
                    json.dumps(analysis["analysis_payload"]),
                    test_id,
                ),
            )
            return test_id


def convert_one_off_test_to_project(user_id, test_id, plan):
    test = get_one_off_test(user_id, test_id)
    if not test:
        return None

    project_id = create_project(
        user_id,
        _project_name_from_prompt(test["prompt"]),
        "Created from a one-off test.",
        plan,
        charge_credit=False,
    )
    create_project_material(user_id, project_id, test["prompt"], plan, mode=test["mode"], charge_credit=False)
    return project_id


def get_one_off_test(user_id, test_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    mode,
                    prompt,
                    idea_score,
                    live_signal_score,
                    perception_score,
                    spread_score,
                    idea_summary,
                    live_signal_summary,
                    perception_summary,
                    spread_summary,
                    analysis_payload,
                    created_at
                FROM one_off_tests
                WHERE id = %s AND user_id = %s
                LIMIT 1
                """,
                (test_id, user_id),
            )
            row = cur.fetchone()

    if not row:
        return None

    return _one_off_test_from_row(row)


def list_recent_one_off_tests(user_id, limit=6):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                SELECT
                    id,
                    user_id,
                    mode,
                    prompt,
                    idea_score,
                    live_signal_score,
                    perception_score,
                    spread_score,
                    idea_summary,
                    live_signal_summary,
                    perception_summary,
                    spread_summary,
                    analysis_payload,
                    created_at
                FROM one_off_tests
                WHERE user_id = %s
                ORDER BY created_at DESC
                LIMIT %s
                """,
                (user_id, limit),
            )
            rows = cur.fetchall()

    return [_one_off_test_from_row(row) for row in rows]
