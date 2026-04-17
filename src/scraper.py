"""
LinkedIn job scraper.
- Job search: HTTP requests with li_at cookie (reliable, no bot detection)
- Easy Apply: Playwright browser (only when applying, triggered separately)
Searches for Director/Sr Manager/Manager roles in Consumer Insights, Analytics,
Marketing, Commercial, Shopper, and Strategy in Austria or remote.
"""
from __future__ import annotations

import asyncio
import json
import os
import random
import re
import time
from datetime import datetime
from urllib.parse import urlencode

import requests
from bs4 import BeautifulSoup

try:
    from playwright.async_api import async_playwright, Page, BrowserContext
    _PLAYWRIGHT_AVAILABLE = True
except ImportError:
    _PLAYWRIGHT_AVAILABLE = False

COOKIES_PATH = os.path.join(os.path.dirname(__file__), '..', 'data', 'cookies', 'linkedin_cookies.json')

# f_TPR values: r86400 = past 24h, r604800 = past week
TIME_FILTER_FIRST_RUN = "r604800"   # past week  — used on very first run to catch up
TIME_FILTER_NORMAL    = "r86400"    # past 24h   — used on every subsequent hourly run

# Search configs for LinkedIn guest API.
# Note: guest API does not support f_WT (remote filter) reliably — removed.
# Scorer/filter will handle location relevance after fetching results.

SEARCH_CONFIGS = [

    # ══════════════════════════════════════════════════════════════════════
    # AUSTRIA — BROAD SWEEPS (5 pages each = 125 results)
    # These are the most critical — catch ANY senior role regardless of area
    # pages=5 overrides the default 3
    # ══════════════════════════════════════════════════════════════════════
    {"keywords": "Director",                            "location": "Austria", "remote": False, "pages": 5},
    {"keywords": "Head of",                             "location": "Austria", "remote": False, "pages": 5},
    {"keywords": "Senior Manager",                      "location": "Austria", "remote": False, "pages": 5},
    {"keywords": "Senior Director",                     "location": "Austria", "remote": False, "pages": 5},
    {"keywords": "Lead",                                "location": "Austria", "remote": False, "pages": 4},
    {"keywords": "Partner",                             "location": "Austria", "remote": False, "pages": 3},

    # ══════════════════════════════════════════════════════════════════════
    # AUSTRIA — BY AREA (categories the broad sweeps may miss)
    # ══════════════════════════════════════════════════════════════════════
    {"keywords": "Consumer Insights",                   "location": "Austria", "remote": False},
    {"keywords": "Analytics Manager Director",          "location": "Austria", "remote": False},
    {"keywords": "Commercial Strategy",                 "location": "Austria", "remote": False},
    {"keywords": "Business Transformation",             "location": "Austria", "remote": False},
    {"keywords": "Business Development Manager",        "location": "Austria", "remote": False},
    {"keywords": "Operational Excellence",              "location": "Austria", "remote": False},
    {"keywords": "Innovation",                          "location": "Austria", "remote": False},
    # Missing categories found in audit:
    {"keywords": "Sales Manager Director",              "location": "Austria", "remote": False},
    {"keywords": "Portfolio Manager",                   "location": "Austria", "remote": False},
    {"keywords": "Sustainability Director Lead",        "location": "Austria", "remote": False},
    {"keywords": "Finance Manager Director",            "location": "Austria", "remote": False},
    {"keywords": "Account Director Manager",            "location": "Austria", "remote": False},
    {"keywords": "Global Manager",                      "location": "Austria", "remote": False},
    {"keywords": "Category Development Manager",        "location": "Austria", "remote": False},
    {"keywords": "Category Manager",                    "location": "Austria", "remote": False},
    {"keywords": "E-Commerce Manager Director",         "location": "Austria", "remote": False},
    {"keywords": "International Manager",               "location": "Austria", "remote": False},
    {"keywords": "Manager",                              "location": "Austria", "remote": False, "pages": 4},
    {"keywords": "Customer Insights",                   "location": "Austria", "remote": False},
    {"keywords": "Shopper Marketing Manager",           "location": "Austria", "remote": False},
    {"keywords": "Media Manager Director",              "location": "Austria", "remote": False},
    {"keywords": "Customer Engagement Manager",         "location": "Austria", "remote": False},
    {"keywords": "Trade Marketing Manager",             "location": "Austria", "remote": False},

    # ══════════════════════════════════════════════════════════════════════
    # EUROPE REMOTE — BROAD SWEEPS
    # ══════════════════════════════════════════════════════════════════════
    {"keywords": "Director Consumer Insights",          "location": "Europe",  "remote": True},
    {"keywords": "Director Analytics",                  "location": "Europe",  "remote": True},
    {"keywords": "Head of Strategy",                    "location": "Europe",  "remote": True},
    {"keywords": "Head of Insights",                    "location": "Europe",  "remote": True},
    {"keywords": "Head of Commercial",                  "location": "Europe",  "remote": True},
    {"keywords": "Director Strategy FMCG",              "location": "Europe",  "remote": True},
    {"keywords": "Senior Director Insights",            "location": "Europe",  "remote": True},

    # ══════════════════════════════════════════════════════════════════════
    # EUROPE — BY AREA
    # ══════════════════════════════════════════════════════════════════════
    {"keywords": "Head of Consumer Insights",           "location": "Europe",  "remote": False},
    {"keywords": "Director Marketing Analytics",        "location": "Europe",  "remote": False},
    {"keywords": "Head of Commercial Strategy FMCG",   "location": "Europe",  "remote": False},
    {"keywords": "Commercial Director FMCG",            "location": "Europe",  "remote": False},
    {"keywords": "Business Transformation Director",    "location": "Europe",  "remote": False},
    {"keywords": "Shopper Insights Director",           "location": "Europe",  "remote": False},
    {"keywords": "Consumer Insights Manager",           "location": "Europe",  "remote": False},
    {"keywords": "Business Development Manager",        "location": "Europe",  "remote": True},
    {"keywords": "Operational Innovation",              "location": "Europe",  "remote": True},
    {"keywords": "Business Transformation Partner",     "location": "Europe",  "remote": True},
    {"keywords": "Innovation Director",                 "location": "Europe",  "remote": True},
    {"keywords": "Shopper Insights Director Manager",   "location": "Europe",  "remote": True},
    {"keywords": "Category Analytics Director",         "location": "Europe",  "remote": True},
    {"keywords": "Shopper Marketing Director",          "location": "Europe",  "remote": True},
    {"keywords": "Media Strategy Director",             "location": "Europe",  "remote": True},
    {"keywords": "Customer Engagement Director",        "location": "Europe",  "remote": True},
    {"keywords": "Trade Marketing Director",            "location": "Europe",  "remote": True},
]

BASE_URL = "https://www.linkedin.com/jobs/search/"
GUEST_API_URL = "https://www.linkedin.com/jobs-guest/jobs/api/seeMoreJobPostings/search"

# Track whether this is the first run (used to select time filter)
_SEEN_IDS_FILE = os.path.join(os.path.dirname(__file__), '..', 'data', 'seen_ids.json')


def _load_seen_ids() -> set:
    if os.path.exists(_SEEN_IDS_FILE):
        with open(_SEEN_IDS_FILE) as f:
            return set(json.load(f))
    return set()


def _save_seen_ids(ids: set) -> None:
    os.makedirs(os.path.dirname(_SEEN_IDS_FILE), exist_ok=True)
    with open(_SEEN_IDS_FILE, 'w') as f:
        json.dump(list(ids), f)


def _is_first_run() -> bool:
    return not os.path.exists(_SEEN_IDS_FILE)


def _build_url(keywords: str, location: str, remote: bool, time_filter: str, start: int = 0) -> str:
    """Build LinkedIn guest jobs API URL (no auth required, returns parseable HTML)."""
    params = {
        "keywords": keywords,
        "location": location,
        "f_TPR": time_filter,
        "start": start,
    }
    if remote:
        params["f_WT"] = "2"
    return GUEST_API_URL + "?" + urlencode(params)


async def _random_delay(min_s: float = 3.0, max_s: float = 8.0) -> None:
    await asyncio.sleep(random.uniform(min_s, max_s))


async def _load_cookies(context: BrowserContext) -> bool:
    """Load LinkedIn session cookies. Returns True if cookies file exists."""
    if not os.path.exists(COOKIES_PATH):
        print(f"[scraper] Cookie file not found: {COOKIES_PATH}")
        print("[scraper] Please export your LinkedIn cookies and save to that path.")
        return False
    with open(COOKIES_PATH, 'r') as f:
        cookies = json.load(f)
    # Ensure domain is set correctly for linkedin.com cookies
    for cookie in cookies:
        if 'domain' not in cookie or not cookie['domain']:
            cookie['domain'] = '.linkedin.com'
    await context.add_cookies(cookies)
    return True


async def _is_logged_in(page: Page) -> bool:
    """Check if we're still authenticated (no redirect to login page)."""
    return 'linkedin.com/login' not in page.url and 'linkedin.com/authwall' not in page.url


async def _extract_job_cards(page: Page) -> list[dict]:
    """Extract job cards from current search results page."""
    jobs = []
    await page.wait_for_selector('.jobs-search__results-list, .scaffold-layout__list', timeout=15000)

    cards = await page.query_selector_all('.jobs-search__results-list li, .job-card-container')

    for card in cards:
        try:
            job_id = await card.get_attribute('data-job-id') or ''
            if not job_id:
                # Try to get from nested element
                link = await card.query_selector('a[href*="/jobs/view/"]')
                if link:
                    href = await link.get_attribute('href') or ''
                    match = re.search(r'/jobs/view/(\d+)', href)
                    job_id = match.group(1) if match else ''

            if not job_id:
                continue

            title_el = await card.query_selector('.job-card-list__title, .jobs-unified-top-card__job-title, h3')
            title = (await title_el.inner_text()).strip() if title_el else ''

            company_el = await card.query_selector('.job-card-container__company-name, .job-card-list__company-name, h4')
            company = (await company_el.inner_text()).strip() if company_el else ''

            location_el = await card.query_selector('.job-card-container__metadata-item, .job-card-list__metadata')
            location = (await location_el.inner_text()).strip() if location_el else ''

            url = f"https://www.linkedin.com/jobs/view/{job_id}/"

            if title and company and job_id:
                jobs.append({
                    'id': job_id,
                    'title': title,
                    'company': company,
                    'location': location,
                    'url': url,
                    'description': '',
                    'found_at': datetime.utcnow().isoformat(),
                })
        except Exception as e:
            print(f"[scraper] Error parsing card: {e}")
            continue

    return jobs


async def _get_job_description(page: Page, url: str) -> str:
    """Navigate to job detail page and extract full description."""
    try:
        await page.goto(url, wait_until='domcontentloaded', timeout=20000)
        await _random_delay(2.0, 5.0)

        # Try multiple selectors for description
        for selector in [
            '.jobs-description__content',
            '.jobs-box__html-content',
            '#job-details',
            '.description__text',
        ]:
            el = await page.query_selector(selector)
            if el:
                return (await el.inner_text()).strip()
    except Exception as e:
        print(f"[scraper] Error getting description for {url}: {e}")
    return ''


def _make_session(cookies: list[dict]) -> requests.Session:
    """Create requests session with all LinkedIn cookies and browser-like headers."""
    session = requests.Session()
    for c in cookies:
        domain = c.get('domain', '.linkedin.com')
        # requests cookiejar needs domain without leading dot for hostOnly cookies
        session.cookies.set(c['name'], c['value'], domain=domain, path=c.get('path', '/'))
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,image/webp,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
        'Accept-Encoding': 'gzip, deflate, br',
        'Referer': 'https://www.linkedin.com/',
        'sec-ch-ua': '"Chromium";v="124", "Google Chrome";v="124"',
        'sec-ch-ua-mobile': '?0',
        'sec-ch-ua-platform': '"Windows"',
        'Sec-Fetch-Dest': 'document',
        'Sec-Fetch-Mode': 'navigate',
        'Sec-Fetch-Site': 'same-origin',
        'Upgrade-Insecure-Requests': '1',
    })
    return session


def _parse_job_cards_html(html: str) -> list[dict]:
    """Parse job cards from LinkedIn guest API HTML response."""
    soup = BeautifulSoup(html, 'html.parser')
    jobs = []

    for card in soup.select('li'):
        try:
            # Job ID from link href — handles both:
            # www.linkedin.com/jobs/view/1234567890 (ID directly after /view/)
            # at.linkedin.com/jobs/view/job-title-1234567890?... (ID at end of slug)
            link = card.select_one('a[href*="/jobs/view/"]')
            if not link:
                continue
            href = link.get('href', '')
            match = re.search(r'/jobs/view/(\d+)', href) or re.search(r'-(\d{7,})(?:\?|$)', href)
            job_id = match.group(1) if match else ''
            if not job_id:
                continue

            title_el = card.select_one('.base-search-card__title')
            title = title_el.get_text(strip=True) if title_el else ''

            company_el = card.select_one('.base-search-card__subtitle')
            company = company_el.get_text(strip=True) if company_el else ''

            location_el = card.select_one('.job-search-card__location')
            location = location_el.get_text(strip=True) if location_el else ''

            if title and company and job_id:
                jobs.append({
                    'id': job_id,
                    'title': title,
                    'company': company,
                    'location': location,
                    'url': f'https://www.linkedin.com/jobs/view/{job_id}/',
                    'description': '',
                    'found_at': datetime.utcnow().isoformat(),
                })
        except Exception:
            continue

    return jobs


_CLOSED_SIGNALS = [
    'no longer accepting applications',
    'ya no se aceptan solicitudes',
    'bewerbungen werden nicht mehr',
    'cette offre n\'accepte plus',
    'closed for applications',
    'application deadline has passed',
]


def _get_job_description_http(session: requests.Session, url: str) -> str:
    """
    Fetch job description via HTTP request.
    Returns '__CLOSED__' sentinel if job is no longer accepting applications.
    """
    try:
        time.sleep(random.uniform(2.0, 5.0))
        resp = session.get(url, timeout=15)
        if resp.status_code != 200:
            return ''
        soup = BeautifulSoup(resp.text, 'html.parser')

        # Check for "no longer accepting applications" before parsing description
        page_text_lower = soup.get_text(separator=' ').lower()
        if any(sig in page_text_lower for sig in _CLOSED_SIGNALS):
            return '__CLOSED__'

        for sel in ['.description__text', '.jobs-description__content', '#job-details', '.show-more-less-html__markup']:
            el = soup.select_one(sel)
            if el:
                return el.get_text(separator='\n', strip=True)
    except Exception as e:
        print(f"[scraper] Error getting description: {e}")
    return ''


async def scrape_jobs(notify_login_error=None) -> list[dict]:
    """
    Main scraping function. Returns list of NEW job dicts with descriptions.
    Uses HTTP requests (not Playwright) for job search — more reliable.
    - First ever run: searches past 7 days to catch up.
    - All subsequent runs: searches past 24 hours only.
    - Deduplicates against seen_ids.json — never returns a job seen before.
    """
    first_run = _is_first_run()
    time_filter = TIME_FILTER_FIRST_RUN if first_run else TIME_FILTER_NORMAL
    print(f"[scraper] Time filter: {'past 7 days (first run)' if first_run else 'past 24 hours'}")

    # Load cookie from file
    if not os.path.exists(COOKIES_PATH):
        print(f"[scraper] Cookie file not found: {COOKIES_PATH}")
        if notify_login_error:
            notify_login_error("Cookie file not found. Please re-export LinkedIn cookies.")
        return []

    with open(COOKIES_PATH) as f:
        cookies = json.load(f)
    li_at = next((c['value'] for c in cookies if c['name'] == 'li_at'), '')
    if not li_at:
        print("[scraper] li_at cookie not found in cookie file.")
        if notify_login_error:
            notify_login_error("li_at cookie missing. Please re-export LinkedIn cookies.")
        return []

    # Guest API search — no auth needed for searching
    # li_at is still kept in cookies file for Easy Apply (Playwright-based)
    session = requests.Session()
    session.headers.update({
        'User-Agent': (
            'Mozilla/5.0 (Windows NT 10.0; Win64; x64) '
            'AppleWebKit/537.36 (KHTML, like Gecko) '
            'Chrome/124.0.0.0 Safari/537.36'
        ),
        'Accept': 'text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8',
        'Accept-Language': 'en-US,en;q=0.9',
    })
    print("[scraper] Using LinkedIn guest jobs API.")

    # Load all job IDs ever seen
    seen_ids = _load_seen_ids()
    new_ids_this_run: set = set()
    all_jobs = []

    print(f"[scraper] Running {len(SEARCH_CONFIGS)} searches...")

    for config in SEARCH_CONFIGS:
        keywords = config['keywords']
        location = config['location']
        remote = config['remote']

        max_pages = config.get('pages', 3)
        print(f"[scraper] '{keywords}' / {location} / remote={remote} / pages={max_pages}")

        for page_num in range(max_pages):
            start = page_num * 25
            url = _build_url(keywords, location, remote, time_filter, start)

            try:
                time.sleep(random.uniform(3.0, 7.0))
                resp = session.get(url, timeout=20)

                if resp.status_code != 200:
                    print(f"[scraper]   HTTP {resp.status_code} — skipping")
                    break

                cards = _parse_job_cards_html(resp.text)
                if not cards:
                    break

                fresh = [
                    c for c in cards
                    if c['id'] not in seen_ids and c['id'] not in new_ids_this_run
                ]
                new_ids_this_run.update(c['id'] for c in fresh)

                print(f"[scraper]   Page {page_num + 1}: {len(cards)} found, {len(fresh)} new")

                open_jobs = []
                for job in fresh:
                    desc = _get_job_description_http(session, job['url'])
                    if desc == '__CLOSED__':
                        print(f"[scraper]   Closed (no longer accepting): {job['title']} @ {job['company']}")
                        continue
                    job['description'] = desc
                    open_jobs.append(job)

                all_jobs.extend(open_jobs)

                if len(cards) < 10:
                    break

                time.sleep(random.uniform(10.0, 20.0))

            except Exception as e:
                print(f"[scraper] Error: {e}")
                break

        time.sleep(random.uniform(5.0, 10.0))

    _save_seen_ids(seen_ids | new_ids_this_run)
    print(f"[scraper] Done. New jobs: {len(all_jobs)} | Total seen ever: {len(seen_ids | new_ids_this_run)}")
    return all_jobs


async def test_auth() -> bool:
    """Quick test to verify LinkedIn cookie authentication works."""
    if not _PLAYWRIGHT_AVAILABLE:
        print("[test_auth] Playwright not installed — skipping browser auth test.")
        return False
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(headless=False)
        context = await browser.new_context()
        loaded = await _load_cookies(context)
        if not loaded:
            print("[test_auth] No cookies file found.")
            await browser.close()
            return False
        page = await context.new_page()
        await page.goto('https://www.linkedin.com/feed/', wait_until='domcontentloaded')
        await asyncio.sleep(3)
        logged_in = await _is_logged_in(page)
        print(f"[test_auth] Logged in: {logged_in} | URL: {page.url}")
        await browser.close()
        return logged_in


if __name__ == '__main__':
    # Run test
    result = asyncio.run(test_auth())
    print(f"Auth test: {'PASSED' if result else 'FAILED'}")
