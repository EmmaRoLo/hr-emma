"""
Hourly pipeline orchestrator.
Runs: scrape → filter → save → notify.
Dashboard (Flask) runs in a background thread.
"""

import asyncio
import os
import sys

from apscheduler.schedulers.background import BackgroundScheduler
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.database import get_pending_jobs, job_exists, log_run, save_jobs
from src.filter import filter_and_score
from src.mailer import send_alert, send_job_digest
from src.scraper import scrape_jobs

MAX_AUTO_APPLY = int(os.getenv('MAX_AUTO_APPLY_PER_HOUR', 10))
_auto_apply_count = 0


def reset_apply_counter():
    global _auto_apply_count
    _auto_apply_count = 0


def run_pipeline():
    """Main hourly pipeline: scrape → filter → save → notify."""
    print('\n[pipeline] --- Starting hourly run ---')

    # 1. Scrape
    raw_jobs = asyncio.run(scrape_jobs(notify_login_error=send_alert))
    print(f"[pipeline] Scraped {len(raw_jobs)} raw jobs")

    if not raw_jobs:
        log_run(0, 0, 0, 'scraper returned 0 jobs')
        return

    # 2. Filter & score (deduplicate against DB)
    existing_ids = {j['id'] for j in raw_jobs if job_exists(j['id'])}
    to_save, skipped = filter_and_score(raw_jobs, existing_ids)

    print(f"[pipeline] New qualified jobs: {len(to_save)} | Skipped: {len(skipped)}")

    # 3. Save to DB (saves skipped too for deduplication, but status='skipped')
    all_to_insert = to_save + skipped
    inserted = save_jobs(all_to_insert)
    print(f"[pipeline] Inserted {inserted} new rows to DB")

    # 4. Notify by email — new jobs this run + all pending in DB
    new_pending = [j for j in to_save if j.get('status') == 'pending']
    all_pending = get_pending_jobs()

    if new_pending:
        print(f"[pipeline] Sending digest: {len(new_pending)} new + {len(all_pending)} total pending")
        send_job_digest(all_pending)
    elif all_pending:
        print(f"[pipeline] No new jobs but {len(all_pending)} still pending — sending reminder digest")
        send_job_digest(all_pending)
    else:
        print("[pipeline] No pending jobs to notify about.")

    log_run(
        jobs_found=len(raw_jobs),
        jobs_new=len(to_save),
        applied=0,
        notes=f"skipped={len(skipped)}"
    )
    print('[pipeline] --- Run complete ---\n')


def create_scheduler() -> BackgroundScheduler:
    scheduler = BackgroundScheduler()

    # Main pipeline: every hour
    scheduler.add_job(
        run_pipeline,
        trigger='interval',
        hours=1,
        id='linkedin_pipeline',
        max_instances=1,
        coalesce=True,
    )

    # Reset auto-apply counter at midnight
    scheduler.add_job(
        reset_apply_counter,
        trigger='cron',
        hour=0,
        minute=0,
        id='reset_counter',
    )

    return scheduler
