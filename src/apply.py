"""
LinkedIn job application automation using Playwright.
1. Tries LinkedIn Easy Apply first.
2. If no Easy Apply, follows the external "Apply" button to the company portal
   and fills common fields (Workday, Greenhouse, Lever, generic).
Safety guards: CAPTCHA detection, form complexity limit, login redirect.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys

try:
    from playwright.async_api import async_playwright, Page, BrowserContext, TimeoutError as PlaywrightTimeout
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False
    PlaywrightTimeout = Exception

sys.path.insert(0, os.path.dirname(os.path.dirname(__file__)))
from src.database import update_status

COOKIES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cookies', 'linkedin_cookies.json')
OUTPUT_DIR = os.path.join(os.path.dirname(__file__), '..', 'output')

# Emmanuel's pre-fill data
APPLICANT = {
    'phone': '+43 66021 64853',
    'first_name': 'Emmanuel',
    'last_name': 'Rodríguez',
    'email': 'emmanuel.rdrlp@gmail.com',
    'city': 'Groß Gerungs',
    'country': 'Austria',
    'salary_expectation': '110000',
    'years_experience': '10',
    'work_authorization_austria': True,
    'english_level': 'Professional working proficiency',
    'german_level': 'No proficiency',
    'cover_letter': (
        "Commercial & Insights Leader with 10+ years in FMCG (PepsiCo, Nielsen, Kantar). "
        "Expert in consumer insights, advanced analytics, and commercial strategy. "
        "Based in Austria with full EU work authorization."
    ),
}

MAX_STEPS = 8


async def _random_delay(min_s=1.5, max_s=4.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _load_cookies(context: BrowserContext) -> bool:
    if not os.path.exists(COOKIES_PATH):
        return False
    with open(COOKIES_PATH) as f:
        cookies = json.load(f)
    for c in cookies:
        if 'domain' not in c or not c['domain']:
            c['domain'] = '.linkedin.com'
    await context.add_cookies(cookies)
    return True


async def _detect_captcha(page: Page) -> bool:
    for sel in ['[id*="captcha"]', '[class*="captcha"]',
                'iframe[src*="recaptcha"]', 'iframe[src*="hcaptcha"]']:
        if await page.query_selector(sel):
            return True
    return False


async def _fill_field(page: Page, label_text: str, value: str) -> bool:
    """Try multiple strategies to find and fill a text field by label."""
    try:
        # aria-label
        field = await page.query_selector(f'input[aria-label*="{label_text}" i]')
        if field and await field.is_visible():
            await field.fill(value)
            return True
        # placeholder
        field = await page.query_selector(f'input[placeholder*="{label_text}" i]')
        if field and await field.is_visible():
            await field.fill(value)
            return True
        # label → for → input
        labels = await page.query_selector_all('label')
        for label in labels:
            text = await label.inner_text()
            if label_text.lower() in text.lower():
                for_attr = await label.get_attribute('for')
                if for_attr:
                    inp = await page.query_selector(f'#{for_attr}')
                    if inp and await inp.is_visible():
                        await inp.fill(value)
                        return True
                # sibling input
                inp = await label.query_selector('input')
                if inp and await inp.is_visible():
                    await inp.fill(value)
                    return True
        # name attribute
        field = await page.query_selector(f'input[name*="{label_text}" i]')
        if field and await field.is_visible():
            await field.fill(value)
            return True
    except Exception:
        pass
    return False


async def _fill_generic_form(page: Page) -> None:
    """Fill common fields found on any job application form."""
    await _random_delay(1.0, 2.0)

    # Name fields
    for lbl in ['first name', 'firstname', 'first_name', 'given name', 'vorname']:
        await _fill_field(page, lbl, APPLICANT['first_name'])
    for lbl in ['last name', 'lastname', 'last_name', 'surname', 'family name', 'nachname']:
        await _fill_field(page, lbl, APPLICANT['last_name'])

    # Email
    for lbl in ['email', 'e-mail', 'email address']:
        field = await page.query_selector('input[type="email"]')
        if field and await field.is_visible():
            await field.fill(APPLICANT['email'])
            break
        await _fill_field(page, lbl, APPLICANT['email'])

    # Phone
    for lbl in ['phone', 'mobile', 'telephone', 'tel', 'phone number']:
        await _fill_field(page, lbl, APPLICANT['phone'])

    # Location
    for lbl in ['city', 'location', 'address', 'city/town', 'stadt']:
        await _fill_field(page, lbl, APPLICANT['city'])

    # Country
    for lbl in ['country', 'land']:
        # Try select
        sel = await page.query_selector(f'select[aria-label*="{lbl}" i]')
        if not sel:
            sel = await page.query_selector(f'select[name*="{lbl}" i]')
        if sel and await sel.is_visible():
            try:
                await sel.select_option(label='Austria')
            except Exception:
                try:
                    await sel.select_option(value='AT')
                except Exception:
                    pass
        else:
            await _fill_field(page, lbl, APPLICANT['country'])

    # Salary
    for lbl in ['salary', 'expected salary', 'desired salary', 'gehalt', 'compensation']:
        await _fill_field(page, lbl, APPLICANT['salary_expectation'])

    # Years of experience
    for lbl in ['years of experience', 'years experience', 'experience']:
        await _fill_field(page, lbl, APPLICANT['years_experience'])
        sel = await page.query_selector(f'select[aria-label*="{lbl}" i]')
        if sel and await sel.is_visible():
            try:
                await sel.select_option(label='10+')
            except Exception:
                pass

    # Cover letter / message textarea
    textareas = await page.query_selector_all('textarea')
    for ta in textareas:
        if await ta.is_visible():
            current = await ta.input_value()
            if not current:
                await ta.fill(APPLICANT['cover_letter'])
            break

    # Work authorization — radio Yes
    for lbl in ['authorized', 'work authorization', 'eligible to work', 'visa', 'right to work']:
        radios = await page.query_selector_all(f'input[type="radio"]')
        for r in radios:
            aria = (await r.get_attribute('aria-label') or '').lower()
            val = (await r.get_attribute('value') or '').lower()
            if 'yes' in aria or 'yes' in val or 'true' in val:
                try:
                    await r.click()
                except Exception:
                    pass
                break


# ── Portal-specific handlers ─────────────────────────────────────────────────

async def _apply_workday(page: Page, job_id: str) -> bool:
    """Handle Workday application portal."""
    print(f"[apply] Detected Workday portal for {job_id}", flush=True)
    try:
        await _random_delay(2.0, 3.5)
        # Click "Apply" or "Apply Manually" if present
        for sel in ['a[data-automation-id*="apply" i]', 'button[data-automation-id*="apply" i]',
                    'a:has-text("Apply")', 'button:has-text("Apply Manually")']:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await _random_delay(2.0, 3.0)
                break

        step = 0
        while step < MAX_STEPS:
            await _fill_generic_form(page)

            # Submit
            for sel in ['button[data-automation-id*="bottom-navigation-next-button"]',
                        'button[aria-label*="submit" i]', 'button:has-text("Submit")']:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await _random_delay(2.0, 3.0)
                    if 'submit' in sel.lower() or 'Submit' in sel:
                        print(f"[apply] Workday: submitted {job_id}", flush=True)
                        return True

            # Next
            next_found = False
            for sel in ['button[data-automation-id*="bottom-navigation-next-button"]',
                        'button:has-text("Next")', 'button:has-text("Continue")',
                        'button[aria-label*="next" i]']:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await _random_delay(1.5, 2.5)
                    step += 1
                    next_found = True
                    break

            if not next_found:
                break

        return False
    except Exception as e:
        print(f"[apply] Workday error: {e}", flush=True)
        return False


async def _apply_greenhouse(page: Page, job_id: str) -> bool:
    """Handle Greenhouse application portal."""
    print(f"[apply] Detected Greenhouse portal for {job_id}", flush=True)
    try:
        await _random_delay(2.0, 3.0)
        await _fill_generic_form(page)

        # Upload resume if field present — skip for now, log it
        resume_input = await page.query_selector('input[type="file"]')
        if resume_input:
            print(f"[apply] Greenhouse: resume upload required — skipping file", flush=True)

        # Submit
        for sel in ['input[type="submit"]', 'button[type="submit"]',
                    'button:has-text("Submit Application")', 'button:has-text("Submit")']:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await _random_delay(2.0, 3.0)
                print(f"[apply] Greenhouse: submitted {job_id}", flush=True)
                return True
        return False
    except Exception as e:
        print(f"[apply] Greenhouse error: {e}", flush=True)
        return False


async def _apply_lever(page: Page, job_id: str) -> bool:
    """Handle Lever application portal."""
    print(f"[apply] Detected Lever portal for {job_id}", flush=True)
    try:
        await _random_delay(2.0, 3.0)
        await _fill_generic_form(page)

        for sel in ['button[type="submit"]', 'button:has-text("Submit Application")',
                    'button:has-text("Apply")', 'input[type="submit"]']:
            btn = await page.query_selector(sel)
            if btn and await btn.is_visible():
                await btn.click()
                await _random_delay(2.0, 3.0)
                print(f"[apply] Lever: submitted {job_id}", flush=True)
                return True
        return False
    except Exception as e:
        print(f"[apply] Lever error: {e}", flush=True)
        return False


async def _apply_external_portal(page: Page, job_id: str, portal_url: str) -> bool:
    """
    Navigate to external portal and attempt form fill + submit.
    Detects Workday / Greenhouse / Lever; falls back to generic.
    """
    print(f"[apply] External portal: {portal_url[:80]}", flush=True)
    try:
        await page.goto(portal_url, wait_until='domcontentloaded', timeout=30000)
        await _random_delay(2.0, 4.0)

        if await _detect_captcha(page):
            print(f"[apply] CAPTCHA on external portal — routing to manual", flush=True)
            return False

        url = page.url.lower()

        if 'myworkdayjobs' in url or 'workday' in url:
            return await _apply_workday(page, job_id)
        elif 'greenhouse.io' in url or 'boards.greenhouse' in url:
            return await _apply_greenhouse(page, job_id)
        elif 'jobs.lever.co' in url or 'lever.co' in url:
            return await _apply_lever(page, job_id)
        else:
            # Generic: fill + try submit
            print(f"[apply] Generic portal for {job_id}", flush=True)
            await _fill_generic_form(page)
            for sel in ['button[type="submit"]', 'input[type="submit"]',
                        'button:has-text("Submit")', 'button:has-text("Apply")',
                        'button:has-text("Send Application")']:
                btn = await page.query_selector(sel)
                if btn and await btn.is_visible():
                    await btn.click()
                    await _random_delay(2.0, 3.0)
                    print(f"[apply] Generic portal: submitted {job_id}", flush=True)
                    return True
            return False
    except Exception as e:
        print(f"[apply] External portal error: {e}", flush=True)
        return False


# ── LinkedIn Easy Apply ───────────────────────────────────────────────────────

async def _handle_easy_apply_step(page: Page, step_num: int) -> None:
    """Fill fields on a single LinkedIn Easy Apply step."""
    await _random_delay(1.0, 2.5)
    await _fill_generic_form(page)


async def apply_to_job(job: dict) -> bool:
    """
    1. Try LinkedIn Easy Apply.
    2. If no Easy Apply button, follow external Apply link to company portal.
    Returns True if application submitted successfully.
    """
    job_id = job['id']
    url = job.get('url', '')

    if not _PLAYWRIGHT_AVAILABLE:
        print(f"[apply] Playwright not installed — routing {job_id} to manual.")
        update_status(job_id, 'manual')
        return False

    print(f"[apply] Starting browser for job {job_id}: {job.get('title')} @ {job.get('company')}", flush=True)
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=['--no-sandbox', '--disable-setuid-sandbox', '--disable-dev-shm-usage'],
        )
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        )

        if not await _load_cookies(context):
            print(f"[apply] No cookies — cannot apply to {job_id}", flush=True)
            await browser.close()
            return False

        page = await context.new_page()

        try:
            await page.goto(url, wait_until='networkidle', timeout=30000)

            # Dismiss cookie/consent banner before anything else
            for cookie_sel in [
                'button[action-type="ACCEPT"]',
                'button.artdeco-global-alert-action:first-child',
                'button[aria-label*="Accept" i]',
            ]:
                try:
                    btn = await page.query_selector(cookie_sel)
                    if btn and await btn.is_visible():
                        await btn.click()
                        print(f"[apply] Cookie banner dismissed", flush=True)
                        await asyncio.sleep(1.5)
                        break
                except Exception:
                    pass

            # Wait for job content to render
            try:
                await page.wait_for_selector(
                    '.jobs-unified-top-card__content--two-pane, '
                    '.job-details-jobs-unified-top-card__container, '
                    '.jobs-s-apply-button, .jobs-apply-button, '
                    'button[aria-label*="Apply" i]',
                    timeout=15000
                )
            except Exception:
                pass  # Continue anyway — different layout possible

            await page.evaluate("window.scrollBy(0, 300)")
            await _random_delay(1.5, 2.5)

            current_url = page.url
            page_title = await page.title()
            print(f"[apply] Landed: {current_url[:80]} | {page_title[:50]}", flush=True)

            if 'login' in current_url or 'authwall' in current_url or 'checkpoint' in current_url:
                print(f"[apply] Cookie expired — login redirect. Routing to manual.", flush=True)
                update_status(job_id, 'manual')
                await browser.close()
                return False

            if await _detect_captcha(page):
                print(f"[apply] CAPTCHA detected — routing to manual", flush=True)
                update_status(job_id, 'manual')
                await browser.close()
                return False

            # Find job container to scope button searches
            job_container = None
            for container_sel in [
                '.jobs-unified-top-card',
                '.job-details-jobs-unified-top-card__container',
                '.jobs-details__main-content',
                '.scaffold-layout__main',
            ]:
                job_container = await page.query_selector(container_sel)
                if job_container:
                    break
            search_root = job_container if job_container else page
            print(f"[apply] Job container: {'found' if job_container else 'not found — using page'}", flush=True)

            # ── Try Easy Apply ────────────────────────────────────────────
            easy_apply_btn = None
            for selector in [
                'button[aria-label*="Easy Apply" i]',
                'button.jobs-apply-button',
                '.jobs-apply-button',
                'button:has-text("Easy Apply")',
            ]:
                easy_apply_btn = await search_root.query_selector(selector)
                if easy_apply_btn and await easy_apply_btn.is_visible():
                    break
                easy_apply_btn = None

            if easy_apply_btn:
                print(f"[apply] Easy Apply found — proceeding", flush=True)
                await easy_apply_btn.click()
                await _random_delay(2.0, 3.5)

                step = 0
                while step < MAX_STEPS:
                    if await _detect_captcha(page):
                        print(f"[apply] CAPTCHA at step {step} — aborting", flush=True)
                        update_status(job_id, 'manual')
                        await browser.close()
                        return False

                    await _handle_easy_apply_step(page, step)

                    # Submit?
                    submit_btn = None
                    for sel in [
                        'button[aria-label*="Submit application" i]',
                        'button[aria-label*="Submit" i]',
                        'button:has-text("Submit application")',
                        'button:has-text("Submit")',
                    ]:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            submit_btn = btn
                            break

                    if submit_btn:
                        await submit_btn.click()
                        await _random_delay(2.0, 4.0)
                        print(f"[apply] Easy Apply submitted: {job['title']} @ {job['company']}", flush=True)
                        update_status(job_id, 'applied')
                        await browser.close()
                        return True

                    # Next step?
                    next_btn = None
                    for sel in [
                        'button[aria-label*="Continue to next step" i]',
                        'button[aria-label*="Next" i]',
                        'button[aria-label*="Review" i]',
                        'button:has-text("Next")',
                        'button:has-text("Continue")',
                        'button:has-text("Review")',
                    ]:
                        btn = await page.query_selector(sel)
                        if btn and await btn.is_visible():
                            next_btn = btn
                            break

                    if next_btn:
                        await next_btn.click()
                        await _random_delay(1.5, 3.0)
                        step += 1
                    else:
                        print(f"[apply] Stuck at step {step} — routing to manual", flush=True)
                        update_status(job_id, 'manual')
                        await browser.close()
                        return False

                print(f"[apply] Too many steps — routing to manual", flush=True)
                update_status(job_id, 'manual')
                await browser.close()
                return False

            # ── No Easy Apply → try external Apply button ─────────────────
            print(f"[apply] No Easy Apply found — looking for external Apply button", flush=True)

            # Log buttons from job container for diagnosis
            try:
                log_root = job_container if job_container else page
                all_btns = await log_root.query_selector_all('button')
                print(f"[apply] Buttons in job container: {len(all_btns)}", flush=True)
                for b in all_btns[:30]:
                    try:
                        lbl = await b.get_attribute('aria-label') or ''
                        cls = await b.get_attribute('class') or ''
                        txt = (await b.inner_text()).strip()[:30]
                        print(f"[apply] BTN cls={cls[:40]!r} lbl={lbl[:60]!r} txt={txt!r}", flush=True)
                    except Exception:
                        pass
            except Exception:
                pass

            external_url = None

            for selector in [
                'button[aria-label*="company website" i]',
                'a[aria-label*="company website" i]',
                'button.jobs-apply-button',
                'a.jobs-apply-button',
                '.jobs-apply-button',
                'button[data-tracking-control-name*="apply" i]',
                'a[data-tracking-control-name*="apply" i]',
                'button[aria-label*="Apply" i]',
                'a[aria-label*="Apply" i]',
                'a:has-text("Apply on company website")',
                'button:has-text("Apply on company website")',
                'a:has-text("Apply")',
                'button:has-text("Apply")',
            ]:
                btn = await search_root.query_selector(selector)
                if btn:
                    href = await btn.get_attribute('href')
                    if href and href.startswith('http'):
                        external_url = href
                        print(f"[apply] External URL via href: {external_url[:80]}", flush=True)
                        break
                    # No href — click and see where we land
                    try:
                        async with context.expect_page(timeout=8000) as new_page_info:
                            await btn.click()
                        new_page = await new_page_info.value
                        await new_page.wait_for_load_state('domcontentloaded', timeout=15000)
                        external_url = new_page.url
                        print(f"[apply] External URL via new tab: {external_url[:80]}", flush=True)
                        success = await _apply_external_portal(new_page, job_id, external_url)
                        await new_page.close()
                        if success:
                            update_status(job_id, 'applied')
                        else:
                            update_status(job_id, 'manual')
                        await browser.close()
                        return success
                    except Exception:
                        # Didn't open new tab — check if page navigated
                        await _random_delay(1.5, 2.5)
                        if page.url != url:
                            external_url = page.url
                            print(f"[apply] Navigated to: {external_url[:80]}", flush=True)
                        break

            if not external_url:
                print(f"[apply] No apply button found for {job_id} — routing to manual", flush=True)
                update_status(job_id, 'manual')
                await browser.close()
                return False

            new_page = await context.new_page()
            success = await _apply_external_portal(new_page, job_id, external_url)
            await new_page.close()

            if success:
                update_status(job_id, 'applied')
            else:
                update_status(job_id, 'manual')

            await browser.close()
            return success

        except PlaywrightTimeout:
            print(f"[apply] Timeout for {job_id} — routing to manual", flush=True)
            update_status(job_id, 'manual')
        except Exception as e:
            print(f"[apply] Error for {job_id}: {e} — routing to manual", flush=True)
            update_status(job_id, 'manual')

        await browser.close()
    return False


def apply_sync(job: dict) -> bool:
    """Synchronous wrapper for use in threads."""
    import traceback
    print(f"[apply] apply_sync called for {job.get('id')} — playwright={_PLAYWRIGHT_AVAILABLE}", flush=True)
    try:
        result = asyncio.run(apply_to_job(job))
        print(f"[apply] apply_sync finished: result={result}", flush=True)
        return result
    except Exception as e:
        print(f"[apply] apply_sync EXCEPTION: {e}", flush=True)
        traceback.print_exc()
        return False
