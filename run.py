"""
HR Emma — Entry point.

Starts:
  1. SQLite DB initialization
  2. Flask dashboard on port 5050 (background thread)
  3. APScheduler hourly pipeline (main thread — blocks)

Usage:
  python run.py              # Normal start (runs immediately + every hour)
  python run.py --now        # Run pipeline once immediately, then exit
  python run.py --dashboard  # Dashboard only (no scheduler)
  python run.py --test-mail  # Test Gmail connection
  python run.py --test-auth  # Test LinkedIn cookie authentication
"""

import argparse
import asyncio
import os
import sys
import threading

from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(__file__))

from src.database import init_db
from src.apply import apply_sync
from src.generator import generate_and_send
from src.dashboard import app as flask_app, register_callbacks, run_dashboard
from src.scheduler import create_scheduler, run_pipeline

# Railway injects PORT; fallback to DASHBOARD_PORT for local use
DASHBOARD_PORT = int(os.getenv('PORT', os.getenv('DASHBOARD_PORT', 5050)))


def start_dashboard_thread():
    t = threading.Thread(
        target=run_dashboard,
        kwargs={'port': DASHBOARD_PORT},
        daemon=True,
        name='dashboard',
    )
    t.start()
    print(f"[run] Dashboard started at http://localhost:{DASHBOARD_PORT}")
    return t


def main():
    parser = argparse.ArgumentParser(description='HR Emma — LinkedIn Job Agent')
    parser.add_argument('--now', action='store_true', help='Run pipeline once immediately then exit')
    parser.add_argument('--dashboard', action='store_true', help='Start dashboard only')
    parser.add_argument('--test-mail', action='store_true', help='Test Gmail SMTP')
    parser.add_argument('--test-auth', action='store_true', help='Test LinkedIn cookie auth')
    args = parser.parse_args()

    # Init DB and data directories
    os.makedirs('data/cookies', exist_ok=True)
    os.makedirs('output', exist_ok=True)
    init_db()
    print("[run] Database initialized.")

    # On Railway, write cookies from env var if cookies file is missing
    cookies_path = 'data/cookies/linkedin_cookies.json'
    if not os.path.exists(cookies_path):
        li_at = os.getenv('LINKEDIN_COOKIE', '')
        if li_at:
            import json as _json
            with open(cookies_path, 'w') as f:
                _json.dump([{
                    "name": "li_at", "value": li_at,
                    "domain": ".www.linkedin.com", "path": "/",
                    "httpOnly": True, "secure": True, "session": False
                }], f)
            print("[run] LinkedIn cookie written from env var.")

    if args.test_mail:
        from src.mailer import send_test
        send_test()
        return

    if args.test_auth:
        from src.scraper import test_auth
        ok = asyncio.run(test_auth())
        sys.exit(0 if ok else 1)

    if args.now:
        run_pipeline()
        return

    # Register callbacks so dashboard can trigger apply/generate
    register_callbacks(
        apply_fn=apply_sync,
        generate_fn=generate_and_send,
    )

    if args.dashboard:
        print(f"[run] Dashboard-only mode — http://localhost:{DASHBOARD_PORT}")
        run_dashboard(port=DASHBOARD_PORT)
        return

    # Normal mode: dashboard + scheduler
    start_dashboard_thread()

    scheduler = create_scheduler()
    scheduler.start()
    print("[run] Scheduler started. Pipeline runs every hour.")
    print("[run] Running first pipeline immediately...")
    run_pipeline()

    print(f"\n[run] HR Emma is running.")
    print(f"[run] Dashboard: http://localhost:{DASHBOARD_PORT}")
    print("[run] Press Ctrl+C to stop.\n")

    try:
        import time
        while True:
            time.sleep(60)
    except KeyboardInterrupt:
        print("\n[run] Shutting down...")
        scheduler.shutdown(wait=False)


if __name__ == '__main__':
    main()
