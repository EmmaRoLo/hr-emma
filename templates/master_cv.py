"""
Master CV data for Emmanuel Rodríguez.
This is the single source of truth for all CV generation.
The Claude API generator selects and tailors from this data per job.
"""

PROFILE = {
    "name": "Emmanuel Rodríguez",
    "title": "Commercial & Insights Leader | Business Transformation | FMCG",
    "address": "Harruck 8, 3920 Groß Gerungs, Austria",
    "phone": "+43 66021 64853",
    "email": "emmanuel.rdrlp@gmail.com",
    "linkedin": "https://www.linkedin.com/in/emmanuel-rdrlp/",
    "work_authorization": "Legal resident in Austria — fully eligible to work in Austria/EU",
}

SUMMARY = (
    "Commercial & Insights Leader with 10+ years driving revenue growth, category strategy, "
    "and organizational transformation across FMCG / CPG in LATAM. Expert in consumer insights, "
    "advanced analytics, and commercial excellence. Currently leading Business Transformation at "
    "PepsiCo, designing operating models for scale. MBA candidate at TU Wien (Austria). "
    "Legal resident — fully eligible to work in Austria/EU."
)

CORE_COMPETENCIES = [
    "Consumer Insights",
    "Shopper Analytics",
    "Category Management",
    "Commercial Strategy",
    "Market Intelligence",
    "Business Transformation",
    "Operating Model Design",
    "P&L Management",
    "Cross-functional Leadership",
    "Annual Operating Plan (AOP)",
    "Advanced Analytics",
    "Power BI",
    "Nielsen RMS / Scan / TT",
    "Kantar Panel",
    "FMCG / CPG / Retail",
    "Regional Leadership",
    "Stakeholder Management",
    "Change Management",
    "Strategic Planning",
    "Campaign Management",
]

EXPERIENCE = [
    {
        "title": "Business Transformation Lead, Commercial & Sales",
        "company": "PepsiCo LATAM",
        "start": "Oct 2025",
        "end": "Present",
        "tags": ["transformation", "commercial", "strategy", "leadership", "operations"],
        "bullets": [
            "Designed end-to-end Commercial & Sales capability transition across 8 LATAM markets, reducing operational complexity by ~30% and accelerating time-to-execution.",
            "Defined governance frameworks and service delivery models in partnership with Global Capability Centers (GCC), ensuring disciplined transitions and measurable business impact.",
            "Orchestrated cross-functional alignment across Commercial, Sales, Finance and Capabilities (150+ stakeholders), enabling sustainable growth and long-term competitiveness.",
            "Led large-scale transformation programs in close partnership with LATAM Commercial Leadership, ensuring disciplined execution and measurable outcomes.",
        ],
    },
    {
        "title": "SR Manager, Market & Consumer Insights",
        "company": "PepsiCo LATAM Foods",
        "start": "Jan 2024",
        "end": "Sep 2025",
        "tags": ["insights", "analytics", "consumer", "shopper", "strategy", "fmcg"],
        "bullets": [
            "Drove Consumer & Market Insights strategy for PepsiCo Mexico Foods (~$2B revenue base), shaping AOP decisions and long-term growth initiatives at C-suite level.",
            "Delivered high-impact market intelligence to senior leadership, directly influencing annual operating plans and category investment decisions.",
            "Built and deployed advanced analytics capabilities reducing time-to-insight by 40%, strengthening forecasting and performance management frameworks.",
            "Led category growth frameworks and consumer segmentation projects to support commercial execution across Sales, Marketing, Finance and Supply Chain.",
        ],
    },
    {
        "title": "Analytics & Insights Manager",
        "company": "PepsiCo LATAM Foods",
        "start": "Jun 2021",
        "end": "Dec 2022",
        "tags": ["analytics", "insights", "regional", "leadership", "fmcg"],
        "bullets": [
            "Standardized regional information architecture across 8 LATAM countries, ensuring consistent data access and reporting for all stakeholders.",
            "Led a team of 12 analysts delivering actionable insights to 8 business units, supporting $500M+ annual planning cycles.",
            "Created and implemented new analytics processes and capabilities to support business units in annual planning and performance management.",
            "Developed new BI processes and automation reducing manual reporting effort by 35% across the regional team.",
        ],
    },
    {
        "title": "Associate Business Intelligence Manager",
        "company": "PepsiCo México Savory Foods",
        "start": "Jun 2021",
        "end": "Dec 2022",
        "tags": ["analytics", "bi", "insights", "fmcg"],
        "bullets": [
            "Managed business intelligence platforms and analytics delivery for México Savory Foods division.",
            "Designed dashboards and KPI frameworks used by commercial and marketing teams for decision-making.",
        ],
    },
    {
        "title": "Marketing Manager",
        "company": "Walmart México",
        "start": "Dec 2019",
        "end": "Mar 2021",
        "tags": ["marketing", "shopper", "retail", "commercial", "campaign"],
        "bullets": [
            "Managed marketing campaigns for retail division, leading shopper marketing and category activation across key accounts.",
            "Held P&L responsibility for promotional budget across key categories, optimizing ROI on marketing investment.",
            "Collaborated with suppliers on joint business plans and category growth strategies.",
        ],
    },
    {
        "title": "Research Manager",
        "company": "Kantar Worldpanel",
        "start": "Apr 2019",
        "end": "Dec 2019",
        "tags": ["research", "consumer", "insights", "panel", "fmcg"],
        "bullets": [
            "Led consumer panel research projects for top FMCG clients, delivering purchase behavior and category penetration analysis.",
            "Designed custom research methodologies for category penetration and brand health measurement.",
        ],
    },
    {
        "title": "Category Management Coordinator",
        "company": "San Pablo Pharmacies",
        "start": "Oct 2017",
        "end": "Mar 2019",
        "tags": ["category", "commercial", "retail", "analytics"],
        "bullets": [
            "Coordinated category management projects across pharmacy retail channels.",
            "Analyzed sell-in / sell-out data to optimize SKU assortment and space allocation.",
        ],
    },
    {
        "title": "Market Analyst",
        "company": "Nielsen",
        "start": "Sep 2015",
        "end": "Sep 2017",
        "tags": ["analytics", "market", "fmcg", "retail", "nielsen"],
        "bullets": [
            "Delivered RMS / Scan / TT analysis for FMCG clients across México, supporting commercial and trade marketing decisions.",
            "Prepared competitive landscape reports and market share tracking for key account teams.",
        ],
    },
]

EDUCATION = [
    {
        "degree": "MBA — Advanced Technologies & Global Leadership",
        "institution": "TU Wien (Vienna University of Technology)",
        "location": "Vienna, Austria",
        "start": "Oct 2025",
        "end": "Expected 2027",
    },
    {
        "degree": "Bachelor — Trade Relationships",
        "institution": "Instituto Politécnico Nacional (IPN)",
        "location": "Mexico City, México",
        "start": "Aug 2011",
        "end": "May 2015",
    },
]

LANGUAGES = [
    {"language": "Spanish", "level": "Native"},
    {"language": "English", "level": "Advanced (C1)"},
]

SOFTWARE = [
    "Power BI",
    "Microsoft Excel (Advanced)",
    "PowerPoint",
    "Nielsen RMS, ST, NIV, SCAN",
    "TT, SABINE, SPECTRA",
    "Kantar Panel",
]
