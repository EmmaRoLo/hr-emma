"""
Job filter and scorer for Emmanuel Rodriguez's search criteria.

Scoring (0-100) before zone multiplier:
  Title match     30pts  -- Director/Head=30, Sr Manager=22, Manager=15, Lead=12, other=8
  Area match      30pts  -- Insights/Analytics/Shopper=30, Commercial/Strategy/Transformation=27,
                            Marketing=22, other=8
  Location fit    20pts  -- Austria=20, Remote=18, Hybrid Austria=15, EU remote=12
  Company fit     10pts  -- Known FMCG/CPG/Retail/Consulting=10, other=5
  Seniority cues  10pts  -- Leadership signals in desc=10, Manager=7, no signal=3

Industry Zone multiplier applied AFTER base score:
  Zone 1 - Core        x1.00  (FMCG, CPG, Retail, Consumer Goods, Market Research)
  Zone 2 - Adjacent    x0.90  (Tech, Consulting, Finance/Banking, E-commerce, Media, Logistics)
  Zone 3 - Stretch     x0.75  (General Healthcare, Manufacturing, Insurance, Automotive, Government)
  Zone 4 - Excluded    x0.00  (Specialized Medical/Pharma R&D, Energy/Utilities, Mining,
                                Civil Engineering, Defense, Agriculture)

Hard-exclude before scoring:
  - Job written in German (langdetect)
  - Description contains German fluency requirement phrases
"""

import re

try:
    from langdetect import detect, DetectorFactory
    DetectorFactory.seed = 42
    LANGDETECT_AVAILABLE = True
except ImportError:
    LANGDETECT_AVAILABLE = False
    print("[filter] langdetect not installed -- German detection uses keyword method only.")


# ── HARD EXCLUDE: German language requirement ────────────────────────────────

GERMAN_REQUIREMENT_PHRASES = [
    r'deutsch\s+flie[sß]end',
    r'flie[sß]ende\s+deutschkenntnisse',
    r'muttersprache\s+deutsch',
    r'deutsch\s+als\s+muttersprache',
    r'deutschkenntnisse\s+erforderlich',
    r'german\s+fluent',
    r'fluent\s+(?:in\s+)?german',
    r'german\s+language\s+required',
    r'german\s+(?:is\s+)?(?:a\s+)?(?:must|required|mandatory)',
    r'german\s+speaking\s+required',
    r'proficiency\s+in\s+german\s+(?:is\s+)?required',
    r'c1\s+german', r'c2\s+german',
    r'native\s+german', r'german\s+native',
]
GERMAN_RE = [re.compile(p, re.IGNORECASE) for p in GERMAN_REQUIREMENT_PHRASES]


# ── INDUSTRY ZONES ───────────────────────────────────────────────────────────
# Each zone is a list of keywords checked against (title + company + description).
# First matching zone wins. If no zone matches -> Zone 2 (Adjacent) by default.

ZONE_1_CORE = [
    # FMCG / CPG brands
    'fmcg', 'cpg', 'consumer goods', 'consumer packaged',
    'unilever', 'nestle', 'nestlé', 'p&g', 'procter', 'gamble', 'reckitt',
    'henkel', 'beiersdorf', 'mondelez', 'kraft', 'heinz', 'coca-cola', 'pepsi',
    'pepsico', 'diageo', 'ab inbev', 'heineken', 'danone', 'ferrero', 'mars',
    'colgate', 'kimberly', 'loreal', "l'oreal", 'kao', 'haleon', 'red bull',
    'redbull', 'general mills', 'kellogg', 'campbell', 'conagra', 'lavazza',
    'illy', 'jde peets', 'bonduelle', 'iglo', 'reckitt benckiser',
    'unicharm', 'essity', 'energizer', 'spectrum brands',
    # Retail / Trade
    'retail', 'walmart', 'lidl', 'rewe', 'spar', 'metro', 'aldi', 'carrefour',
    'dm drogerie', 'billa', 'kaufland', 'hofer', 'merkur', 'interspar', 'edeka',
    'tesco', 'sainsbury', 'morrisons', 'waitrose', 'migros', 'coop',
    # Market Research
    'nielsen', 'kantar', 'iqvia', 'mintel', 'euromonitor', 'circana',
    'ipsos', 'gfk', 'iri', 'numerator', 'stackline',
    # Premium / Luxury Consumer
    'lvmh', 'richemont', 'estee lauder', 'shiseido', 'kering',
]

ZONE_2_ADJACENT = [
    # Management Consulting
    'mckinsey', 'bain', 'bcg', 'accenture', 'deloitte', 'oliver wyman',
    'kearney', 'pwc', 'ey ', 'ernst & young', 'capgemini', 'kpmg', 'roland berger',
    # Technology / SaaS / E-commerce
    'technology', 'software', 'saas', 'platform', 'digital', 'e-commerce',
    'ecommerce', 'marketplace', 'amazon', 'google', 'microsoft', 'meta',
    'salesforce', 'sap', 'oracle', 'adobe', 'databricks',
    # Finance / Banking / Insurance (non-specialized)
    'bank', 'finance', 'financial services', 'insurance', 'fintech',
    'investment', 'asset management', 'private equity',
    # Media / Entertainment / Sports
    'media', 'entertainment', 'publishing', 'advertising', 'agency',
    'sports', 'gaming', 'broadcast',
    # Logistics / Supply Chain
    'logistics', 'supply chain', 'transport', 'delivery', 'dhl', 'ups', 'fedex',
    # Telecoms
    'telecom', 'telecommunications', 'wireless', 'mobile operator',
    # General Consumer Services
    'hospitality', 'travel', 'tourism', 'airline', 'hotel',
]

ZONE_3_STRETCH = [
    # General Healthcare (non-pharma R&D)
    'healthcare', 'health care', 'hospital', 'clinic', 'medtech',
    'medical device', 'dental', 'wellness', 'nutrition supplement',
    # Manufacturing / Industrial
    'manufacturing', 'industrial', 'factory', 'plant', 'production',
    'machinery', 'equipment', 'tools',
    # Automotive
    'automotive', 'automobile', 'vehicle', 'ev ', 'electric vehicle',
    'car manufacturer', 'volkswagen', 'bmw', 'mercedes', 'audi', 'stellantis',
    # Real Estate / Construction
    'real estate', 'construction', 'property', 'infrastructure',
    # Government / Public Sector
    'government', 'public sector', 'municipality', 'ministry', 'ngo',
    'non-profit', 'nonprofit', 'charity', 'foundation',
    # Education
    'university', 'education', 'academic', 'school', 'learning',
]

ZONE_4_EXCLUDED = [
    # Specialized Pharma / Biotech R&D
    'pharmaceutical', 'pharma', 'biotech', 'biotechnology', 'clinical trial',
    'drug discovery', 'oncology', 'genomics', 'biopharma', 'medtronic',
    'novartis', 'roche', 'pfizer', 'astrazeneca', 'sanofi', 'bayer', 'boehringer',
    'merck', 'abbvie', 'gilead', 'biogen',
    # Energy / Utilities / Oil & Gas
    'energy', 'utilities', 'electricity', 'power generation', 'oil', 'gas',
    'petroleum', 'renewables', 'solar', 'wind energy', 'nuclear',
    'shell', 'bp ', 'exxon', 'total energies', 'engie', 'verbund',
    # Mining / Raw Materials
    'mining', 'minerals', 'metals', 'steel', 'aluminum', 'iron ore',
    # Civil / Structural Engineering
    'civil engineering', 'structural engineering', 'geotechnical',
    # Defense / Aerospace
    'defense', 'defence', 'military', 'aerospace', 'airforce', 'navy',
    'weapons', 'armament',
    # Agriculture
    'agriculture', 'farming', 'crop', 'fertilizer', 'pesticide', 'agribusiness',
]

# Zone labels for display
ZONE_LABELS = {1: 'Core', 2: 'Adjacent', 3: 'Stretch', 4: 'Out of scope'}

# Cross matrix: ZONE_TIER_MATRIX[zone][tier] = (multiplier, class_label)
# Zone 4 always = 0 regardless of tier
ZONE_TIER_MATRIX = {
    #        Tier 1 (Strategy/Insights/Analytics)  Tier 2 (Commercial/Transformation)  Tier 3 (Operations/Marketing)
    1: {1: (1.00, 'A - Prime'),    2: (0.95, 'B - Strong'),  3: (0.85, 'C - Good')  },
    2: {1: (0.90, 'B - Strong'),   2: (0.80, 'C - Good'),    3: (0.65, 'D - Weak')  },
    3: {1: (0.75, 'C - Good'),     2: (0.60, 'D - Weak'),    3: (0.00, 'E - Skip')  },
    4: {1: (0.00, 'Skip'),         2: (0.00, 'Skip'),         3: (0.00, 'Skip')      },
}


# ── TITLE / AREA / LOCATION / SENIORITY KEYWORDS ────────────────────────────

TITLE_DIRECTOR_KW   = ['director', 'head of', 'vp ', 'vice president', 'chief', 'cmo', 'cco', 'cso']
TITLE_SR_MANAGER_KW = ['senior manager', 'sr manager', 'sr. manager', 'lead manager']
TITLE_MANAGER_KW    = ['manager', 'lead', 'principal']

# Tier 1 — Core expertise: Strategy, Market Insights, Consumer Insights, Analytics, Shopper
# These are Emmanuel's deepest skills — 10 years of direct experience
AREA_TIER1 = [
    # Strategy
    'strategic planning', 'strategy director', 'head of strategy',
    'business strategy', 'go-to-market strategy', 'revenue strategy', 'growth strategy',
    # Market & Consumer Insights
    'consumer insights', 'market insights', 'market & insights', 'market intelligence',
    'shopper insights', 'shopper analytics', 'category insights', 'category analytics',
    'market research', 'panel data', 'consumer research',
    # Analytics
    'analytics', 'data analytics', 'advanced analytics', 'business intelligence',
    'category management', 'performance analytics',
]

# Tier 2 — Strong fit: Commercial, Transformation
# Current role territory — solid match, slightly less depth than Tier 1
AREA_TIER2 = [
    # Commercial
    'commercial strategy', 'commercial excellence', 'commercial director',
    'commercial insights', 'commercial analytics', 'commercial lead',
    'commercial transformation', 'commercial operations', 'commercial manager',
    # Transformation
    'business transformation', 'transformation director', 'transformation lead',
    'transformation program', 'operating model', 'capability building',
    'organisational transformation', 'organizational transformation',
]

# Tier 3 — Acceptable: Operations, Marketing, Trade
# Transferable skills but not primary expertise
AREA_TIER3 = [
    # Operations
    'operations director', 'operational excellence', 'operations manager',
    'revenue operations', 'sales operations',
    # Marketing & Trade
    'marketing director', 'marketing manager', 'brand strategy',
    'trade marketing', 'shopper marketing', 'growth marketing',
    'campaign management', 'market positioning', 'marketing',
]

KNOWN_FMCG_COMPANIES = set(ZONE_1_CORE)

SENIORITY_CUE_KW = [
    'leadership', 'head of', 'senior', 'principal', 'lead', 'director',
    'cross-functional', 'c-suite', 'executive', 'vp', 'global', 'regional',
    'p&l', 'budget', 'stakeholder', 'board',
]


# ── HELPER FUNCTIONS ─────────────────────────────────────────────────────────

def _requires_german(text: str) -> bool:
    return any(p.search(text) for p in GERMAN_RE)


def _is_german_language(text: str) -> bool:
    if not LANGDETECT_AVAILABLE or not text or len(text) < 50:
        return False
    try:
        return detect(text[:2000]) == 'de'
    except Exception:
        return False


def _detect_zone(title: str, company: str, description: str) -> int:
    """
    Returns 1, 2, 3, or 4.
    Checks Zone 4 first (hard excludes), then Zone 1, then Zone 2, then Zone 3.
    Default if nothing matches: Zone 2 (Adjacent) -- gives benefit of the doubt.
    """
    text = (title + ' ' + company + ' ' + description[:1500]).lower()

    # Zone 4 check first -- hard out
    for kw in ZONE_4_EXCLUDED:
        if kw in text:
            return 4

    # Zone 1 -- core sweet spot
    for kw in ZONE_1_CORE:
        if kw in text:
            return 1

    # Zone 3 -- stretch (check before 2 because some overlap)
    for kw in ZONE_3_STRETCH:
        if kw in text:
            return 3

    # Zone 2 -- adjacent / default
    return 2


def _score_title(title: str) -> int:
    t = title.lower()
    for kw in TITLE_DIRECTOR_KW:
        if kw in t:
            return 30
    for kw in TITLE_SR_MANAGER_KW:
        if kw in t:
            return 22
    for kw in TITLE_MANAGER_KW:
        if kw in t:
            return 15
    return 8


def _detect_area_tier(title: str, description: str) -> int:
    """Returns 1, 2, or 3. Title match takes priority over description match."""
    tl = title.lower()
    dl = description.lower()
    for kw in AREA_TIER1:
        if kw in tl: return 1
    for kw in AREA_TIER2:
        if kw in tl: return 2
    for kw in AREA_TIER3:
        if kw in tl: return 3
    for kw in AREA_TIER1:
        if kw in dl: return 1
    for kw in AREA_TIER2:
        if kw in dl: return 2
    for kw in AREA_TIER3:
        if kw in dl: return 3
    return 3  # default to Tier 3 if no match — still gets scored, just lower


def _score_area(tier: int) -> int:
    """Convert tier to base area points."""
    return {1: 30, 2: 27, 3: 22}.get(tier, 22)


AUSTRIA_KW = ['austria', 'wien', 'vienna', 'graz', 'salzburg', 'linz', 'innsbruck', 'klagenfurt']
REMOTE_KW  = ['remote', 'work from home', 'wfh', 'anywhere', 'fully remote', 'home office']
HYBRID_KW  = ['hybrid']

# Countries/regions outside Austria where Emmanuel CANNOT work on-site
NON_AUSTRIA_KW = [
    'united kingdom', ' uk ', 'england', 'london', 'manchester', 'birmingham',
    'germany', 'berlin', 'munich', 'münchen', 'frankfurt', 'hamburg',
    'france', 'paris', 'netherlands', 'amsterdam', 'spain', 'madrid', 'barcelona',
    'italy', 'milan', 'rome', 'switzerland', 'zurich', 'zürich', 'geneva',
    'poland', 'warsaw', 'czech', 'prague', 'hungary', 'budapest',
    'sweden', 'stockholm', 'denmark', 'copenhagen', 'norway', 'oslo',
    'finland', 'helsinki', 'belgium', 'brussels', 'portugal', 'lisbon',
    'ireland', 'dublin', 'romania', 'bucharest', 'croatia', 'slovakia',
]


HYBRID_SIGNALS = [
    'hybrid', 'days in office', 'days in london', 'days a week in',
    'days per week in', 'on-site days', 'office days',
]

FULLY_REMOTE_KW = ['fully remote', 'fully-remote', '100% remote', 'remote only',
                   'remote position', 'remote role', 'remote job', 'remote work',
                   'work from anywhere', 'anywhere in', 'location: remote',
                   'remote (', '(remote)', 'remote –', 'remote —']


def _is_location_eligible(location: str, description: str) -> bool:
    """
    Hard location filter:
    - Austria (onsite, hybrid, remote)  → eligible
    - Rest of EU/world: FULLY remote only (no hybrid, no WFH partial)
    """
    loc  = location.lower()
    desc = description[:800].lower()
    combined = loc + ' ' + desc

    is_austria = any(k in combined for k in AUSTRIA_KW)

    # Austria: all work modes allowed
    if is_austria:
        return True

    # Non-Austria: reject if hybrid signals found
    is_hybrid = any(k in combined for k in HYBRID_SIGNALS)
    if is_hybrid:
        return False

    # Non-Austria: only allow if explicitly FULLY remote
    is_fully_remote = any(k in combined for k in FULLY_REMOTE_KW)
    if is_fully_remote:
        return True

    # Fallback: check basic remote keywords but require no location anchor
    has_non_austria_city = any(k in combined for k in NON_AUSTRIA_KW)
    is_remote = any(k in combined for k in REMOTE_KW)
    if is_remote and not has_non_austria_city:
        return True
    if is_remote and has_non_austria_city:
        # Has a specific non-Austria city + remote → likely hybrid or misleading
        return False

    return False


def _score_location(location: str, description: str) -> int:
    loc = (location + ' ' + description[:500]).lower()
    if any(k in loc for k in AUSTRIA_KW):
        return 20
    if any(k in loc for k in REMOTE_KW):
        return 18
    if 'hybrid' in loc:
        return 15
    if any(k in loc for k in ['germany', 'switzerland', 'netherlands', 'europe', ' eu ']):
        return 12
    return 5


def _score_company(company: str, description: str) -> int:
    text = (company + ' ' + description[:300]).lower()
    for kw in KNOWN_FMCG_COMPANIES:
        if kw in text:
            return 10
    return 5


def _score_seniority_cues(title: str, description: str) -> int:
    text = (title + ' ' + description[:1000]).lower()
    count = sum(1 for kw in SENIORITY_CUE_KW if kw in text)
    if count >= 3: return 10
    if count >= 1: return 7
    return 3


# ── MAIN SCORE FUNCTION ──────────────────────────────────────────────────────

def score_job(job: dict) -> tuple[int, str, int, int, str]:
    """
    Returns (score 0-100, language, zone 1-4, tier 1-3, class_label).
    score=0 means hard-excluded (German language, Zone 4, or Zone3/Tier3).
    class_label examples: 'A - Prime', 'B - Strong', 'C - Good', 'D - Weak', 'Skip'.
    """
    title       = job.get('title', '')
    company     = job.get('company', '')
    location    = job.get('location', '')
    description = job.get('description', '')
    full_text   = f"{title} {company} {location} {description}"

    # Hard-exclude: German language requirement
    if _is_german_language(description) or _is_german_language(title):
        return 0, 'excluded', 0, 0, 'Skip'
    if _requires_german(full_text):
        return 0, 'excluded', 0, 0, 'Skip'

    # Hard-exclude: location not eligible (non-Austria, non-remote)
    if not _is_location_eligible(location, description):
        return 0, 'excluded', 0, 0, 'Skip'

    # Detect language label
    if LANGDETECT_AVAILABLE and description:
        try:
            language = 'de' if detect(description[:1000]) == 'de' else 'en'
        except Exception:
            language = 'en'
    else:
        language = 'en'

    # Detect zone (industry) and tier (position type)
    zone = _detect_zone(title, company, description)
    tier = _detect_area_tier(title, description)

    # Look up matrix
    multiplier, class_label = ZONE_TIER_MATRIX[zone][tier]

    # Hard out
    if multiplier == 0.0:
        return 0, language, zone, tier, class_label

    # Base score components
    base = (
        _score_title(title)
        + _score_area(tier)
        + _score_location(location, description)
        + _score_company(company, description)
        + _score_seniority_cues(title, description)
    )

    final = round(min(base * multiplier, 100))
    return final, language, zone, tier, class_label


def filter_and_score(jobs: list[dict], existing_ids: set[str]) -> tuple[list[dict], list[dict]]:
    """
    Score and filter jobs. Attaches score, language, zone, zone_label to each job.
    Returns (pending_jobs, skipped_jobs).
    Threshold to show in dashboard: score >= 40.
    """
    to_save = []
    skipped = []

    for job in jobs:
        if job['id'] in existing_ids:
            continue

        score, language, zone, tier, class_label = score_job(job)
        job['score']       = score
        job['language']    = language
        job['zone']        = zone
        job['zone_label']  = ZONE_LABELS.get(zone, '')
        job['tier']        = tier
        job['class_label'] = class_label

        if language == 'excluded' or score == 0:
            job['status'] = 'skipped'
            skipped.append(job)
        elif score < 40:
            job['status'] = 'skipped'
            skipped.append(job)
        else:
            job['status'] = 'pending'
            to_save.append(job)

    to_save.sort(key=lambda j: j['score'], reverse=True)
    return to_save, skipped
