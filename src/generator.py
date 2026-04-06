"""
Claude API-powered CV and cover letter generator.
Takes a job dict + master profile data → produces tailored .docx files.
Uses claude-sonnet-4-6 to tailor content to the specific job description.
"""

import json
import os
import re
import subprocess
import sys
from datetime import datetime

import anthropic
from docx import Document
from docx.enum.text import WD_ALIGN_PARAGRAPH
from docx.oxml import OxmlElement
from docx.oxml.ns import qn
from docx.shared import Cm, Pt, RGBColor
from dotenv import load_dotenv

load_dotenv()

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.database import update_status
from src.mailer import send_manual_package
from src.tracker import record_sent_cv, EXCEL_PATH
from templates.master_cover_letter import HEADER, STRUCTURE
from templates.master_cv import (
    CORE_COMPETENCIES, EDUCATION, EXPERIENCE, LANGUAGES, PROFILE,
    SOFTWARE, SUMMARY,
)

OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')
PHOTO_PATH = os.path.join(os.path.dirname(__file__), '..', 'Originales', 'Foto Emmma V2.jpg')
os.makedirs(OUTPUT_DIR, exist_ok=True)

client = anthropic.Anthropic(api_key=os.getenv('ANTHROPIC_API_KEY', ''))

CV_SYSTEM_PROMPT = """You are an elite ATS optimization consultant for senior FMCG executive roles.

You receive:
1. Emmanuel's master CV profile (JSON)
2. A job description

Your task: produce a tailored CV as JSON. Rules:
- NEVER fabricate experience or facts — only rearrange and re-emphasize what exists
- Rewrite the summary (max 3 sentences) mirroring the job's exact keywords
- ALWAYS include ALL roles from the master profile — never drop any position
- For each role, select the 3–5 most relevant bullet points (from master bullets list)
- Reorder core_competencies to put the most relevant ones first (max 12)
- Quantify every bullet — include %, dollar amounts, headcount, scale
- Executive tone: action verbs, business impact, strategic framing
- Do NOT add extra roles not in the master profile
- WRITING STYLE — human, natural, senior executive tone:
  * NO em dashes (— or –). Use a period or rewrite the sentence instead
  * NO Oxford commas (no comma before "and" in a list)
  * NO over-formal connectors like "Furthermore", "Moreover", "Additionally"
  * Vary sentence structure — not every bullet should start the same way
  * DO NOT mention visa, residency, work authorization or Austria eligibility anywhere in the CV content (it is already in the header)

Return ONLY valid JSON, no markdown, no explanation:
{
  "summary": "...",
  "core_competencies": ["...", ...],
  "experience": [
    {
      "title": "...",
      "company": "...",
      "start": "...",
      "end": "...",
      "bullets": ["...", ...]
    }
  ]
}"""

CL_SYSTEM_PROMPT = """You are an elite executive cover letter writer for senior FMCG roles.

You receive:
1. Emmanuel's profile summary
2. A job description
3. Cover letter structure template

Your task: write a tailored cover letter. Rules:
- Max 4 short paragraphs, ~250 words total
- Mirror keywords from the job description naturally
- Opening: strong hook referencing the specific role and company
- Body: 2 most relevant achievements that directly match job requirements
- Company fit: 1–2 sentences showing you researched this specific company
- Closing: confident, forward-looking
- WRITING STYLE — human, natural, senior executive tone:
  * NO em dashes (— or –). Use a period or rewrite the sentence instead
  * NO Oxford commas (no comma before "and" in a list)
  * NO over-formal connectors like "Furthermore", "Moreover", "Additionally"
  * Vary sentence structure
  * DO NOT mention visa, residency or work authorization (a dedicated paragraph is already appended after the letter body)

Return ONLY valid JSON:
{
  "salutation": "Dear [Name/Hiring Team],",
  "opening": "...",
  "body": "...",
  "company_fit": "...",
  "closing": "...",
  "sign_off": "Kind regards,\\nEmmanuel Rodríguez"
}"""


ML_SYSTEM_PROMPT = """You are writing a Letter of Motivation for Emmanuel Rodríguez applying to a senior FMCG role.

A Motivation Letter is DIFFERENT from a Cover Letter:
- Cover Letter: formal intro, key achievements, what you bring
- Motivation Letter: WHY this role and company, personal drive, career direction, cultural fit

Write 4 paragraphs, ~320 words total. Structure:
1. Opening: Why THIS specific role at THIS company excites you — specific, not generic
2. Why this field: Genuine professional drive for Consumer Insights / Analytics / Commercial Strategy
3. Why this company + career narrative: How their mission or market position connects with Emmanuel's trajectory and makes this the natural next step
4. Closing: Confident, forward-looking — include Austria residency naturally as a practical readiness note (one sentence, woven in, not a standalone announcement)

Rules:
- NEVER fabricate — draw only from Emmanuel's real background
- Human, personal, genuine — not corporate boilerplate
- NO em dashes (— or –). Use a period or rewrite the sentence
- NO Oxford commas (no comma before "and" in a list)
- NO over-formal connectors like "Furthermore", "Moreover", "Additionally"

Return ONLY valid JSON:
{
  "salutation": "Dear [Name/Hiring Team],",
  "opening": "...",
  "motivation_field": "...",
  "motivation_company": "...",
  "closing": "...",
  "sign_off": "Kind regards,\\nEmmanuel Rodríguez"
}"""


def _call_claude(system: str, user_message: str, max_tokens: int = 2000) -> str:
    message = client.messages.create(
        model='claude-sonnet-4-6',
        max_tokens=max_tokens,
        system=system,
        messages=[{'role': 'user', 'content': user_message}],
    )
    return message.content[0].text


def _tailor_cv(job: dict) -> dict:
    master_data = {
        'summary': SUMMARY,
        'core_competencies': CORE_COMPETENCIES,
        'experience': EXPERIENCE,
        'profile': PROFILE,
    }
    user_msg = f"""MASTER PROFILE:
{json.dumps(master_data, ensure_ascii=False, indent=2)}

JOB DESCRIPTION:
Title: {job['title']}
Company: {job['company']}
Location: {job.get('location', '')}

{job.get('description', '')[:3000]}"""

    raw = _call_claude(CV_SYSTEM_PROMPT, user_msg)
    # Strip any accidental markdown
    raw = re.sub(r'^```json\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    return json.loads(raw)


def _tailor_cover_letter(job: dict) -> dict:
    structure_str = json.dumps(STRUCTURE, ensure_ascii=False, indent=2)
    user_msg = f"""PROFILE SUMMARY:
{SUMMARY}

CONTACT:
{PROFILE['name']} | {PROFILE['address']} | {PROFILE['phone']} | {PROFILE['email']}
Work authorization: {PROFILE['work_authorization']}

COVER LETTER STRUCTURE TEMPLATE:
{structure_str}

JOB DESCRIPTION:
Title: {job['title']}
Company: {job['company']}
Location: {job.get('location', '')}

{job.get('description', '')[:3000]}"""

    raw = _call_claude(CL_SYSTEM_PROMPT, user_msg)
    raw = re.sub(r'^```json\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    return json.loads(raw)


def _tailor_motivation_letter(job: dict) -> dict:
    user_msg = f"""PROFILE SUMMARY:
{SUMMARY}

CONTACT:
{PROFILE['name']} | {PROFILE['address']} | {PROFILE['phone']} | {PROFILE['email']}

JOB DESCRIPTION:
Title: {job['title']}
Company: {job['company']}
Location: {job.get('location', '')}

{job.get('description', '')[:3000]}"""

    raw = _call_claude(ML_SYSTEM_PROMPT, user_msg)
    raw = re.sub(r'^```json\s*', '', raw.strip())
    raw = re.sub(r'\s*```$', '', raw.strip())
    return json.loads(raw)


def _safe_filename(text: str) -> str:
    return re.sub(r'[^\w\-]', '_', text)[:30]


def _docx_to_pdf(docx_path: str) -> str | None:
    """Convert a .docx to .pdf using LibreOffice. Returns pdf path or None on failure."""
    import shutil
    lo = shutil.which('libreoffice') or shutil.which('soffice')
    if not lo:
        for candidate in ['/usr/bin/libreoffice', '/usr/bin/soffice',
                          '/usr/lib/libreoffice/program/soffice']:
            if os.path.exists(candidate):
                lo = candidate
                break
    if not lo:
        print(f"[generator] LibreOffice not found — sending DOCX", flush=True)
        return None
    print(f"[generator] Using LibreOffice at: {lo}", flush=True)
    try:
        out_dir = os.path.dirname(docx_path)
        print(f"[generator] Converting to PDF: {docx_path}", flush=True)
        result = subprocess.run(
            [lo, '--headless', '--convert-to', 'pdf', '--outdir', out_dir, docx_path],
            capture_output=True, text=True, timeout=60
        )
        print(f"[generator] LO returncode={result.returncode} stdout={result.stdout[:100]} stderr={result.stderr[:100]}", flush=True)
        if result.returncode == 0:
            pdf_path = docx_path.replace('.docx', '.pdf')
            if os.path.exists(pdf_path):
                print(f"[generator] PDF created: {pdf_path}", flush=True)
                return pdf_path
            print(f"[generator] PDF file not found after conversion", flush=True)
        else:
            print(f"[generator] PDF conversion failed rc={result.returncode}: {result.stderr[:200]}", flush=True)
    except Exception as e:
        print(f"[generator] PDF conversion error: {e}", flush=True)
    return None


# --- DOCX builders ---

def _set_font(run, size=11, bold=False, color=None):
    run.font.size = Pt(size)
    run.font.bold = bold
    if color:
        run.font.color.rgb = RGBColor(*color)


def _remove_table_borders(table):
    """Remove all visible borders from a table (invisible layout table)."""
    tbl = table._tbl
    tblPr = tbl.find(qn('w:tblPr'))
    if tblPr is None:
        tblPr = OxmlElement('w:tblPr')
        tbl.insert(0, tblPr)
    tblBorders = OxmlElement('w:tblBorders')
    for side in ('top', 'left', 'bottom', 'right', 'insideH', 'insideV'):
        el = OxmlElement(f'w:{side}')
        el.set(qn('w:val'), 'none')
        tblBorders.append(el)
    tblPr.append(tblBorders)


def _build_cv_docx(tailored: dict, job: dict) -> str:
    doc = Document()

    # Margins
    for section in doc.sections:
        section.top_margin = Pt(36)
        section.bottom_margin = Pt(36)
        section.left_margin = Pt(54)
        section.right_margin = Pt(54)

    # Header: name+contact on left, photo on right
    header_table = doc.add_table(rows=1, cols=2)
    _remove_table_borders(header_table)
    left_cell = header_table.cell(0, 0)
    right_cell = header_table.cell(0, 1)

    # Left: name
    name_p = left_cell.paragraphs[0]
    run = name_p.add_run(PROFILE['name'])
    run.font.size = Pt(20)
    run.font.bold = True
    run.font.color.rgb = RGBColor(30, 58, 95)

    # Left: contact
    contact_p = left_cell.add_paragraph()
    contact_p.paragraph_format.space_after = Pt(2)
    run = contact_p.add_run(
        f"{PROFILE['address']}  |  {PROFILE['phone']}  |  {PROFILE['email']}  |  {PROFILE['linkedin']}"
    )
    _set_font(run, size=9, color=(107, 114, 128))

    # Left: work authorization
    auth_p = left_cell.add_paragraph()
    auth_p.paragraph_format.space_after = Pt(4)
    run = auth_p.add_run(PROFILE['work_authorization'])
    _set_font(run, size=9, bold=True, color=(37, 99, 235))

    # Right: photo
    photo_p = right_cell.paragraphs[0]
    photo_p.alignment = WD_ALIGN_PARAGRAPH.RIGHT
    if os.path.exists(PHOTO_PATH):
        photo_run = photo_p.add_run()
        photo_run.add_picture(PHOTO_PATH, width=Cm(2.8))

    # Divider
    doc.add_paragraph('─' * 80).paragraph_format.space_after = Pt(2)

    # Summary
    _add_section_header(doc, 'PROFESSIONAL SUMMARY')
    p = doc.add_paragraph()
    run = p.add_run(tailored.get('summary', SUMMARY))
    _set_font(run, size=10.5)
    p.paragraph_format.space_after = Pt(8)

    # Core Competencies
    _add_section_header(doc, 'CORE COMPETENCIES')
    comps = tailored.get('core_competencies', CORE_COMPETENCIES)[:12]
    # 3-column layout via tab stops
    for i in range(0, len(comps), 3):
        row = comps[i:i+3]
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run('  ·  '.join(f'▪ {c}' for c in row))
        _set_font(run, size=9.5)

    doc.add_paragraph('').paragraph_format.space_after = Pt(4)

    # Experience — guarantee all master roles appear even if Claude dropped some
    tailored_exp = tailored.get('experience', [])
    tailored_titles = {e.get('title', '').lower() for e in tailored_exp}
    for master_role in EXPERIENCE:
        if master_role['title'].lower() not in tailored_titles:
            tailored_exp.append(master_role)

    # Experience
    _add_section_header(doc, 'PROFESSIONAL EXPERIENCE')
    for exp in tailored_exp:
        # Role title + company
        p = doc.add_paragraph()
        p.paragraph_format.space_before = Pt(6)
        p.paragraph_format.space_after = Pt(0)
        run = p.add_run(exp['title'])
        _set_font(run, size=11, bold=True, color=(30, 58, 95))
        run2 = p.add_run(f"  —  {exp['company']}")
        _set_font(run2, size=10.5, color=(75, 85, 99))

        # Dates
        p2 = doc.add_paragraph()
        p2.paragraph_format.space_after = Pt(2)
        run = p2.add_run(f"{exp.get('start', '')} – {exp.get('end', '')}")
        _set_font(run, size=9, color=(156, 163, 175))

        # Bullets
        for bullet in exp.get('bullets', []):
            bp = doc.add_paragraph(style='List Bullet')
            bp.paragraph_format.space_after = Pt(1)
            run = bp.add_run(bullet)
            _set_font(run, size=10)

    doc.add_paragraph('').paragraph_format.space_after = Pt(4)

    # Education
    _add_section_header(doc, 'EDUCATION')
    for edu in EDUCATION:
        p = doc.add_paragraph()
        p.paragraph_format.space_after = Pt(2)
        run = p.add_run(f"{edu['degree']}  —  {edu['institution']}, {edu['location']}")
        _set_font(run, size=10.5, bold=True)
        run2 = p.add_run(f"  ({edu['start']} – {edu['end']})")
        _set_font(run2, size=9.5, color=(107, 114, 128))

    # Languages + Software
    _add_section_header(doc, 'LANGUAGES & TOOLS')
    lang_str = '  |  '.join(f"{l['language']} ({l['level']})" for l in LANGUAGES)
    sw_str = '  ·  '.join(SOFTWARE)
    p = doc.add_paragraph()
    run = p.add_run(f"Languages: {lang_str}")
    _set_font(run, size=10)
    p2 = doc.add_paragraph()
    run = p2.add_run(f"Tools: {sw_str}")
    _set_font(run, size=10)

    # Save
    date_str = datetime.now().strftime('%Y%m%d')
    fname = f"CV_Emmanuel_{_safe_filename(job['company'])}_{date_str}.docx"
    path = os.path.join(OUTPUT_DIR, fname)
    doc.save(path)
    print(f"[generator] CV saved: {path}")
    return path


def _add_section_header(doc, text: str):
    p = doc.add_paragraph()
    p.paragraph_format.space_before = Pt(8)
    p.paragraph_format.space_after = Pt(2)
    run = p.add_run(text)
    _set_font(run, size=10, bold=True, color=(30, 58, 95))
    run2 = p.add_run('\n' + '─' * 60)
    _set_font(run2, size=8, color=(209, 213, 219))


def _build_cl_docx(tailored: dict, job: dict) -> str:
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(54)
        section.bottom_margin = Pt(54)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    # Header
    h = doc.add_heading(HEADER['name'], 0)
    for run in h.runs:
        run.font.color.rgb = RGBColor(30, 58, 95)

    contact_p = doc.add_paragraph(
        f"{HEADER['address']}\n{HEADER['email']}  ·  {HEADER['phone']}"
    )
    for run in contact_p.runs:
        _set_font(run, size=10, color=(107, 114, 128))
    contact_p.paragraph_format.space_after = Pt(16)

    # Date
    date_p = doc.add_paragraph(datetime.now().strftime('%B %d, %Y'))
    for run in date_p.runs:
        _set_font(run, size=11)
    date_p.paragraph_format.space_after = Pt(12)

    # Salutation
    sal_p = doc.add_paragraph(tailored.get('salutation', 'Dear Hiring Team,'))
    for run in sal_p.runs:
        _set_font(run, size=11)
    sal_p.paragraph_format.space_after = Pt(10)

    # Body paragraphs
    for para_key in ['opening', 'body', 'company_fit']:
        text = tailored.get(para_key, '')
        if text:
            p = doc.add_paragraph(text)
            for run in p.runs:
                _set_font(run, size=11)
            p.paragraph_format.space_after = Pt(10)

    # Austria paragraph (always include)
    auth_text = (
        "I currently hold legal residence in Austria, ensuring full eligibility "
        "to live and work locally without any sponsorship requirement."
    )
    p = doc.add_paragraph(auth_text)
    for run in p.runs:
        _set_font(run, size=11)
    p.paragraph_format.space_after = Pt(10)

    # Closing
    closing = tailored.get(
        'closing',
        f"I would welcome the opportunity to discuss how my background can contribute to {job['company']}'s objectives. Thank you for your consideration."
    )
    p = doc.add_paragraph(closing)
    for run in p.runs:
        _set_font(run, size=11)
    p.paragraph_format.space_after = Pt(16)

    # Sign off
    p = doc.add_paragraph(tailored.get('sign_off', 'Kind regards,\nEmmanuel Rodríguez'))
    for run in p.runs:
        _set_font(run, size=11, bold=True)

    # Save
    date_str = datetime.now().strftime('%Y%m%d')
    fname = f"CoverLetter_Emmanuel_{_safe_filename(job['company'])}_{date_str}.docx"
    path = os.path.join(OUTPUT_DIR, fname)
    doc.save(path)
    print(f"[generator] Cover letter saved: {path}")
    return path


def _build_ml_docx(tailored: dict, job: dict) -> str:
    doc = Document()

    for section in doc.sections:
        section.top_margin = Pt(54)
        section.bottom_margin = Pt(54)
        section.left_margin = Pt(72)
        section.right_margin = Pt(72)

    # Header
    h = doc.add_heading(HEADER['name'], 0)
    for run in h.runs:
        run.font.color.rgb = RGBColor(30, 58, 95)

    contact_p = doc.add_paragraph(
        f"{HEADER['address']}\n{HEADER['email']}  ·  {HEADER['phone']}"
    )
    for run in contact_p.runs:
        _set_font(run, size=10, color=(107, 114, 128))
    contact_p.paragraph_format.space_after = Pt(16)

    # Date
    date_p = doc.add_paragraph(datetime.now().strftime('%B %d, %Y'))
    for run in date_p.runs:
        _set_font(run, size=11)
    date_p.paragraph_format.space_after = Pt(12)

    # Title
    title_p = doc.add_paragraph('LETTER OF MOTIVATION')
    for run in title_p.runs:
        _set_font(run, size=12, bold=True, color=(30, 58, 95))
    title_p.paragraph_format.space_after = Pt(12)

    # Salutation
    sal_p = doc.add_paragraph(tailored.get('salutation', 'Dear Hiring Team,'))
    for run in sal_p.runs:
        _set_font(run, size=11)
    sal_p.paragraph_format.space_after = Pt(10)

    # Body paragraphs
    for para_key in ['opening', 'motivation_field', 'motivation_company', 'closing']:
        text = tailored.get(para_key, '')
        if text:
            p = doc.add_paragraph(text)
            for run in p.runs:
                _set_font(run, size=11)
            p.paragraph_format.space_after = Pt(10)

    # Sign off
    p = doc.add_paragraph(tailored.get('sign_off', 'Kind regards,\nEmmanuel Rodríguez'))
    for run in p.runs:
        _set_font(run, size=11, bold=True)

    # Save
    date_str = datetime.now().strftime('%Y%m%d')
    fname = f"MotivationLetter_Emmanuel_{_safe_filename(job['company'])}_{date_str}.docx"
    path = os.path.join(OUTPUT_DIR, fname)
    doc.save(path)
    print(f"[generator] Motivation letter saved: {path}")
    return path


def generate_and_send(job: dict) -> tuple[str, str, str]:
    """
    Generate tailored CV + cover letter + motivation letter for a job.
    Saves as PDF (falls back to docx), emails all 3 to Emmanuel.
    Returns (cv_path, cl_path, ml_path).
    """
    print(f"[generator] Generating for: {job['title']} @ {job['company']}")

    try:
        tailored_cv = _tailor_cv(job)
    except Exception as e:
        print(f"[generator] Claude CV error: {e} — using master template")
        tailored_cv = {
            'summary': SUMMARY,
            'core_competencies': CORE_COMPETENCIES,
            'experience': EXPERIENCE,
        }

    try:
        tailored_cl = _tailor_cover_letter(job)
    except Exception as e:
        print(f"[generator] Claude CL error: {e} — using master template")
        tailored_cl = {
            'salutation': 'Dear Hiring Team,',
            'opening': STRUCTURE['opening'].replace('[ROLE]', job['title']).replace('[COMPANY]', job['company']),
            'body': '',
            'company_fit': '',
            'closing': STRUCTURE['closing'].replace('[COMPANY]', job['company']).replace('[KEY_AREA]', 'Consumer Insights & Commercial Strategy'),
            'sign_off': STRUCTURE['sign_off'],
        }

    try:
        tailored_ml = _tailor_motivation_letter(job)
    except Exception as e:
        print(f"[generator] Claude ML error: {e} — using fallback")
        tailored_ml = {
            'salutation': 'Dear Hiring Team,',
            'opening': f"I am writing to express my strong motivation for the {job['title']} role at {job['company']}.",
            'motivation_field': '',
            'motivation_company': '',
            'closing': 'I look forward to the opportunity to discuss how my background aligns with your goals. I am based in Austria with full eligibility to work locally.',
            'sign_off': 'Kind regards,\nEmmanuel Rodríguez',
        }

    cv_docx = _build_cv_docx(tailored_cv, job)
    cl_docx = _build_cl_docx(tailored_cl, job)
    ml_docx = _build_ml_docx(tailored_ml, job)

    # Convert to PDF (keep docx as fallback)
    cv_path = _docx_to_pdf(cv_docx) or cv_docx
    cl_path = _docx_to_pdf(cl_docx) or cl_docx
    ml_path = _docx_to_pdf(ml_docx) or ml_docx

    # Save PDF copy + update Excel tracker
    try:
        record_sent_cv(job, cv_path)
    except Exception as e:
        print(f"[generator] Tracker error (non-fatal): {e}")

    # Send email with CV, cover letter, motivation letter and Excel tracker attached
    excel = EXCEL_PATH if os.path.exists(EXCEL_PATH) else None
    send_manual_package(job, cv_path, cl_path, ml_path=ml_path, excel_path=excel)
    update_status(job['id'], 'sent')

    return cv_path, cl_path, ml_path
