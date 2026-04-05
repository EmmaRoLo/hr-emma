"""
Master cover letter template for Emmanuel Rodríguez.
The Claude API generator fills in [COMPANY], [ROLE], and tailors the body paragraphs.
"""

HEADER = {
    "name": "Emmanuel Rodríguez",
    "address": "Harruck 8, 3920 Groß Gerungs, Austria",
    "phone": "+43 66021 64853",
    "email": "emmanuel.rdrlp@gmail.com",
    "linkedin": "https://www.linkedin.com/in/emmanuel-rdrlp/",
}

# Short version used in LinkedIn Easy Apply text boxes (≤300 chars)
SHORT_VERSION = (
    "Commercial & Insights Leader with 10+ years in FMCG (PepsiCo, Nielsen, Kantar). "
    "Expert in consumer insights, advanced analytics and commercial strategy. "
    "Based in Austria with full EU work authorization. "
    "Eager to bring measurable impact to [COMPANY]."
)

# Full version structure — Claude fills in paragraph bodies per job
STRUCTURE = {
    "salutation": "Dear Hiring Team,",
    "opening": (
        "I am writing to express my strong interest in the [ROLE] position at [COMPANY]. "
        "With 10+ years of experience driving commercial strategy, consumer insights, and "
        "organizational transformation across FMCG / CPG in LATAM, I am confident I can "
        "deliver measurable impact from day one."
    ),
    "paragraph_2_template": (
        # Claude replaces this with job-specific achievements from master_cv
        "[2-3 sentences highlighting the most relevant experience bullets for this specific role. "
        "Mirror keywords from the job description. Quantify impact.]"
    ),
    "paragraph_3_template": (
        # Claude tailors this to company context
        "[1-2 sentences on why this company specifically — industry fit, mission, market position. "
        "Show you did your research.]"
    ),
    "austria_paragraph": (
        "I currently hold legal residence in Austria, ensuring full eligibility to live and "
        "work locally without any sponsorship requirement."
    ),
    "closing": (
        "I would welcome the opportunity to discuss how my background in [KEY_AREA] can "
        "contribute to [COMPANY]'s growth objectives. Thank you for your consideration."
    ),
    "sign_off": "Kind regards,\nEmmanuel Rodríguez",
}

# Keywords to emphasize per area (used by Claude to select relevant bullets)
AREA_KEYWORDS = {
    "consumer_insights": [
        "consumer insights", "market research", "shopper behavior", "panel data",
        "segmentation", "brand health", "category penetration", "Kantar", "Nielsen",
    ],
    "analytics": [
        "advanced analytics", "data-driven", "Power BI", "KPI", "performance management",
        "forecasting", "business intelligence", "reporting", "dashboards",
    ],
    "marketing": [
        "campaign management", "brand strategy", "go-to-market", "shopper marketing",
        "category activation", "marketing planning", "P&L", "ROI",
    ],
    "commercial": [
        "commercial strategy", "revenue growth", "trade marketing", "key account",
        "annual operating plan", "AOP", "commercial excellence", "category management",
    ],
    "shopper": [
        "shopper insights", "path to purchase", "in-store", "retail execution",
        "category management", "planogram", "shopper marketing",
    ],
    "strategy": [
        "business transformation", "operating model", "strategic planning",
        "change management", "cross-functional", "stakeholder management", "GCC",
    ],
}
