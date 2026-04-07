"""
Flask dashboard for reviewing and actioning LinkedIn jobs.
Runs on http://localhost:5050
"""

import os
import sys
import threading

from flask import Flask, jsonify, render_template, request, send_file

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.database import get_all_non_pending, get_job, get_pending_jobs, update_status

TEMPLATES_DIR = os.path.join(os.path.dirname(__file__), 'web', 'templates')

app = Flask(__name__, template_folder=TEMPLATES_DIR)
app.secret_key = os.getenv('DASHBOARD_SECRET', 'hr-emma-dev-secret')

_apply_callback = None   # set by run.py to trigger apply.py
_generate_callback = None  # set by run.py to trigger generator.py


def register_callbacks(apply_fn, generate_fn):
    global _apply_callback, _generate_callback
    _apply_callback = apply_fn
    _generate_callback = generate_fn


@app.route('/')
def index():
    jobs = get_pending_jobs()
    return render_template('index.html', jobs=jobs, page='pending')


@app.route('/history')
def history():
    jobs = get_all_non_pending()
    return render_template('history.html', jobs=jobs, page='history')


@app.route('/job/<job_id>')
def job_detail(job_id):
    job = get_job(job_id)
    if not job:
        return 'Job not found', 404
    return render_template('job_detail.html', job=job, page='pending')


@app.route('/action/<job_id>', methods=['POST'])
def action(job_id):
    data = request.get_json(force=True)
    action_type = data.get('action', '')

    job = get_job(job_id)
    if not job:
        return jsonify({'ok': False, 'error': 'Job not found'}), 404

    if action_type == 'skip':
        update_status(job_id, 'skipped')
        return jsonify({'ok': True, 'status': 'skipped'})

    elif action_type == 'approve':
        update_status(job_id, 'approved')
        if _apply_callback:
            def _apply_with_fallback(job):
                import traceback
                print(f"[dashboard] apply thread started for {job['id']}", flush=True)
                try:
                    success = _apply_callback(job)
                except Exception as e:
                    print(f"[dashboard] _apply_callback EXCEPTION: {e}", flush=True)
                    traceback.print_exc()
                    success = False
                if not success and _generate_callback:
                    print(f"[dashboard] Apply failed for {job['id']} — generating CV as fallback")
                    _generate_callback(job)
            t = threading.Thread(target=_apply_with_fallback, args=(job,), daemon=True)
            t.start()
        return jsonify({'ok': True, 'status': 'approved', 'message': 'Aplicando en LinkedIn...'})

    elif action_type == 'manual':
        update_status(job_id, 'manual')
        if _generate_callback:
            t = threading.Thread(target=_generate_callback, args=(job,), daemon=True)
            t.start()
        return jsonify({'ok': True, 'status': 'manual', 'message': 'Generando CV personalizado...'})

    return jsonify({'ok': False, 'error': 'Unknown action'}), 400


@app.route('/status')
def status():
    pending = get_pending_jobs()
    return jsonify({
        'ok': True,
        'pending': len(pending),
    })


@app.route('/admin/add-job', methods=['POST'])
def add_job_manual():
    """Manually insert a job into the DB. Protected by DASHBOARD_SECRET."""
    secret = os.getenv('DASHBOARD_SECRET', '')
    data = request.get_json(force=True)
    if data.get('secret') != secret:
        return jsonify({'ok': False, 'error': 'Unauthorized'}), 403

    from src.filter import score_job, ZONE_LABELS
    from src.database import save_jobs
    from datetime import datetime

    job = {
        'id':          data.get('id') or f"manual_{int(datetime.utcnow().timestamp())}",
        'title':       data.get('title', ''),
        'company':     data.get('company', ''),
        'location':    data.get('location', ''),
        'description': data.get('description', ''),
        'url':         data.get('url', ''),
        'found_at':    datetime.utcnow().isoformat(),
    }
    if not job['title'] or not job['company']:
        return jsonify({'ok': False, 'error': 'title and company required'}), 400

    score, lang, zone, tier, cl = score_job(job)
    job.update({'score': score, 'language': lang, 'zone': zone,
                'zone_label': ZONE_LABELS.get(zone, ''), 'tier': tier,
                'class_label': cl, 'status': 'pending'})
    inserted = save_jobs([job])
    if inserted == 0:
        # Already exists — update url and status to pending
        from src.database import _connect
        with _connect() as conn:
            conn.execute(
                "UPDATE jobs SET url=?, status='pending', score=?, class_label=?, zone=?, zone_label=?, tier=? WHERE id=?",
                (job['url'], score, cl, zone, ZONE_LABELS.get(zone,''), tier, job['id'])
            )
            conn.commit()
    return jsonify({'ok': True, 'inserted': inserted, 'updated': 1 if inserted == 0 else 0,
                    'score': score, 'class_label': cl, 'id': job['id']})


@app.route('/admin/reset-all', methods=['POST'])
def reset_all_to_pending():
    """Reset all non-pending jobs back to pending so they can be re-actioned."""
    from src.database import _connect
    with _connect() as conn:
        result = conn.execute(
            "UPDATE jobs SET status = 'pending' WHERE status IN ('sent', 'applied', 'manual', 'skipped', 'approved')"
        )
        count = result.rowcount
        conn.commit()
    return jsonify({'ok': True, 'reset': count})


@app.route('/admin/rescore', methods=['POST'])
def rescore_all():
    """Re-score all skipped jobs with current filter logic. Recovers false-positives."""
    from src.filter import score_job, ZONE_LABELS
    from src.database import _connect
    recovered = 0
    with _connect() as conn:
        rows = conn.execute(
            "SELECT id, title, company, location, description FROM jobs WHERE status = 'skipped'"
        ).fetchall()
        for row in rows:
            job = dict(row)
            job['description'] = job.get('description') or ''
            score, language, zone, tier, class_label = score_job(job)
            if language != 'excluded' and score >= 40:
                conn.execute(
                    """UPDATE jobs SET status='pending', score=?, language=?, zone=?, zone_label=?, tier=?, class_label=?
                       WHERE id=?""",
                    (score, language, zone, ZONE_LABELS.get(zone, ''), tier, class_label, job['id'])
                )
                recovered += 1
        conn.commit()
    return jsonify({'ok': True, 'recovered': recovered, 'total_skipped': len(rows)})


@app.route('/admin/refilter', methods=['POST'])
def refilter_pending():
    """Re-apply location filter to all pending jobs, skip ineligible ones."""
    from src.filter import _is_location_eligible
    jobs = get_pending_jobs()
    skipped = 0
    for job in jobs:
        if not _is_location_eligible(job.get('location', ''), job.get('description', '')):
            update_status(job['id'], 'skipped')
            skipped += 1
    return jsonify({'ok': True, 'skipped': skipped, 'remaining': len(jobs) - skipped})


@app.route('/admin/send-digest', methods=['POST'])
def send_digest():
    """Manually trigger email digest for all pending jobs."""
    from src.mailer import send_job_digest
    jobs = get_pending_jobs()
    if not jobs:
        return jsonify({'ok': False, 'message': 'No pending jobs to send'})
    ok = send_job_digest(jobs)
    return jsonify({'ok': ok, 'message': f'Digest sent with {len(jobs)} jobs' if ok else 'Failed to send'})


@app.route('/download/tracker')
def download_tracker():
    """Download the Excel tracker file."""
    from src.tracker import EXCEL_PATH
    if not os.path.exists(EXCEL_PATH):
        return 'No hay CVs enviados todavía.', 404
    return send_file(EXCEL_PATH, as_attachment=True, download_name='Seguimiento Jobs.xlsx')


@app.route('/admin/cookie', methods=['GET', 'POST'])
def update_cookie():
    """Admin endpoint to update LinkedIn cookie remotely."""
    secret = os.getenv('DASHBOARD_SECRET', '')
    if request.method == 'GET':
        return f'''
        <html><body style="font-family:Arial;max-width:500px;margin:50px auto;padding:20px">
        <h2>Update LinkedIn Cookie</h2>
        <form method="POST">
          <p><label>Admin Password:<br>
          <input type="password" name="secret" style="width:100%;padding:8px;margin:4px 0"></label></p>
          <p><label>li_at cookie value:<br>
          <textarea name="li_at" rows="4" style="width:100%;padding:8px;margin:4px 0"></textarea></label></p>
          <button type="submit" style="background:#2563eb;color:white;padding:10px 24px;border:none;border-radius:6px;cursor:pointer">Update Cookie</button>
        </form>
        </body></html>'''

    data = request.form
    if data.get('secret') != secret:
        return '<p style="color:red">Wrong password.</p>', 403

    li_at = data.get('li_at', '').strip()
    if not li_at:
        return '<p style="color:red">Empty cookie value.</p>', 400

    import json as _json
    cookies_path = os.path.join(os.path.dirname(__file__), '..', 'data', 'cookies', 'linkedin_cookies.json')
    os.makedirs(os.path.dirname(cookies_path), exist_ok=True)
    with open(cookies_path, 'w') as f:
        _json.dump([{
            "name": "li_at", "value": li_at,
            "domain": ".www.linkedin.com", "path": "/",
            "httpOnly": True, "secure": True, "session": False
        }], f)
    print(f"[admin] LinkedIn cookie updated.")
    return '<html><body style="font-family:Arial;max-width:500px;margin:50px auto;padding:20px"><p style="color:green;font-size:18px">Cookie updated successfully.</p><a href="/">Go to Dashboard</a></body></html>'


def run_dashboard(port: int = 5050, debug: bool = False):
    app.run(host='0.0.0.0', port=port, debug=debug, use_reloader=False)
