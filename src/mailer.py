"""
Gmail SMTP mailer for HR Emma notifications.

SECURITY SCOPE — READ BEFORE MODIFYING:
  Protocol used: SMTP (outbound-only, port 587 with STARTTLS)
  This module can ONLY:
    - Send emails FROM gmail_user TO gmail_user (self-notification only)
  This module can NEVER:
    - Read, access, or search the inbox (requires IMAP — not configured, not imported)
    - Send emails to any third party
    - Access contacts, calendar, Drive, or any other Google service
    - Modify, delete, or move any emails
  The App Password grants SMTP send-only access. Google enforces this at the protocol level.
"""

import os
import smtplib
import ssl
from datetime import datetime
from email.mime.application import MIMEApplication
from email.mime.multipart import MIMEMultipart
from email.mime.text import MIMEText

from dotenv import load_dotenv

load_dotenv()

GMAIL_USER = os.getenv('GMAIL_USER', 'emmanuel.rdrlp@gmail.com')
GMAIL_APP_PASSWORD = os.getenv('GMAIL_APP_PASSWORD', '')
DASHBOARD_PORT = int(os.getenv('DASHBOARD_PORT', 5050))
NGROK_STATIC_DOMAIN = os.getenv('NGROK_STATIC_DOMAIN', '')
RAILWAY_PUBLIC_DOMAIN = os.getenv('RAILWAY_PUBLIC_DOMAIN', '')


def _get_dashboard_url() -> str:
    """Return best available public URL: Railway > ngrok static > ngrok local API > localhost."""
    # Railway cloud deployment (auto-injected by Railway)
    if RAILWAY_PUBLIC_DOMAIN:
        return f"https://{RAILWAY_PUBLIC_DOMAIN}"
    # ngrok static domain (local tunnel)
    if NGROK_STATIC_DOMAIN:
        return f"https://{NGROK_STATIC_DOMAIN}"
    # ngrok dynamic URL (query local ngrok API)
    try:
        import urllib.request
        with urllib.request.urlopen('http://localhost:4040/api/tunnels', timeout=2) as r:
            import json as _json
            data = _json.loads(r.read())
            tunnels = data.get('tunnels', [])
            for t in tunnels:
                if t.get('proto') == 'https':
                    return t['public_url']
    except Exception:
        pass
    return f"http://localhost:{DASHBOARD_PORT}"


def _send(msg: MIMEMultipart) -> bool:
    """Send email via Gmail SMTP (outbound only). Returns True on success."""
    if not GMAIL_APP_PASSWORD:
        print("[mailer] GMAIL_APP_PASSWORD not set — skipping email.")
        return False

    # SECURITY: enforce self-only delivery — recipient must always be the owner
    recipient = msg['To']
    if recipient != GMAIL_USER:
        print(f"[mailer] BLOCKED — attempted to send to {recipient}. Only self-delivery allowed.")
        return False

    try:
        ctx = ssl.create_default_context()
        with smtplib.SMTP_SSL('smtp.gmail.com', 465, context=ctx) as server:
            server.login(GMAIL_USER, GMAIL_APP_PASSWORD)
            server.sendmail(GMAIL_USER, GMAIL_USER, msg.as_string())
        return True
    except Exception as e:
        print(f"[mailer] Failed to send email: {e}")
        return False


def _score_badge(score: int) -> str:
    if score >= 65:
        color = '#22c55e'  # green
        emoji = '🟢'
    elif score >= 40:
        color = '#f59e0b'  # yellow
        emoji = '🟡'
    else:
        color = '#ef4444'  # red
        emoji = '🔴'
    return f'<span style="background:{color};color:white;padding:2px 8px;border-radius:10px;font-weight:bold">{emoji} {score}</span>'


def send_job_digest(jobs: list[dict]) -> bool:
    """
    Send HTML email digest of new jobs to Emmanuel.
    jobs: list of job dicts (already filtered and scored).
    """
    if not jobs:
        return False

    now = datetime.now().strftime('%d/%m %H:%M')
    subject = f"🎯 HR Emma — {len(jobs)} nuevas posiciones [{now}]"

    # Sort by score
    sorted_jobs = sorted(jobs, key=lambda j: j.get('score', 0), reverse=True)

    rows = ''
    for job in sorted_jobs:
        score = job.get('score', 0)
        rows += f"""
        <tr style="border-bottom:1px solid #e5e7eb">
          <td style="padding:10px 8px;font-weight:600;color:#1e3a5f">{job['title']}</td>
          <td style="padding:10px 8px;color:#374151">{job['company']}</td>
          <td style="padding:10px 8px;color:#6b7280">{job.get('location','')}</td>
          <td style="padding:10px 8px;text-align:center">{_score_badge(score)}</td>
        </tr>"""

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;max-width:700px;margin:0 auto;padding:20px;color:#1f2937">
      <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px;border-radius:12px;margin-bottom:24px">
        <h1 style="color:white;margin:0;font-size:22px">🎯 HR Emma</h1>
        <p style="color:#93c5fd;margin:4px 0 0">{len(jobs)} nuevas posiciones encontradas — {now}</p>
      </div>

      <table style="width:100%;border-collapse:collapse;margin-bottom:24px">
        <thead>
          <tr style="background:#f3f4f6">
            <th style="padding:10px 8px;text-align:left;color:#374151">Posición</th>
            <th style="padding:10px 8px;text-align:left;color:#374151">Empresa</th>
            <th style="padding:10px 8px;text-align:left;color:#374151">Ubicación</th>
            <th style="padding:10px 8px;text-align:center;color:#374151">Score</th>
          </tr>
        </thead>
        <tbody>{rows}</tbody>
      </table>

      <div style="text-align:center;margin:32px 0">
        <a href="{_get_dashboard_url()}"
           style="background:#2563eb;color:white;padding:14px 32px;border-radius:8px;
                  text-decoration:none;font-weight:bold;font-size:16px">
          Revisar en Dashboard →
        </a>
      </div>

      <p style="color:#9ca3af;font-size:12px;text-align:center">
        HR Emma · Auto-generado · {now}
      </p>
    </body>
    </html>"""

    msg = MIMEMultipart('alternative')
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg.attach(MIMEText(html, 'html'))

    ok = _send(msg)
    if ok:
        print(f"[mailer] Digest sent: {len(jobs)} jobs")
    return ok


def send_manual_package(job: dict, cv_path: str, cl_path: str, excel_path: str = None) -> bool:
    """
    Send tailored CV + cover letter to Emmanuel for a manual application.
    cv_path: path to .docx CV file
    cl_path: path to .docx cover letter file
    """
    subject = f"📄 HR Emma — CV listo: {job['title']} @ {job['company']}"

    html = f"""
    <!DOCTYPE html>
    <html>
    <body style="font-family:Arial,sans-serif;max-width:600px;margin:0 auto;padding:20px">
      <div style="background:linear-gradient(135deg,#1e3a5f,#2563eb);padding:24px;border-radius:12px;margin-bottom:24px">
        <h1 style="color:white;margin:0;font-size:20px">📄 CV & Cover Letter Listo</h1>
      </div>

      <div style="background:#f8fafc;border-left:4px solid #2563eb;padding:16px;border-radius:4px;margin-bottom:20px">
        <p style="margin:0;font-size:16px"><strong>{job['title']}</strong></p>
        <p style="margin:4px 0 0;color:#6b7280">{job['company']} · {job.get('location','')}</p>
        <p style="margin:8px 0 0">
          <a href="{job.get('url','#')}" style="color:#2563eb">Ver oferta en LinkedIn →</a>
        </p>
      </div>

      <p>Adjunto encontrarás:</p>
      <ul>
        <li><strong>CV personalizado</strong> — adaptado a los keywords de esta posición</li>
        <li><strong>Cover letter personalizada</strong> — alineada al rol y empresa</li>
      </ul>

      <p style="color:#6b7280;font-size:13px">
        Score de fit: <strong>{job.get('score', 0)}/100</strong>
      </p>
    </body>
    </html>"""

    msg = MIMEMultipart()
    msg['Subject'] = subject
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    msg.attach(MIMEText(html, 'html'))

    attachments = [(cv_path, 'CV'), (cl_path, 'CoverLetter')]
    if excel_path:
        attachments.append((excel_path, 'Seguimiento'))
    for path, label in attachments:
        if path and os.path.exists(path):
            with open(path, 'rb') as f:
                part = MIMEApplication(f.read(), Name=os.path.basename(path))
                part['Content-Disposition'] = f'attachment; filename="{os.path.basename(path)}"'
                msg.attach(part)
        else:
            print(f"[mailer] {label} file not found: {path}")

    ok = _send(msg)
    if ok:
        print(f"[mailer] Manual package sent for {job['title']} @ {job['company']}")
    return ok


def send_alert(message: str) -> bool:
    """Send a plain-text alert email (e.g., login failure)."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '⚠️ HR Emma — Alerta del sistema'
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    html = f"""
    <html><body style="font-family:Arial,sans-serif;padding:20px">
      <div style="background:#fef2f2;border-left:4px solid #ef4444;padding:16px;border-radius:4px">
        <h2 style="color:#dc2626;margin:0">⚠️ Alerta HR Emma</h2>
        <p style="margin:8px 0 0">{message}</p>
      </div>
    </body></html>"""
    msg.attach(MIMEText(html, 'html'))
    return _send(msg)


def send_test() -> bool:
    """Send a test email to verify Gmail configuration."""
    msg = MIMEMultipart('alternative')
    msg['Subject'] = '✅ HR Emma — Test de conexión OK'
    msg['From'] = GMAIL_USER
    msg['To'] = GMAIL_USER
    html = """
    <html><body style="font-family:Arial,sans-serif;padding:20px">
      <div style="background:#f0fdf4;border-left:4px solid #22c55e;padding:16px;border-radius:4px">
        <h2 style="color:#16a34a;margin:0">✅ HR Emma configurado correctamente</h2>
        <p>El sistema de notificaciones por email funciona.</p>
      </div>
    </body></html>"""
    msg.attach(MIMEText(html, 'html'))
    ok = _send(msg)
    print(f"[mailer] Test email: {'SENT' if ok else 'FAILED'}")
    return ok


if __name__ == '__main__':
    send_test()
