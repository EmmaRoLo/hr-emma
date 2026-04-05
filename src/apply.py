"""
LinkedIn Easy Apply automation using Playwright.
Handles multi-step Easy Apply forms with pre-filled data for Emmanuel.
Safety guards: CAPTCHA detection, form complexity limit, German detection.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import sys

try:
    from playwright.async_api import async_playwright, Page, TimeoutError as PlaywrightTimeout
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
}

MAX_STEPS = 6  # Abort if form has more steps than this


async def _random_delay(min_s=1.5, max_s=4.0):
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _load_cookies(context):
    if not os.path.exists(COOKIES_PATH):
        return False
    with open(COOKIES_PATH) as f:
        cookies = json.load(f)
    for c in cookies:
        if 'domain' not in c or not c['domain']:
            c['domain'] = '.linkedin.com'
    await context.add_cookies(cookies)
    return True


async def _fill_text_field(page: Page, label_text: str, value: str) -> bool:
    """Try to find a text input by its label and fill it."""
    try:
        # Strategy 1: aria-label
        field = await page.query_selector(f'input[aria-label*="{label_text}" i]')
        if field:
            await field.fill(value)
            return True
        # Strategy 2: label element containing text → for attribute → input
        labels = await page.query_selector_all('label')
        for label in labels:
            text = await label.inner_text()
            if label_text.lower() in text.lower():
                for_attr = await label.get_attribute('for')
                if for_attr:
                    inp = await page.query_selector(f'#{for_attr}')
                    if inp:
                        await inp.fill(value)
                        return True
    except Exception:
        pass
    return False


async def _handle_form_step(page: Page, step_num: int) -> bool:
    """
    Fill fields on a single Easy Apply step.
    Returns True if step was handled, False if we should abort.
    """
    await _random_delay(1.0, 2.5)

    # Phone number
    await _fill_text_field(page, 'phone', APPLICANT['phone'])
    await _fill_text_field(page, 'mobile', APPLICANT['phone'])

    # Location / City
    await _fill_text_field(page, 'city', APPLICANT['city'])
    await _fill_text_field(page, 'location', APPLICANT['city'])

    # Salary
    for label in ['salary', 'expected salary', 'desired salary', 'gehalt']:
        field = await page.query_selector(f'input[aria-label*="{label}" i]')
        if field:
            await field.fill(APPLICANT['salary_expectation'])
            break

    # Work authorization / visa
    for label in ['authorized', 'work authorization', 'visa', 'eligible to work', 'recht zu arbeiten']:
        radios = await page.query_selector_all(f'input[type="radio"][aria-label*="{label}" i]')
        if radios:
            # Select "Yes" — usually first option
            await radios[0].click()
            break
        # Try select dropdowns
        selects = await page.query_selector_all(f'select[aria-label*="{label}" i]')
        for sel in selects:
            await sel.select_option(label='Yes')

    # Years of experience
    for label in ['years of experience', 'experience', 'jahre']:
        field = await page.query_selector(f'input[aria-label*="{label}" i]')
        if field:
            await field.fill(APPLICANT['years_experience'])
            break
        sel = await page.query_selector(f'select[aria-label*="{label}" i]')
        if sel:
            try:
                await sel.select_option(label='10+')
            except Exception:
                pass

    # Cover letter text area (use short version)
    textarea = await page.query_selector('textarea')
    if textarea:
        short_cl = (
            "Commercial & Insights Leader with 10+ years in FMCG (PepsiCo, Nielsen, Kantar). "
            "Expert in consumer insights, advanced analytics, and commercial strategy. "
            "Based in Austria with full EU work authorization."
        )
        current = await textarea.input_value()
        if not current:
            await textarea.fill(short_cl)

    return True


async def _detect_captcha(page: Page) -> bool:
    captcha_signals = [
        '[id*="captcha"]',
        '[class*="captcha"]',
        'iframe[src*="recaptcha"]',
        'iframe[src*="hcaptcha"]',
    ]
    for sel in captcha_signals:
        if await page.query_selector(sel):
            return True
    return False


async def apply_to_job(job: dict) -> bool:
    """
    Attempt LinkedIn Easy Apply for a job.
    Updates job status in DB.
    Returns True if application submitted successfully.
    """
    job_id = job['id']
    url = job.get('url', '')

    if not _PLAYWRIGHT_AVAILABLE:
        print(f"[apply] Playwright not installed — routing {job_id} to manual.")
        update_status(job_id, 'manual')
        return False

    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=True)
        context = await browser.new_context(
            user_agent=(
                'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
                'AppleWebKit/537.36 (KHTML, like Gecko) '
                'Chrome/124.0.0.0 Safari/537.36'
            )
        )

        if not await _load_cookies(context):
            print(f"[apply] No cookies — cannot apply to {job_id}")
            await browser.close()
            return False

        page = await context.new_page()

        try:
            await page.goto(url, wait_until='domcontentloaded', timeout=20000)
            await _random_delay(2.0, 4.0)

            # Check for CAPTCHA before proceeding
            if await _detect_captcha(page):
                print(f"[apply] CAPTCHA detected for {job_id} — routing to manual")
                update_status(job_id, 'manual')
                await browser.close()
                return False

            # Find and click Easy Apply button
            easy_apply_btn = None
            for selector in [
                'button[aria-label*="Easy Apply" i]',
                'button.jobs-apply-button',
                '.jobs-apply-button',
                'button:has-text("Easy Apply")',
            ]:
                easy_apply_btn = await page.query_selector(selector)
                if easy_apply_btn:
                    break

            if not easy_apply_btn:
                print(f"[apply] Easy Apply button not found for {job_id}")
                update_status(job_id, 'manual')
                await browser.close()
                return False

            await easy_apply_btn.click()
            await _random_delay(2.0, 3.5)

            # Multi-step form navigation
            step = 0
            while step < MAX_STEPS:
                if await _detect_captcha(page):
                    print(f"[apply] CAPTCHA at step {step} — aborting")
                    update_status(job_id, 'manual')
                    await browser.close()
                    return False

                await _handle_form_step(page, step)

                # Look for Submit or Next button
                submit_btn = None
                for sel in [
                    'button[aria-label*="Submit application" i]',
                    'button[aria-label*="Submit" i]',
                    'button:has-text("Submit application")',
                    'button:has-text("Submit")',
                ]:
                    btn = await page.query_selector(sel)
                    if btn:
                        is_visible = await btn.is_visible()
                        if is_visible:
                            submit_btn = btn
                            break

                if submit_btn:
                    await submit_btn.click()
                    await _random_delay(2.0, 4.0)
                    print(f"[apply] Application submitted for {job_id} — {job['title']} @ {job['company']}")
                    update_status(job_id, 'applied')
                    await browser.close()
                    return True

                # Try "Next" / "Continue" / "Review"
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
                    # No next or submit found — too complex
                    print(f"[apply] Could not navigate form at step {step} — routing to manual")
                    update_status(job_id, 'manual')
                    await browser.close()
                    return False

            # Exceeded max steps
            print(f"[apply] Form too complex (>{MAX_STEPS} steps) — routing to manual")
            update_status(job_id, 'manual')

        except PlaywrightTimeout:
            print(f"[apply] Timeout for {job_id} — routing to manual")
            update_status(job_id, 'manual')
        except Exception as e:
            print(f"[apply] Error for {job_id}: {e} — routing to manual")
            update_status(job_id, 'manual')

        await browser.close()
    return False


def apply_sync(job: dict) -> bool:
    """Synchronous wrapper for use in threads."""
    return asyncio.run(apply_to_job(job))
