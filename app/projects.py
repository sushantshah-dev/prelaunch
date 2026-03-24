from db import db_connection


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


def _score_for(prompt, stage, minimum, maximum):
    span = maximum - minimum
    seed = sum(ord(character) for character in f"{prompt}:{stage}")
    return round(minimum + (seed % (span + 1)), 1)


def _clamp(value, minimum=0, maximum=100):
    return round(max(minimum, min(maximum, value)), 1)


def _extract_keywords(prompt):
    seen = []
    for word in prompt.replace("\n", " ").split():
        normalized = word.strip(".,!?;:()[]{}\"'").lower()
        if len(normalized) < 5 or normalized in seen:
            continue
        seen.append(normalized)
        if len(seen) == 3:
            break
    return seen


def _project_name_from_prompt(prompt):
    clean_prompt = " ".join(prompt.split())
    if not clean_prompt:
        return "Untitled Project"

    trimmed = clean_prompt[:48].strip(" .,!?:;")
    words = trimmed.split()
    if len(words) > 6:
        trimmed = " ".join(words[:6])
    return trimmed.title() or "Untitled Project"


def _contains_any(text, phrases):
    return any(phrase in text for phrase in phrases)


def _score_breakdown(prompt):
    clean_prompt = " ".join(prompt.split())
    lower = clean_prompt.lower()
    words = clean_prompt.split()
    word_count = len(words)
    sentence_count = max(1, sum(clean_prompt.count(mark) for mark in ".!?"))

    has_audience = _contains_any(
        lower,
        ("for ", "founder", "team", "creator", "marketer", "designer", "parent", "developer", "student", "seller"),
    )
    has_outcome = _contains_any(
        lower,
        ("help", "reduce", "increase", "save", "improve", "faster", "easier", "without", "so that"),
    )
    has_differentiator = _contains_any(
        lower,
        ("instead of", "unlike", "first", "only", "different", "unique", "better", "faster"),
    )
    has_distribution = _contains_any(
        lower,
        ("share", "viral", "invite", "community", "creator", "audience", "referral", "social", "newsletter"),
    )
    has_signal = _contains_any(
        lower,
        ("search", "demand", "market", "reddit", "trend", "signal", "volume", "community", "keyword"),
    )
    has_price = _contains_any(
        lower,
        ("price", "pricing", "$", "subscription", "plan", "monthly", "annual"),
    )
    has_proof = _contains_any(
        lower,
        ("proof", "data", "evidence", "pilot", "users", "customers", "results", "traction"),
    )

    concise_range = 20 <= word_count <= 90
    clear_length = 35 <= word_count <= 140

    idea_score = 46
    if clear_length:
        idea_score += 10
    if has_audience:
        idea_score += 9
    if has_outcome:
        idea_score += 10
    if has_differentiator:
        idea_score += 8
    if sentence_count > 1:
        idea_score += 4

    live_signal_score = 42
    if has_signal:
        live_signal_score += 12
    if has_distribution:
        live_signal_score += 11
    if has_outcome:
        live_signal_score += 6
    if has_price:
        live_signal_score += 5

    perception_score = 44
    if has_audience:
        perception_score += 11
    if has_outcome:
        perception_score += 10
    if has_price:
        perception_score += 8
    if has_proof:
        perception_score += 7

    spread_score = 43
    if concise_range:
        spread_score += 12
    if has_outcome:
        spread_score += 7
    if has_differentiator:
        spread_score += 8
    if has_distribution:
        spread_score += 6

    return {
        "clean_prompt": clean_prompt,
        "word_count": word_count,
        "sentence_count": sentence_count,
        "keywords": _extract_keywords(clean_prompt),
        "has_audience": has_audience,
        "has_outcome": has_outcome,
        "has_differentiator": has_differentiator,
        "has_distribution": has_distribution,
        "has_signal": has_signal,
        "has_price": has_price,
        "has_proof": has_proof,
        "idea_score": _clamp(idea_score),
        "live_signal_score": _clamp(live_signal_score),
        "perception_score": _clamp(perception_score),
        "spread_score": _clamp(spread_score),
    }


def build_analysis(prompt, plan, *, mode="idea", context_label="this concept"):
    clean_prompt = " ".join(prompt.split())
    breakdown = _score_breakdown(clean_prompt)
    keywords = breakdown["keywords"]
    focus = ", ".join(keywords) if keywords else "the clearest user pain"
    snippet = clean_prompt[:180]
    normalized_mode = normalize_test_mode(mode)

    idea_score = breakdown["idea_score"] + (4 if normalized_mode == "idea" else 0)
    live_signal_score = breakdown["live_signal_score"] + (5 if normalized_mode == "live_signals" else 0)
    perception_score = breakdown["perception_score"] + (5 if normalized_mode == "perception" else 0)
    spread_score = breakdown["spread_score"] + (5 if normalized_mode == "spread" else 0)

    analysis = {
        "idea_score": _clamp(idea_score),
        "idea_summary": (
            f"{context_label.capitalize()} is strongest when it stays centered on {focus}. "
            f"{'The audience is clear. ' if breakdown['has_audience'] else 'The audience still needs to be named more explicitly. '}"
            f"{'The outcome is easy to see.' if breakdown['has_outcome'] else 'The outcome should be stated more directly.'}"
        ),
        "live_signal_score": None,
        "live_signal_summary": "",
        "perception_score": None,
        "perception_summary": "",
        "spread_score": None,
        "spread_summary": "",
        "prompt_preview": snippet,
    }

    if plan in {"Starter", "Pro"}:
        analysis["live_signal_score"] = _clamp(live_signal_score)
        analysis["live_signal_summary"] = (
            f"Live-signal readiness improves when the language stays searchable around {focus}. "
            f"{'The prompt already hints at channels or demand sources. ' if breakdown['has_signal'] or breakdown['has_distribution'] else 'Add channel, market, or demand language to make external signal easier to read. '}"
            f"{'Pricing context is present.' if breakdown['has_price'] else 'A pricing or plan cue would make market intent easier to judge.'}"
        )

    if plan == "Pro":
        analysis["perception_score"] = _clamp(perception_score)
        analysis["perception_summary"] = (
            f"Perception is driven by how clearly the promise lands for a specific audience. "
            f"{'The framing leans outcome-first. ' if breakdown['has_outcome'] else 'Shift the framing away from mechanics and toward user payoff. '}"
            f"{'Trust signals are present.' if breakdown['has_proof'] else 'Proof, credibility, or concrete examples would make this feel safer and more premium.'}"
        )
        analysis["spread_score"] = _clamp(spread_score)
        analysis["spread_summary"] = (
            f"Spread is healthiest when someone can retell the idea in one sentence. "
            f"{'The pitch is compact enough to travel. ' if 20 <= breakdown['word_count'] <= 90 else 'Trim the pitch so the core claim is easier to repeat. '}"
            f"{'There is a noticeable differentiator.' if breakdown['has_differentiator'] else 'A sharper contrast or differentiator would improve retellability.'}"
        )

    return analysis


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
        "created_at": row[11],
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
        "created_at": row[12],
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


def create_project(user_id, name, description):
    with db_connection() as conn:
        with conn.cursor() as cur:
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
                    name.strip(),
                    description.strip(),
                ),
            )
            return cur.fetchone()[0]


def update_project(user_id, project_id, name, description):
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
                    name.strip(),
                    description.strip(),
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


def create_project_material(user_id, project_id, content, plan, mode="idea"):
    analysis = build_analysis(content, plan, mode=mode, context_label="this project")

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
                    spread_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    project_id,
                    content.strip(),
                    analysis["idea_score"],
                    analysis["live_signal_score"],
                    analysis["perception_score"],
                    analysis["spread_score"],
                    analysis["idea_summary"],
                    analysis["live_signal_summary"],
                    analysis["perception_summary"],
                    analysis["spread_summary"],
                ),
            )
            material_id = cur.fetchone()[0]

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
    analysis = build_analysis(prompt, plan, mode=normalized_mode)

    with db_connection() as conn:
        with conn.cursor() as cur:
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
                    spread_summary
                )
                VALUES (%s, %s, %s, %s, %s, %s, %s, %s, %s, %s, %s)
                RETURNING id
                """,
                (
                    user_id,
                    normalized_mode,
                    prompt.strip(),
                    analysis["idea_score"],
                    analysis["live_signal_score"],
                    analysis["perception_score"],
                    analysis["spread_score"],
                    analysis["idea_summary"],
                    analysis["live_signal_summary"],
                    analysis["perception_summary"],
                    analysis["spread_summary"],
                ),
            )
            return cur.fetchone()[0]


def convert_one_off_test_to_project(user_id, test_id, plan):
    test = get_one_off_test(user_id, test_id)
    if not test:
        return None

    project_id = create_project(
        user_id,
        _project_name_from_prompt(test["prompt"]),
        "Created from a one-off test.",
    )
    create_project_material(user_id, project_id, test["prompt"], plan, mode=test["mode"])
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
