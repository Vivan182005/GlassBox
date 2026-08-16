import re
import os
import json
import urllib.request
from typing import Dict, Any, Optional
from groq import Groq

ATS_SIGNATURES = [
    {
        "id": "workday",
        "name": "Workday",
        "patterns": [r"myworkdayjobs\.com", r"workday\.com", r"wd\d+\.myworkdayjobs\.com"],
        "parsing_behavior": {
            "handles_columns": False,
            "handles_tables": False,
            "drops_icons": True,
            "strict_headers": True,
            "drops_header_footer": True,
            "description": "Concatenates multi-column text horizontally line-by-line. Drops header/footer contact info and non-standard section headers like 'What I've Built'."
        }
    },
    {
        "id": "greenhouse",
        "name": "Greenhouse",
        "patterns": [r"boards\.greenhouse\.io", r"job-boards\.greenhouse\.io", r"greenhouse\.io"],
        "parsing_behavior": {
            "handles_columns": True,
            "handles_tables": False,
            "drops_icons": True,
            "strict_headers": False,
            "drops_header_footer": False,
            "description": "Good column detection, but flattens table cells into unstructured rows and drops text attached to graphic icons."
        }
    },
    {
        "id": "lever",
        "name": "Lever",
        "patterns": [r"jobs\.lever\.co", r"lever\.co"],
        "parsing_behavior": {
            "handles_columns": True,
            "handles_tables": True,
            "drops_icons": True,
            "strict_headers": False,
            "drops_header_footer": False,
            "description": "High accuracy on standard layouts, but mangles non-standard section headers and dates formatted as text ranges."
        }
    },
    {
        "id": "icims",
        "name": "iCIMS",
        "patterns": [r".*\.icims\.com", r"icims\.com"],
        "parsing_behavior": {
            "handles_columns": False,
            "handles_tables": False,
            "drops_icons": True,
            "strict_headers": True,
            "drops_header_footer": True,
            "description": "Legacy parser rules. Severely distorts 2-column resumes and drops unrecognized custom section names."
        }
    },
    {
        "id": "taleo",
        "name": "Taleo (Oracle)",
        "patterns": [r".*\.taleo\.net", r"taleo\.net"],
        "parsing_behavior": {
            "handles_columns": False,
            "handles_tables": False,
            "drops_icons": True,
            "strict_headers": True,
            "drops_header_footer": True,
            "description": "Legacy enterprise ATS. Requires exact standard headers ('Work Experience', 'Education') and drops header contact details."
        }
    },
    {
        "id": "smartrecruiters",
        "name": "SmartRecruiters",
        "patterns": [r"jobs\.smartrecruiters\.com", r"smartrecruiters\.com"],
        "parsing_behavior": {
            "handles_columns": True,
            "handles_tables": False,
            "drops_icons": False,
            "strict_headers": False,
            "drops_header_footer": False,
            "description": "Modern parser with strong structural recognition, but flattens complex nested tables."
        }
    },
    {
        "id": "successfactors",
        "name": "SAP SuccessFactors",
        "patterns": [r".*\.successfactors\.com", r"successfactors\.com"],
        "parsing_behavior": {
            "handles_columns": False,
            "handles_tables": False,
            "drops_icons": True,
            "strict_headers": True,
            "drops_header_footer": True,
            "description": "Enterprise parser sensitive to non-standard header naming and visual layout elements."
        }
    }
]

GENERIC_ATS_PROFILE = {
    "id": "generic",
    "name": "Generic / Standard ATS",
    "patterns": [],
    "parsing_behavior": {
        "handles_columns": False,
        "handles_tables": False,
        "drops_icons": True,
        "strict_headers": False,
        "drops_header_footer": False,
        "description": "Baseline ATS parser profile with conservative column and table degradation assumptions."
    }
}

def get_cache_file_path() -> str:
    possible_paths = [
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "ats_company_cache.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.dirname(os.path.abspath(__file__)))), "data", "ats_company_cache.json"),
        os.path.join(os.getcwd(), "data", "ats_company_cache.json"),
        os.path.join(os.getcwd(), "ml-service", "data", "ats_company_cache.json")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            return p
    return possible_paths[0]

def load_company_cache() -> Dict[str, Any]:
    cache_path = get_cache_file_path()
    if os.path.exists(cache_path):
        try:
            with open(cache_path, "r", encoding="utf-8") as f:
                return json.load(f)
        except Exception:
            return {}
    return {}

def save_company_cache(cache_data: Dict[str, Any]):
    try:
        cache_path = get_cache_file_path()
        os.makedirs(os.path.dirname(cache_path), exist_ok=True)
        with open(cache_path, "w", encoding="utf-8") as f:
            json.dump(cache_data, f, indent=2)
    except Exception as e:
        print("Failed to save ATS company cache:", e)

def detect_ats_from_url(url: str) -> Dict[str, Any]:
    if not url or not url.strip():
        return {
            "detected": False,
            "profile": GENERIC_ATS_PROFILE,
            "confidence": 0.0,
            "message": "No URL provided; falling back to Generic ATS profile.",
            "source_tier": "tier1"
        }
    
    url_clean = url.strip().lower()
    for ats in ATS_SIGNATURES:
        for pattern in ats["patterns"]:
            if re.search(pattern, url_clean):
                return {
                    "detected": True,
                    "profile": ats,
                    "confidence": 0.95,
                    "message": f"Successfully detected {ats['name']} from live URL domain signature.",
                    "source_tier": "tier1",
                    "detected_url": url.strip()
                }
                
    return {
        "detected": False,
        "profile": GENERIC_ATS_PROFILE,
        "confidence": 0.20,
        "message": "URL signature did not match known ATS domain signatures. Using Generic ATS fallback profile.",
        "source_tier": "tier1"
    }

def detect_ats_by_company_name(company_name: str, groq_api_key_override: Optional[str] = None) -> Dict[str, Any]:
    if not company_name or not company_name.strip():
        return detect_ats_from_url("")
        
    comp_clean = company_name.strip()
    cache_key = comp_clean.lower()
    
    # 1. Check local company cache
    cache = load_company_cache()
    if cache_key in cache:
        cached_entry = cache[cache_key]
        cached_entry["from_cache"] = True
        return cached_entry

    # 2. Tier 1: Probe direct ATS subdomains
    slug = re.sub(r"[^a-zA-Z0-9]", "", comp_clean.lower())
    probe_patterns = [
        (f"https://boards.greenhouse.io/{slug}", "greenhouse"),
        (f"https://jobs.lever.co/{slug}", "lever"),
        (f"https://{slug}.myworkdayjobs.com", "workday"),
        (f"https://{slug}.wd1.myworkdayjobs.com", "workday"),
        (f"https://{slug}.wd3.myworkdayjobs.com", "workday"),
        (f"https://{slug}.wd5.myworkdayjobs.com", "workday"),
        (f"https://jobs.smartrecruiters.com/{slug}", "smartrecruiters"),
        (f"https://{slug}.icims.com", "icims"),
        (f"https://{slug}.taleo.net", "taleo")
    ]
    
    tier1_attempted = True
    for url, ats_id in probe_patterns:
        try:
            req = urllib.request.Request(url, headers={'User-Agent': 'Mozilla/5.0'})
            res = urllib.request.urlopen(req, timeout=2.5)
            if res.status in (200, 301, 302):
                matched_ats = next((a for a in ATS_SIGNATURES if a["id"] == ats_id), GENERIC_ATS_PROFILE)
                result = {
                    "detected": True,
                    "company_name": comp_clean,
                    "profile": matched_ats,
                    "confidence": 0.95,
                    "source_tier": "tier1",
                    "badge_label": f"Verified Live URL: {url}",
                    "message": f"Verified {comp_clean} uses {matched_ats['name']} via live ATS endpoint {url}.",
                    "detected_url": url,
                    "tier1_attempted": True
                }
                cache[cache_key] = result
                save_company_cache(cache)
                return result
        except Exception:
            pass

    # 3. Tier 2: Groq LLM Best Guess Fallback
    api_key = (groq_api_key_override or os.environ.get("GROQ_API_KEY", "")).strip()
    if api_key:
        try:
            client = Groq(api_key=api_key)
            system_prompt = (
                "You are an HR-tech Applicant Tracking System expert. "
                "Given a company name, predict which ATS platform (Workday, Greenhouse, Lever, iCIMS, Taleo, SmartRecruiters, or SAP SuccessFactors) they primarily use. "
                "Return ONLY a strict JSON object:\n"
                "{\n"
                '  "ats_id": "workday"|"greenhouse"|"lever"|"icims"|"taleo"|"smartrecruiters"|"successfactors"|"generic",\n'
                '  "confidence": "medium"|"low",\n'
                '  "reasoning": "one-line rationale"\n'
                "}"
            )
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"Company Name: {comp_clean}"}
                ],
                temperature=0.0,
                response_format={"type": "json_object"}
            )
            res_content = response.choices[0].message.content
            data = json.loads((res_content or "").strip())
            guessed_id = data.get("ats_id", "generic").lower()
            matched_ats = next((a for a in ATS_SIGNATURES if a["id"] == guessed_id), GENERIC_ATS_PROFILE)
            
            result = {
                "detected": True,
                "company_name": comp_clean,
                "profile": matched_ats,
                "confidence": 0.60,
                "source_tier": "tier2",
                "badge_label": "AI Best Guess — Unverified",
                "message": f"AI Best Guess for {comp_clean}: Likely uses {matched_ats['name']}. ({data.get('reasoning', '')})",
                "reasoning": data.get("reasoning", ""),
                "tier1_attempted": True
            }
            cache[cache_key] = result
            save_company_cache(cache)
            return result
        except Exception as e:
            print("Groq ATS prediction failed:", e)

    # Generic Fallback
    res_generic = {
        "detected": False,
        "company_name": comp_clean,
        "profile": GENERIC_ATS_PROFILE,
        "confidence": 0.30,
        "source_tier": "tier2",
        "badge_label": "Generic ATS Fallback",
        "message": f"Could not verify ATS for {comp_clean}. Using Generic ATS profile."
    }
    return res_generic
