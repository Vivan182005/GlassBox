import os
import sys
import json
from typing import Dict, Any, Optional, List

# Ensure ml-service root is in sys.path
sys.path.insert(0, os.path.dirname(os.path.abspath(__file__)))

from fastapi import FastAPI, UploadFile, File, Form, HTTPException
from fastapi.middleware.cors import CORSMiddleware
from pydantic import BaseModel

from parsing.ats_signatures import detect_ats_from_url, detect_ats_by_company_name, ATS_SIGNATURES, GENERIC_ATS_PROFILE
from parsing.degradation_engine import extract_pdf_structure, extract_docx_text, simulate_degradation
from parsing.profile_extractor import extract_candidate_profile
from matching.groq_matcher import match_resume_to_jd
from matching.job_discovery_service import job_discovery_engine
from bias_model.model_trainer import trainer_instance
from explainability.explainer import explainer_instance
from explainability.fairness import calculate_fairness_metrics
from parsing.taxonomy_service import taxonomy_service

app = FastAPI(
    title="GlassBox ML Microservice",
    description="ATS Reality-Checker & Explainable Hiring Bias Auditor Engine",
    version="1.0.0"
)

allowed_origins_env = os.environ.get("ALLOWED_ORIGINS", "*")
allowed_origins = [o.strip() for o in allowed_origins_env.split(",")] if allowed_origins_env != "*" else ["*"]

app.add_middleware(
    CORSMiddleware,
    allow_origins=allowed_origins,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

class UrlDetectRequest(BaseModel):
    url: str

class CompanyDetectRequest(BaseModel):
    company_name: str
    groq_api_key: Optional[str] = None

class JobSearchRequest(BaseModel):
    preferences: Dict[str, Any]
    decision_factors: Optional[Dict[str, float]] = None
    gemini_api_key: Optional[str] = None
    groq_api_key: Optional[str] = None

class MatchRequest(BaseModel):
    resume_text: str
    jd_text: str
    groq_api_key: Optional[str] = None

class CandidatePredictRequest(BaseModel):
    years_experience: float = 3.0
    skill_count: int = 5
    college_tier: str = "Tier 2/3"
    employment_gap_months: float = 0
    has_internship: bool = True
    gpa: float = 3.5
    project_count: int = 3
    graduation_year: int = 2023
    has_referral: bool = False
    demographic_proxy: str = "Group B"
    ice_feature: Optional[str] = "employment_gap_months"
    groq_api_key: Optional[str] = None

@app.get("/api/health")
def health_check():
    return {
        "status": "ok",
        "service": "GlassBox ML Microservice",
        "groq_configured": bool(os.environ.get("GROQ_API_KEY", "").strip())
    }

@app.get("/api/model/stats")
def get_model_training_stats():
    if trainer_instance.model is None:
        trainer_instance.train_model()
    return trainer_instance.metrics

@app.get("/api/job-roles")
def get_job_roles(search: Optional[str] = "", limit: int = 20):
    return taxonomy_service.search_job_roles(search or "", limit=limit)

@app.get("/api/skills")
def get_skills(search: Optional[str] = "", limit: int = 20):
    return taxonomy_service.search_skills(search or "", limit=limit)

@app.get("/api/locations")
def get_locations(search: Optional[str] = "", limit: int = 20):
    return taxonomy_service.search_locations(search or "", limit=limit)

@app.post("/api/ats/detect")
def detect_ats(req: UrlDetectRequest):
    return detect_ats_from_url(req.url)

@app.post("/api/ats/detect-company")
def detect_ats_company(req: CompanyDetectRequest):
    return detect_ats_by_company_name(req.company_name, groq_api_key_override=req.groq_api_key)

@app.post("/api/resume/extract-profile")
async def extract_profile_from_resume(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    groq_api_key: Optional[str] = Form(None),
    max_roles: Optional[int] = Form(5)
):
    extracted_text = ""
    filename = "resume.pdf"
    if file:
        file_bytes = await file.read()
        filename = file.filename or "resume.pdf"
        fname_lower = filename.lower()
        if fname_lower.endswith(".pdf"):
            pdf_data = extract_pdf_structure(file_bytes)
            extracted_text = pdf_data["raw_text"]
        elif fname_lower.endswith(".docx"):
            extracted_text = extract_docx_text(file_bytes)
        else:
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
    elif raw_text and raw_text.strip():
        extracted_text = raw_text.strip()
    else:
        raise HTTPException(status_code=400, detail="Please upload a PDF/DOCX resume file or provide text.")

    profile_data = extract_candidate_profile(extracted_text, filename=filename, api_key_override=groq_api_key)
    
    # Normalize extracted strings against Supabase taxonomy
    inferred = profile_data.get("inferred_fields", {})
    explicit = profile_data.get("explicit_fields", {})

    raw_roles = []
    if inferred.get("primary_role"):
        raw_roles.append(inferred["primary_role"])
    raw_roles.extend(inferred.get("suggested_alternative_roles", []))

    raw_skills = explicit.get("skill_list", [])
    raw_loc = explicit.get("location", "")

    mapped_roles = taxonomy_service.normalize_and_map_roles(raw_roles, max_roles=max_roles or 5)
    mapped_skills = taxonomy_service.normalize_and_map_skills(raw_skills, max_skills=10)
    mapped_locations = taxonomy_service.normalize_and_map_locations(raw_loc)

    profile_data["taxonomy_roles"] = mapped_roles
    profile_data["taxonomy_skills"] = mapped_skills
    profile_data["taxonomy_locations"] = mapped_locations

    return profile_data

@app.post("/api/jobs/search")
def search_and_rank_jobs_endpoint(req: JobSearchRequest):
    return job_discovery_engine.search_and_rank_jobs(
        preferences=req.preferences,
        decision_factors=req.decision_factors,
        api_key_override=req.gemini_api_key or req.groq_api_key
    )

@app.post("/api/parse/simulate")
async def parse_and_simulate(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None),
    careers_url: Optional[str] = Form(""),
    company_name: Optional[str] = Form("")
):
    extracted_text = ""
    blocks = []
    
    if file:
        file_bytes = await file.read()
        filename = (file.filename or "").lower()
        if filename.endswith(".pdf"):
            pdf_data = extract_pdf_structure(file_bytes)
            extracted_text = pdf_data["raw_text"]
            blocks = pdf_data["blocks"]
        elif filename.endswith(".docx"):
            extracted_text = extract_docx_text(file_bytes)
        else:
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
    elif raw_text and raw_text.strip():
        extracted_text = raw_text.strip()
    else:
        raise HTTPException(status_code=400, detail="Please upload a PDF/DOCX file or select a candidate resume.")
        
    if careers_url and careers_url.strip():
        ats_detection = detect_ats_from_url(careers_url)
    elif company_name and company_name.strip():
        ats_detection = detect_ats_by_company_name(company_name)
    else:
        ats_detection = detect_ats_from_url("")
        
    profile = ats_detection["profile"]
    degradation_res = simulate_degradation(extracted_text, blocks, profile)
    degradation_res["ats_detection"] = ats_detection
    return degradation_res

@app.post("/api/batch/parse")
async def batch_parse_all_ats(
    file: Optional[UploadFile] = File(None),
    raw_text: Optional[str] = Form(None)
):
    extracted_text = ""
    blocks = []
    if file:
        file_bytes = await file.read()
        filename = (file.filename or "").lower()
        if filename.endswith(".pdf"):
            pdf_data = extract_pdf_structure(file_bytes)
            extracted_text = pdf_data["raw_text"]
            blocks = pdf_data["blocks"]
        elif filename.endswith(".docx"):
            extracted_text = extract_docx_text(file_bytes)
        else:
            extracted_text = file_bytes.decode("utf-8", errors="ignore")
    elif raw_text and raw_text.strip():
        extracted_text = raw_text.strip()
    else:
        raise HTTPException(status_code=400, detail="No resume content provided.")

    comparison = []
    profiles_to_test = ATS_SIGNATURES + [GENERIC_ATS_PROFILE]
    for profile in profiles_to_test:
        sim = simulate_degradation(extracted_text, blocks, profile)
        comparison.append({
            "ats_id": profile["id"],
            "ats_name": profile["name"],
            "parsing_score": sim["parsing_score"],
            "mangled_count": len(sim["mangled_spans"]),
            "warnings_count": len(sim["warnings"]),
            "description": profile["parsing_behavior"]["description"]
        })
        
    return {
        "original_text_snippet": extracted_text[:300] + "...",
        "comparison": comparison
    }

@app.post("/api/match/score")
def score_jd_match(req: MatchRequest):
    if not req.resume_text.strip() or not req.jd_text.strip():
        raise HTTPException(status_code=400, detail="Both resume_text and jd_text are required.")
    return match_resume_to_jd(req.resume_text, req.jd_text, api_key_override=req.groq_api_key)

@app.post("/api/model/predict-explain")
def predict_and_explain(req: CandidatePredictRequest):
    feat_dict = req.model_dump()
    prediction_res = trainer_instance.predict_candidate(feat_dict)
    global_shap = explainer_instance.get_global_shap_importance()
    waterfall_res = explainer_instance.get_candidate_shap_waterfall(feat_dict)
    lime_res = explainer_instance.get_lime_explanation(feat_dict)
    ice_res = explainer_instance.get_ice_plot_data(req.ice_feature or "employment_gap_months", feat_dict)
    
    plain_explanation = explainer_instance.generate_plain_language_explanation(
        feat_dict, prediction_res, waterfall_res["waterfall"], ice_res, api_key_override=req.groq_api_key
    )
    
    return {
        "candidate_features": feat_dict,
        "model_verdict": prediction_res,
        "plain_language_summary": plain_explanation,
        "global_shap": global_shap["global_importance"],
        "shap_waterfall": waterfall_res,
        "lime_explanation": lime_res,
        "ice_plot": ice_res
    }

@app.get("/api/model/fairness")
def get_fairness_audit():
    return calculate_fairness_metrics()

@app.get("/api/resumes/sample")
def get_sample_resumes():
    possible_paths = [
        os.path.join(os.path.dirname(os.path.abspath(__file__)), "data", "cached_resumes.json"),
        os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "cached_resumes.json"),
        os.path.join(os.getcwd(), "data", "cached_resumes.json"),
        os.path.join(os.getcwd(), "ml-service", "data", "cached_resumes.json")
    ]
    for p in possible_paths:
        if os.path.exists(p):
            try:
                with open(p, "r", encoding="utf-8") as f:
                    candidates = json.load(f)
                    return candidates[:25]
            except Exception:
                pass
    return []
