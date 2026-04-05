"""
Flask dashboard for reviewing and actioning LinkedIn jobs.
Runs on http://localhost:5050
"""

import os
import sys
import threading

from flask import Flask, jsonify, render_template, request

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
            # Run apply in background thread so dashboard stays responsive
            t = threading.Thread(target=_apply_callback, args=(job,), daemon=True)
            t.start()
        return jsonify({'ok': True, 'status': 'approved', 'message': 'Auto-apply iniciado'})

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
