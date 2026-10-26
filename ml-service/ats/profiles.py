"""
Config-driven catalogue of applicant tracking systems.

`url_patterns` / `html_signatures` fingerprint a careers page or apply link.
`parsing` describes publicly documented / commonly observed resume-parser
tendencies, used to simulate what survives parsing. `screening` explains how
candidates are actually filtered on that platform, which differs a lot:
Greenhouse and Lever don't auto-reject on keywords (recruiters search and
filter), while Workday, Taleo and SuccessFactors lean on knockout questions
and requisition-match ranking.

None of this is reverse-engineered from a vendor; it's a simulation profile.
"""
from typing import Any, Dict, List

ATS_PROFILES: List[Dict[str, Any]] = [
    {
        "id": "workday", "name": "Workday", "vendor_region": "Global enterprise",
        "url_patterns": [r"myworkdayjobs\.com", r"myworkdaysite\.com", r"\.wd\d+\.myworkday", r"workday\.com/[a-z-]+/careers"],
        "html_signatures": [r"myworkdayjobs\.com", r"wd\d+\.myworkdaysite"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": True, "drops_header_footer": True},
        "parser_note": "Reads multi-column layouts line-by-line across the page, so left and right columns get interleaved. Contact details placed in the document header/footer are frequently lost.",
        "screening": "Recruiters filter by knockout questions (work authorisation, notice period, years of experience) and search the parsed profile. Auto-populated application fields come straight from the parse, so a bad parse means a half-empty application.",
        "keyword_weight": 0.55,
    },
    {
        "id": "greenhouse", "name": "Greenhouse", "vendor_region": "Global tech",
        "url_patterns": [r"boards\.greenhouse\.io", r"job-boards(?:\.eu)?\.greenhouse\.io", r"boards\.eu\.greenhouse\.io", r"greenhouse\.io/embed", r"grnh\.se"],
        "html_signatures": [r"boards\.greenhouse\.io", r"greenhouse\.io/embed/job_board", r"grnh\.se", r"job-boards\.greenhouse\.io"],
        "parsing": {"handles_columns": True, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Handles two-column layouts reasonably well, but flattens tables into run-on text and drops text attached to icons.",
        "screening": "No automatic keyword rejection. Recruiters review applications and run keyword searches across the candidate database, so keyword coverage decides whether you surface in those searches.",
        "keyword_weight": 0.5,
    },
    {
        "id": "lever", "name": "Lever", "vendor_region": "Global tech",
        "url_patterns": [r"jobs\.lever\.co", r"jobs\.eu\.lever\.co", r"lever\.co/"],
        "html_signatures": [r"jobs\.lever\.co", r"lever-jobs-embed", r"api\.lever\.co"],
        "parsing": {"handles_columns": True, "handles_tables": True, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Accurate on clean single- and two-column layouts. Unusual section names and free-text date ranges are its weak spots.",
        "screening": "Recruiters search and tag candidates. Keyword matches decide whether you show up in searches, and nothing is auto-rejected.",
        "keyword_weight": 0.5,
    },
    {
        "id": "ashby", "name": "Ashby", "vendor_region": "Startups",
        "url_patterns": [r"jobs\.ashbyhq\.com", r"ashbyhq\.com"],
        "html_signatures": [r"jobs\.ashbyhq\.com", r"ashby_embed", r"ashbyhq\.com/.*embed"],
        "parsing": {"handles_columns": True, "handles_tables": True, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Modern parser that copes with most layouts. Icons and graphics are ignored.",
        "screening": "Recruiters review applications and filter on application questions; there's optional AI-assisted review. Keywords matter for search, not auto-rejection.",
        "keyword_weight": 0.5,
    },
    {
        "id": "smartrecruiters", "name": "SmartRecruiters", "vendor_region": "Global enterprise",
        "url_patterns": [r"jobs\.smartrecruiters\.com", r"careers\.smartrecruiters\.com", r"smartrecruiters\.com/"],
        "html_signatures": [r"smartrecruiters\.com/job-widget", r"jobs\.smartrecruiters\.com", r"smartrecruiters\.com/oneclick"],
        "parsing": {"handles_columns": True, "handles_tables": False, "drops_icons": False, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Strong structural recognition; complex or nested tables get flattened.",
        "screening": "Uses an AI match score that ranks applicants against the job, so keyword and title alignment directly affect your rank.",
        "keyword_weight": 0.6,
    },
    {
        "id": "icims", "name": "iCIMS", "vendor_region": "Global enterprise",
        "url_patterns": [r"\.icims\.com", r"icims\.com/jobs"],
        "html_signatures": [r"icims\.com/icims2", r"\.icims\.com"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": True, "drops_header_footer": True},
        "parser_note": "Older parsing rules: two-column resumes get heavily distorted and unfamiliar section names are dropped.",
        "screening": "Knockout questions plus a job-match ranking. Exact keyword and title matches carry a lot of weight.",
        "keyword_weight": 0.6,
    },
    {
        "id": "taleo", "name": "Oracle Taleo", "vendor_region": "Global enterprise",
        "url_patterns": [r"\.taleo\.net", r"taleo\.net/careersection"],
        "html_signatures": [r"taleo\.net"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": True, "drops_header_footer": True},
        "parser_note": "Legacy enterprise parser. Expects standard headings ('Work Experience', 'Education') and often drops contact details from headers.",
        "screening": "Requisition questions act as hard knockouts, and its candidate ranking scores how well the resume matches the requisition, so exact keywords count.",
        "keyword_weight": 0.65,
    },
    {
        "id": "oracle", "name": "Oracle Recruiting Cloud", "vendor_region": "Global enterprise",
        "url_patterns": [r"oraclecloud\.com/hcmUI/CandidateExperience", r"fa\.\w+\.oraclecloud\.com"],
        "html_signatures": [r"hcmUI/CandidateExperience"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": True, "drops_header_footer": True},
        "parser_note": "Behaves like Taleo: favours single-column resumes with conventional headings.",
        "screening": "Knockout questions and recruiter keyword search, plus optional AI match ranking.",
        "keyword_weight": 0.6,
    },
    {
        "id": "successfactors", "name": "SAP SuccessFactors", "vendor_region": "Global enterprise",
        "url_patterns": [r"successfactors\.(?:com|eu)", r"jobs\.sap\.com", r"career\d*\.successfactors"],
        "html_signatures": [r"successfactors\.(?:com|eu)", r"rmk-map"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": True, "drops_header_footer": True},
        "parser_note": "Sensitive to non-standard headings and visual layout elements, and mostly expects a single column.",
        "screening": "Pre-screening questions act as knockouts; recruiters then filter by keywords and qualifications.",
        "keyword_weight": 0.6,
    },
    {
        "id": "darwinbox", "name": "Darwinbox", "vendor_region": "India",
        "url_patterns": [r"darwinbox\.in", r"darwinbox\.com/.*career", r"\.darwinbox\."],
        "html_signatures": [r"darwinbox\.(?:in|com)"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": True},
        "parser_note": "Common among Indian enterprises. It auto-fills application fields from the resume, and simple single-column layouts parse most reliably.",
        "screening": "Recruiters shortlist using filters (experience, notice period, current CTC, location) and keyword search.",
        "keyword_weight": 0.55,
    },
    {
        "id": "keka", "name": "Keka Hire", "vendor_region": "India",
        "url_patterns": [r"\.keka\.com/careers", r"keka\.com/careers"],
        "html_signatures": [r"\.keka\.com"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Popular with Indian startups and SMBs. It extracts the basics (contact, experience, skills); complex layouts lose detail.",
        "screening": "Recruiters screen manually, using keyword search and pipeline filters.",
        "keyword_weight": 0.5,
    },
    {
        "id": "zoho_recruit", "name": "Zoho Recruit", "vendor_region": "India / Global SMB",
        "url_patterns": [r"zohorecruit\.(?:com|in)", r"recruit\.zoho\.(?:com|in)"],
        "html_signatures": [r"zohorecruit", r"recruit\.zoho"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": True},
        "parser_note": "Field-mapping parser: anything it can't map to a field ends up in a raw text blob.",
        "screening": "Recruiters search by keywords and filter by skills; candidate-to-job match scoring is available.",
        "keyword_weight": 0.55,
    },
    {
        "id": "freshteam", "name": "Freshteam", "vendor_region": "India / Global SMB",
        "url_patterns": [r"\.freshteam\.com/jobs", r"freshteam\.com"],
        "html_signatures": [r"freshteam\.com"],
        "parsing": {"handles_columns": True, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "Handles basic layouts; tables and graphics get flattened.",
        "screening": "Manual review supported by keyword search.",
        "keyword_weight": 0.5,
    },
    {
        "id": "eightfold", "name": "Eightfold AI", "vendor_region": "Global enterprise",
        "url_patterns": [r"eightfold\.ai/careers", r"\.eightfold\.ai"],
        "html_signatures": [r"eightfold\.ai"],
        "parsing": {"handles_columns": True, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": False},
        "parser_note": "AI talent platform: it infers skills from context rather than only from exact keywords.",
        "screening": "AI match score against the role. Adjacent skills count, but core skills still need to appear explicitly.",
        "keyword_weight": 0.5,
    },
    {
        "id": "phenom", "name": "Phenom", "vendor_region": "Global enterprise",
        "url_patterns": [r"phenompeople\.com", r"/global/en/job/"],
        "html_signatures": [r"phenompeople", r"phenom-"],
        "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": True},
        "parser_note": "Phenom is a careers-site layer; resumes are usually passed through to the underlying ATS (often Workday or SuccessFactors).",
        "screening": "AI matching on the careers site; the real screening happens in the underlying ATS.",
        "keyword_weight": 0.55,
    },
]

GENERIC_PROFILE: Dict[str, Any] = {
    "id": "generic", "name": "Generic ATS", "vendor_region": "Unknown",
    "url_patterns": [], "html_signatures": [],
    "parsing": {"handles_columns": False, "handles_tables": False, "drops_icons": True, "strict_headers": False, "drops_header_footer": True},
    "parser_note": "Conservative baseline: assumes the parser struggles with columns, tables, icons and header/footer content.",
    "screening": "Assume keyword search plus knockout questions.",
    "keyword_weight": 0.55,
}

PROFILE_BY_ID: Dict[str, Dict[str, Any]] = {p["id"]: p for p in ATS_PROFILES}
PROFILE_BY_ID["generic"] = GENERIC_PROFILE


def get_profile(ats_id: str) -> Dict[str, Any]:
    return PROFILE_BY_ID.get((ats_id or "").lower(), GENERIC_PROFILE)


def public_profile(p: Dict[str, Any]) -> Dict[str, Any]:
    return {k: p[k] for k in ("id", "name", "vendor_region", "parsing", "parser_note", "screening")}
