import time

import psycopg

from config import DATABASE_URL


def db_connection():
    return psycopg.connect(DATABASE_URL)


def wait_for_db(attempts=20, delay_seconds=1.5):
    for attempt in range(attempts):
        try:
            with db_connection() as conn:
                with conn.cursor() as cur:
                    cur.execute("SELECT 1")
            return
        except psycopg.Error:
            if attempt == attempts - 1:
                raise
            time.sleep(delay_seconds)
