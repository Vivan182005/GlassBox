import os
import json
import re
from typing import Dict, Any, Optional
from groq import Groq

def local_keyword_match(resume_text: str, jd_text: str) -> Dict[str, Any]:
    """Fallback requirement matching using local NLP token extraction."""
    resume_words = set(re.findall(r"\b[a-zA-Z0-9\+\#\.\-]{2,}\b", resume_text.lower()))
    jd_words = re.findall(r"\b[a-zA-Z0-9\+\#\.\-]{2,}\b", jd_text.lower())
    
    stop_words = {"and", "the", "with", "for", "you", "that", "this", "have", "will", "our", "are", "from", "team", "work", "experience", "skills", "ability", "must", "plus", "role", "looking"}
    filtered_jd_terms = [w for w in jd_words if w not in stop_words and len(w) > 2]
    
    unique_requirements = sorted(list(set(filtered_jd_terms)))[:15]
    
    matched = []
    missing = []
    
    for req in unique_requirements:
        if req in resume_words:
            matched.append({
                "requirement": req.title(),
                "found": True,
                "rationale": f"Term '{req}' explicitly detected in parsed resume content."
            })
        else:
            missing.append({
                "requirement": req.title(),
                "found": False,
                "rationale": f"Term '{req}' not found in candidate parsed text."
            })
            
    total_reqs = max(len(unique_requirements), 1)
    match_score = int((len(matched) / total_reqs) * 100)
    
    # Feature extraction heuristics for local mode
    resume_lower = resume_text.lower()
    has_intern = bool(re.search(r"\bintern\b|\binternship\b", resume_lower))
    gpa_m = re.search(r"gpa\s*[:\-]?\s*([34]\.\d+)", resume_lower)
    gpa_val = float(gpa_m.group(1)) if gpa_m else 3.5
    projects_cnt = max(1, min(10, len(re.findall(r"\bproject\b|\bbuilt\b|\bdeveloped\b", resume_lower))))
    grad_m = re.search(r"\b(201[5-9]|202[0-5])\b", resume_text)
    grad_yr = int(grad_m.group(1)) if grad_m else 2023
    
    return {
        "match_score": match_score,
        "summary": f"Matched {len(matched)} out of {len(unique_requirements)} core JD requirements via local keyword analysis.",
        "matched_requirements": matched,
        "missing_requirements": missing,
        "extracted_features": {
            "years_experience": 3.5,
            "skill_count": len(matched),
            "college_tier": "Tier 1" if "stanford" in resume_lower or "mit" in resume_lower else "Tier 2/3",
            "employment_gap_months": 0,
            "has_internship": has_intern,
            "gpa": gpa_val,
            "project_count": projects_cnt,
            "graduation_year": grad_yr,
            "has_referral": False
        },
        "groq_used": False,
        "determinism_note": "Calculated via deterministic keyword token matching (local fallback mode)."
    }

def match_resume_to_jd(resume_text: str, jd_text: str, api_key_override: Optional[str] = None) -> Dict[str, Any]:
    api_key = (api_key_override or os.environ.get("GROQ_API_KEY", "")).strip()
    
    if not api_key:
        return local_keyword_match(resume_text, jd_text)
        
    try:
        client = Groq(api_key=api_key)
        
        system_prompt = (
            "You are an expert ATS Applicant Tracking System auditor. "
            "Analyze the candidate resume against the Job Description and extract structured decision features. "
            "You MUST return ONLY a strict valid JSON object matching this schema:\n"
            "{\n"
            '  "match_score": integer 0 to 100,\n'
            '  "summary": "2-sentence overall fit summary",\n'
            '  "matched_requirements": [\n'
            '    {"requirement": "req string", "found": true, "rationale": "one-line reason"}\n'
            '  ],\n'
            '  "missing_requirements": [\n'
            '    {"requirement": "req string", "found": false, "rationale": "one-line reason"}\n'
            '  ],\n'
            '  "extracted_features": {\n'
            '    "years_experience": float,\n'
            '    "skill_count": integer,\n'
            '    "college_tier": "Tier 1" (ONLY for elite institutions: IITs, NITs, BITS, Stanford, MIT, CMU, Harvard, UC Berkeley, Ivy League, or top-50 global CS/engineering universities) OR "Tier 2/3" (for all state, regional, or non-tier-1 colleges),\n'
            '    "employment_gap_months": integer,\n'
            '    "has_internship": boolean,\n'
            '    "gpa": float,\n'
            '    "project_count": integer,\n'
            '    "graduation_year": integer,\n'
            '    "has_referral": boolean\n'
            '  }\n'
            "}\n"
            "Do NOT include any markdown code blocks, conversational text, or commentary outside the JSON."
        )
        
        user_prompt = f"PARSED CANDIDATE RESUME:\n{resume_text}\n\nJOB DESCRIPTION:\n{jd_text}"
        
        response = client.chat.completions.create(
            model="llama-3.3-70b-versatile",
            messages=[
                {"role": "system", "content": system_prompt},
                {"role": "user", "content": user_prompt}
            ],
            temperature=0.0,
            response_format={"type": "json_object"}
        )
        
        res_content = response.choices[0].message.content
        raw_json = (res_content or "").strip()
        data = json.loads(raw_json)
        data["groq_used"] = True
        data["determinism_note"] = "Evaluated via Groq llama-3.3-70b-versatile LLM API with temperature=0."
        return data
        
    except Exception as e:
        fallback_res = local_keyword_match(resume_text, jd_text)
        fallback_res["summary"] += f" (Groq API call failed: {str(e)[:60]}... Used local fallback)."
        return fallback_res
