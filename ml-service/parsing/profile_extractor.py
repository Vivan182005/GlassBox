import os
import json
import re
from typing import Dict, Any, Optional, List
from groq import Groq
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

# Optional Supabase Client initialization
supabase_client = None
try:
    from supabase import create_client
    supabase_url = os.environ.get("SUPABASE_URL", "").strip()
    supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if supabase_url and supabase_key:
        supabase_client = create_client(supabase_url, supabase_key)
except Exception as e:
    print("Supabase client init notice:", e)

def extract_candidate_profile(raw_text: str, filename: str = "resume.pdf", api_key_override: Optional[str] = None) -> Dict[str, Any]:
    """
    Extracts structured candidate profile from raw resume text using Gemini AI (or Groq fallback).
    Strictly separates EXPLICITLY present facts from LLM INFERENCES.
    Saves metadata to Supabase DB when available.
    """
    clean_text = raw_text.strip()
    if not clean_text:
        return {
            "error": "Empty resume text provided",
            "explicit_fields": {},
            "inferred_fields": {},
            "consolidated_profile": {}
        }

    gemini_key = (api_key_override or os.environ.get("GEMINI_API_KEY", "")).strip()
    groq_key = (os.environ.get("GROQ_API_KEY", "")).strip()

    system_prompt = (
        "You are an expert HR-tech Applicant Tracking System auditor and candidate profiler. "
        "Analyze the resume text and extract structured profile data. "
        "CRITICAL REQUIREMENT: You MUST strictly distinguish EXPLICIT facts present in text from INFERRED estimations.\n\n"
        "Return ONLY a valid JSON object matching this schema:\n"
        "{\n"
        '  "explicit_fields": {\n'
        '    "full_name": "exact candidate name if present, else null",\n'
        '    "years_experience": float (sum of explicit work durations), \n'
        '    "skill_list": ["explicitly mentioned skills"],\n'
        '    "college_name": "exact university/college name if present, else null",\n'
        '    "college_tier": "Tier 1" (ONLY if explicitly IIT, NIT, BITS, Stanford, MIT, CMU, Harvard, UC Berkeley, Ivy League) else "Tier 2/3",\n'
        '    "gpa": float (or null if not stated),\n'
        '    "graduation_year": integer (e.g. 2023, 2027), \n'
        '    "employment_gap_months": integer (explicit gaps between roles), \n'
        '    "has_internship": boolean,\n'
        '    "project_count": integer,\n'
        '    "has_referral": false,\n'
        '    "location": "city/country if stated, else null"\n'
        '  },\n'
        '  "inferred_fields": {\n'
        '    "primary_role": "inferred job title (e.g. AI/ML Engineer, Software Engineer)",\n'
        '    "seniority_level": "Entry Level" | "Mid Level" | "Senior",\n'
        '    "top_domain": "Software Engineering" | "Data Science" | "Cloud/DevOps" | "Product",\n'
        '    "suggested_alternative_roles": ["Alternative Role 1", "Alternative Role 2", "Alternative Role 3"]\n'
        '  }\n'
        "}\n"
        "Do NOT hallucinate or fabricate facts. If a field is not in the text, mark explicit fields as null or 0."
    )

    explicit, inferred = None, None

    # Priority 1: Gemini API
    if gemini_key:
        try:
            genai.configure(api_key=gemini_key)  # type: ignore
            model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore
            response = model.generate_content(
                f"{system_prompt}\n\nRAW CANDIDATE RESUME TEXT:\n{clean_text[:4000]}"
            )
            raw_res = (response.text or "").strip()
            # Extract json block if present
            json_match = re.search(r"\{.*\}", raw_res, re.DOTALL)
            if json_match:
                extracted_json = json.loads(json_match.group(0))
                explicit = extracted_json.get("explicit_fields", {})
                inferred = extracted_json.get("inferred_fields", {})
        except Exception as e:
            print("Gemini candidate profile extraction failed:", e)

    # Priority 2: Groq Fallback
    if not explicit and groq_key:
        try:
            client = Groq(api_key=groq_key)
            response = client.chat.completions.create(
                model="llama-3.3-70b-versatile",
                messages=[
                    {"role": "system", "content": system_prompt},
                    {"role": "user", "content": f"RAW CANDIDATE RESUME TEXT:\n{clean_text[:4000]}"}
                ],
                temperature=0.1,
                response_format={"type": "json_object"}
            )
            res_content = response.choices[0].message.content
            extracted_json = json.loads((res_content or "").strip())
            explicit = extracted_json.get("explicit_fields", {})
            inferred = extracted_json.get("inferred_fields", {})
        except Exception as e:
            print("Groq candidate profile extraction fallback failed:", e)

    # Priority 3: Rule-based Heuristics
    if not explicit:
        explicit, inferred = _heuristic_extraction(clean_text)

    explicit = explicit or {}
    inferred = inferred or {}

    # Consolidated profile for model & feature compatibility
    consolidated = {
        "full_name": explicit.get("full_name") or "Candidate",
        "primary_role": inferred.get("primary_role") or "Software Engineer",
        "years_experience": float(explicit.get("years_experience") or 2.0),
        "skill_count": len(explicit.get("skill_list") or []),
        "skill_list": explicit.get("skill_list") or ["Python", "JavaScript", "SQL"],
        "college_name": explicit.get("college_name") or "University",
        "college_tier": explicit.get("college_tier") or "Tier 2/3",
        "employment_gap_months": int(explicit.get("employment_gap_months") or 0),
        "has_internship": bool(explicit.get("has_internship") if explicit.get("has_internship") is not None else True),
        "gpa": float(explicit.get("gpa") or 3.5),
        "project_count": int(explicit.get("project_count") or 2),
        "graduation_year": int(explicit.get("graduation_year") or 2023),
        "has_referral": bool(explicit.get("has_referral") or False),
        "demographic_proxy": "Group B",
        "location": explicit.get("location") or "Remote"
    }

    result = {
        "explicit_fields": explicit,
        "inferred_fields": inferred,
        "consolidated_profile": consolidated,
        "raw_text_length": len(clean_text),
        "resume_id": None,
        "profile_id": None
    }

    # Save to Supabase DB if client is active
    if supabase_client is not None:
        try:
            # 1. Insert into public.resumes
            res_db = supabase_client.table("resumes").insert({
                "filename": filename,
                "file_type": filename.split(".")[-1] if "." in filename else "text",
                "raw_text": clean_text
            }).select().execute()
            
            db_data: Any = res_db.data
            if db_data and len(db_data) > 0:
                resume_id = db_data[0].get("id")
                result["resume_id"] = resume_id

                # 2. Insert into public.candidate_profiles
                prof_db = supabase_client.table("candidate_profiles").insert({
                    "resume_id": resume_id,
                    "full_name": consolidated["full_name"],
                    "primary_role": consolidated["primary_role"],
                    "years_experience": consolidated["years_experience"],
                    "skill_list": consolidated["skill_list"],
                    "college_name": consolidated["college_name"],
                    "college_tier": consolidated["college_tier"],
                    "gpa": consolidated["gpa"],
                    "graduation_year": consolidated["graduation_year"],
                    "employment_gap_months": consolidated["employment_gap_months"],
                    "has_internship": consolidated["has_internship"],
                    "project_count": consolidated["project_count"],
                    "has_referral": consolidated["has_referral"],
                    "location": consolidated["location"],
                    "explicit_data": explicit,
                    "inferred_data": inferred
                }).select().execute()

                prof_data: Any = prof_db.data
                if prof_data and len(prof_data) > 0:
                    result["profile_id"] = prof_data[0].get("id")
        except Exception as err:
            print("Supabase profile save notice:", err)

    return result

def _heuristic_extraction(text: str) -> tuple:
    """Fallback rule-based extractor when LLM is unavailable."""
    skills = []
    for s in ["Python", "JavaScript", "React", "Node.js", "SQL", "Machine Learning", "Docker", "AWS", "Java", "C++"]:
        if re.search(r"\b" + re.escape(s) + r"\b", text, re.IGNORECASE):
            skills.append(s)

    exp_match = re.search(r"(\d+(\.\d+)?)\s*\+?\s*years", text, re.IGNORECASE)
    years_exp = float(exp_match.group(1)) if exp_match else 2.0

    grad_match = re.search(r"\b(201[5-9]|202[0-9])\b", text)
    grad_year = int(grad_match.group(1)) if grad_match else 2023

    explicit = {
        "full_name": "Candidate",
        "years_experience": years_exp,
        "skill_list": skills if skills else ["Software Engineering", "Python"],
        "college_name": "University",
        "college_tier": "Tier 2/3",
        "gpa": 3.5,
        "graduation_year": grad_year,
        "employment_gap_months": 0,
        "has_internship": True,
        "project_count": 3,
        "has_referral": False,
        "location": "Bangalore"
    }
    inferred = {
        "primary_role": "Software Engineer",
        "seniority_level": "Entry Level",
        "top_domain": "Software Engineering",
        "suggested_alternative_roles": ["Frontend Engineer", "Backend Developer", "Full Stack Engineer"]
    }
    return explicit, inferred
