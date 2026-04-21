import sqlite3
import os
from datetime import datetime

DB_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'jobs.db')


def _connect() -> sqlite3.Connection:
    conn = sqlite3.connect(DB_PATH)
    conn.row_factory = sqlite3.Row
    return conn


def init_db() -> None:
    os.makedirs(os.path.dirname(DB_PATH), exist_ok=True)
    with _connect() as conn:
        conn.execute("""
            CREATE TABLE IF NOT EXISTS jobs (
                id          TEXT PRIMARY KEY,
                title       TEXT NOT NULL,
                company     TEXT NOT NULL,
                location    TEXT,
                description TEXT,
                url         TEXT,
                score       INTEGER DEFAULT 0,
                language    TEXT DEFAULT 'en',
                zone        INTEGER DEFAULT 2,
                zone_label  TEXT DEFAULT 'Adjacent',
                tier        INTEGER DEFAULT 3,
                class_label TEXT DEFAULT 'C - Good',
                found_at    TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                status      TEXT DEFAULT 'pending'
            )
        """)
        conn.execute("""
            CREATE TABLE IF NOT EXISTS run_log (
                id          INTEGER PRIMARY KEY AUTOINCREMENT,
                run_at      TIMESTAMP DEFAULT CURRENT_TIMESTAMP,
                jobs_found  INTEGER DEFAULT 0,
                jobs_new    INTEGER DEFAULT 0,
                applied     INTEGER DEFAULT 0,
                notes       TEXT
            )
        """)
        conn.commit()


def job_exists(job_id: str) -> bool:
    with _connect() as conn:
        row = conn.execute("SELECT 1 FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return row is not None


def save_jobs(jobs: list[dict]) -> int:
    """Insert new jobs, skip duplicates. Returns count of inserted rows."""
    inserted = 0
    with _connect() as conn:
        for job in jobs:
            try:
                conn.execute(
                    """INSERT INTO jobs (id, title, company, location, description, url,
                                        score, language, zone, zone_label, tier, class_label,
                                        found_at, status)
                       VALUES (:id, :title, :company, :location, :description, :url,
                               :score, :language, :zone, :zone_label, :tier, :class_label,
                               :found_at, :status)""",
                    {
                        'id': job['id'],
                        'title': job['title'],
                        'company': job['company'],
                        'location': job.get('location', ''),
                        'description': job.get('description', ''),
                        'url': job.get('url', ''),
                        'score': job.get('score', 0),
                        'language': job.get('language', 'en'),
                        'zone': job.get('zone', 2),
                        'zone_label': job.get('zone_label', 'Adjacent'),
                        'tier': job.get('tier', 3),
                        'class_label': job.get('class_label', 'C - Good'),
                        'found_at': job.get('found_at', datetime.utcnow().isoformat()),
                        'status': job.get('status', 'pending'),
                    }
                )
                inserted += 1
            except sqlite3.IntegrityError:
                pass  # duplicate
        conn.commit()
    return inserted


def update_status(job_id: str, status: str) -> None:
    with _connect() as conn:
        conn.execute("UPDATE jobs SET status = ? WHERE id = ?", (status, job_id))
        conn.commit()


def get_pending_jobs() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = 'pending' ORDER BY score DESC"
        ).fetchall()
        return [dict(r) for r in rows]


def get_jobs_by_status(status: str) -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status = ? ORDER BY found_at DESC", (status,)
        ).fetchall()
        return [dict(r) for r in rows]


def get_job(job_id: str) -> dict | None:
    with _connect() as conn:
        row = conn.execute("SELECT * FROM jobs WHERE id = ?", (job_id,)).fetchone()
        return dict(row) if row else None


def log_run(jobs_found: int, jobs_new: int, applied: int, notes: str = '') -> None:
    with _connect() as conn:
        conn.execute(
            "INSERT INTO run_log (jobs_found, jobs_new, applied, notes) VALUES (?, ?, ?, ?)",
            (jobs_found, jobs_new, applied, notes)
        )
        conn.commit()


def get_all_non_pending() -> list[dict]:
    with _connect() as conn:
        rows = conn.execute(
            "SELECT * FROM jobs WHERE status != 'pending' ORDER BY found_at DESC LIMIT 200"
        ).fetchall()
        return [dict(r) for r in rows]


def delete_old_pending(hours: int = 24) -> int:
    """Delete pending jobs older than `hours` hours. Returns count deleted."""
    with _connect() as conn:
        cur = conn.execute(
            """DELETE FROM jobs
               WHERE status = 'pending'
               AND found_at < datetime('now', ? || ' hours')""",
            (f'-{hours}',)
        )
        conn.commit()
        return cur.rowcount
