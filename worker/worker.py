import json
import os
import socket
import threading
import time

from db import db_connection, ensure_schema, wait_for_db
from pipeline import LLMPipeline


POLL_INTERVAL_SECONDS = float(os.environ.get("ANALYSIS_WORKER_POLL_INTERVAL", "2"))
WORKER_ID = os.environ.get("ANALYSIS_WORKER_ID", f"{socket.gethostname()}:{os.getpid()}")
_BACKGROUND_WORKER_ID = os.environ.get("ANALYSIS_APP_WORKER_ID", "web-app-worker")
_worker_condition = threading.Condition()
_worker_thread = None
_worker_requested = False


def _debug_log(message):
    print(f"[analysis_worker] {message}", flush=True)


def _target_table_for(job):
    if job["target_type"] == "project_material":
        return "project_materials"
    if job["target_type"] == "one_off_test":
        return "one_off_tests"
    raise ValueError(f"Unsupported analysis job target_type: {job['target_type']}")


def claim_next_analysis_job(worker_id):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                WITH next_job AS (
                    SELECT id, attempts
                    FROM analysis_jobs
                    WHERE status = 'pending' AND attempts < 2
                    ORDER BY created_at ASC
                    FOR UPDATE SKIP LOCKED
                    LIMIT 1
                )
                UPDATE analysis_jobs
                SET
                    status = 'processing',
                    worker_id = %s,
                    attempts = CASE WHEN (SELECT attempts FROM next_job) = 0 THEN 1 ELSE (SELECT attempts FROM next_job) + 1 END,
                    started_at = NOW(),
                    updated_at = NOW()
                WHERE id = (SELECT id FROM next_job)
                RETURNING
                    id,
                    target_type,
                    target_id,
                    prompt,
                    plan,
                    mode,
                    context_label,
                    status,
                    attempts,
                    worker_id,
                    created_at,
                    started_at,
                    payload
                """,
                (worker_id,),
            )
            row = cur.fetchone()
    if not row:
        return None
    print(f"Claimed job: {row[0]} with attempts: {row[8]}")

    return {
        "id": row[0],
        "target_type": row[1],
        "target_id": row[2],
        "prompt": row[3],
        "plan": row[4],
        "mode": row[5],
        "context_label": row[6],
        "status": row[7],
        "attempts": row[8],
        "worker_id": row[9],
        "created_at": row[10].isoformat() if row[10] else None,
        "started_at": row[11].isoformat() if row[11] else None,
        "payload": row[12] or {},
    }


def sync_target_record_status(job, status, *, extra_payload=None):
    table_name = _target_table_for(job)
    payload = {
        "status": status,
        "job": {
            "id": job["id"],
            "status": status,
            "attempts": job["attempts"],
            "worker_id": job["worker_id"],
            "target_type": job["target_type"],
            "target_id": job["target_id"],
        },
    }
    if extra_payload:
        payload.update(extra_payload)

    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                f"""
                UPDATE {table_name}
                SET analysis_payload = analysis_payload || %s::jsonb
                WHERE id = %s
                """,
                (json.dumps(payload), job["target_id"]),
            )


def mark_job_failed(job, exc):
    # If attempts < 2, set back to pending for retry, else mark as failed
    attempts = job.get("attempts", 0)
    new_status = "pending" if attempts < 2 else "failed"
    with db_connection() as conn:
        with conn.cursor() as cur:
            if new_status == "pending":
                cur.execute(
                    """
                    UPDATE analysis_jobs
                    SET
                        status = 'pending',
                        last_error = %s,
                        completed_at = NULL,
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(exc), job["id"]),
                )
            else:
                cur.execute(
                    """
                    UPDATE analysis_jobs
                    SET
                        status = 'failed',
                        last_error = %s,
                        completed_at = NOW(),
                        updated_at = NOW()
                    WHERE id = %s
                    """,
                    (str(exc), job["id"]),
                )
    sync_target_record_status(job, new_status, extra_payload={"error": str(exc)})
    _debug_log(f"Job {job['id']} failed (status set to {new_status}): {exc}")


def mark_job_completed(job, result=None):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE analysis_jobs
                SET
                    status = 'completed',
                    completed_at = NOW(),
                    updated_at = NOW(),
                    payload = COALESCE(payload, '{}'::jsonb) || %s::jsonb
                WHERE id = %s
                RETURNING completed_at
                """,
                (json.dumps(result or {}), job["id"]),
            )
            row = cur.fetchone()
    completed_at = row[0].isoformat() if row and row[0] else None
    sync_target_record_status(
        job,
        "completed",
        extra_payload={
            "completed_at": completed_at,
            "result": result or {},
        },
    )
    _debug_log(f"Job {job['id']} completed")


def prepare_job(job):
    sync_target_record_status(
        job,
        "processing",
        extra_payload={
            "processing_started_at": job["started_at"],
        },
    )
    _debug_log(
        "Picked up job "
        + json.dumps(
            {
                "id": job["id"],
                "target_type": job["target_type"],
                "target_id": job["target_id"],
                "plan": job["plan"],
                "mode": job["mode"],
                "attempts": job["attempts"],
                "worker_id": job["worker_id"],
            }
        )
    )


def run_worker_once(worker_id=WORKER_ID):
    job = claim_next_analysis_job(worker_id)
    if not job:
        return False

    try:
        print(f"Processing job {job['id']} for target {job['target_type']}:{job['target_id']} with plan {job['plan']} in mode {job['mode']}")
        prepare_job(job)
        LLMPipeline(job).run()
        mark_job_completed(job)
    except Exception as exc:
        
        mark_job_failed(job, exc)
        return True

    return True


def run_worker_loop(worker_id=WORKER_ID, poll_interval_seconds=POLL_INTERVAL_SECONDS):
    _debug_log(f"Worker starting worker_id={worker_id}")
    wait_for_db()
    ensure_schema()
    while True:
        claimed = run_worker_once(worker_id)
        if not claimed:
            time.sleep(poll_interval_seconds)


def _run_requested_jobs(worker_id):
    global _worker_requested, _worker_thread

    _debug_log(f"On-demand worker ready worker_id={worker_id}")
    wait_for_db()
    ensure_schema()

    while True:
        with _worker_condition:
            while not _worker_requested:
                notified = _worker_condition.wait(timeout=5)
                if not notified and not _worker_requested:
                    _worker_thread = None
                    _debug_log(f"On-demand worker exiting worker_id={worker_id}")
                    return
            _worker_requested = False

        while run_worker_once(worker_id):
            pass



# Entry function to start N worker threads
def start_worker_pool(worker_count=1):
    with db_connection() as conn:
        with conn.cursor() as cur:
            cur.execute(
                """
                UPDATE analysis_jobs
                SET status = 'pending', updated_at = NOW()
                WHERE status IN ('failed', 'processing')
                """
            )
            print(f"Reset {cur.rowcount} failed/processing jobs to pending for retry.")

    def worker_thread_fn(idx):
        _debug_log(f"Worker thread {idx} starting")
        run_worker_loop(worker_id=f"{WORKER_ID}-{idx}")

    threads = []
    for i in range(worker_count):
        t = threading.Thread(target=worker_thread_fn, args=(i,), daemon=True, name=f"analysis-worker-{i}")
        t.start()
        threads.append(t)
    # Wait for all threads to finish (they won't, as run_worker_loop is infinite)
    for t in threads:
        t.join()


if __name__ == "__main__":
    import sys
    count = 1
    if len(sys.argv) > 1:
        try:
            count = int(sys.argv[1])
        except Exception:
            print("Usage: python analysis_worker.py [worker_count]")
            sys.exit(1)
    start_worker_pool(worker_count=count)
