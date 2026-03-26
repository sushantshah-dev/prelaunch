import json

from db import db_connection


def _debug_log(message):
    print(f"[analysis_queue] {message}", flush=True)


def enqueue_analysis_job(*, target_type, target_id, prompt, plan, mode="idea", context_label="this concept"):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                INSERT INTO analysis_jobs (
                    target_type,
                    target_id,
                    prompt,
                    plan,
                    mode,
                    context_label,
                    status,
                    payload
                )
                VALUES (%s, %s, %s, %s, %s, %s, 'pending', %s)
                RETURNING id, status, created_at
                """,
                (
                    target_type,
                    target_id,
                    prompt,
                    plan,
                    mode,
                    context_label,
                    json.dumps({"status": "pending"}),
                ),
            )
            row = cur.fetchone()

    job = {
        "id": row[0],
        "status": row[1],
        "created_at": row[2].isoformat() if row[2] else None,
        "target_type": target_type,
        "target_id": target_id,
        "plan": plan,
        "mode": mode,
        "context_label": context_label,
    }
    _debug_log(f"Enqueued analysis job {json.dumps(job)}")
    return job
