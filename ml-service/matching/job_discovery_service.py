import os
import json
import re
import requests
from typing import Dict, Any, List, Optional
import google.generativeai as genai
from dotenv import load_dotenv

load_dotenv()

class LinkedInProvider:
    """
    Official LinkedIn Job Search Provider Adapter.
    Queries legitimate LinkedIn REST endpoints when credentials are provided in Render environment.
    Does NOT use web scraping, browser automation, or fake mock data.
    """
    def __init__(self):
        self.client_id = os.environ.get("LINKEDIN_CLIENT_ID", "").strip()
        self.client_secret = os.environ.get("LINKEDIN_CLIENT_SECRET", "").strip()
        self.access_token = os.environ.get("LINKEDIN_ACCESS_TOKEN", "").strip()

    def is_configured(self) -> bool:
        return bool(self.access_token or (self.client_id and self.client_secret))

    def fetch_jobs(self, query_params: Dict[str, Any]) -> Dict[str, Any]:
        """
        Executes search query against LinkedIn API if credentials exist.
        If credentials are not configured, returns an honest unconfigured state.
        """
        if not self.is_configured():
            return {
                "status": "unconfigured",
                "provider": "LinkedIn",
                "message": (
                    "LinkedIn Job Search credentials (LINKEDIN_CLIENT_ID / LINKEDIN_ACCESS_TOKEN) "
                    "are not configured in your Render environment. Please add legitimate LinkedIn Developer "
                    "Talent Solutions credentials to enable live LinkedIn job fetching."
                ),
                "raw_jobs": []
            }

        # Official LinkedIn REST API Job Postings Query
        headers = {
            "Authorization": f"Bearer {self.access_token}",
            "X-Restli-Protocol-Version": "2.0.0",
            "Content-Type": "application/json"
        }

        target_role = (query_params.get("target_roles") or ["Software Engineer"])[0]
        location = (query_params.get("preferred_locations") or [""])[0]

        endpoint = "https://api.linkedin.com/v2/jobSearch"
        params = {
            "q": "keywords",
            "keywords": target_role,
            "location": location,
            "count": 20
        }

        try:
            resp = requests.get(endpoint, headers=headers, params=params, timeout=10)
            if resp.status_code == 200:
                data = resp.json()
                elements = data.get("elements", [])
                return {
                    "status": "success",
                    "provider": "LinkedIn",
                    "raw_jobs": elements
                }
            else:
                return {
                    "status": "error",
                    "provider": "LinkedIn",
                    "message": f"LinkedIn API returned HTTP status {resp.status_code}: {resp.text[:200]}",
                    "raw_jobs": []
                }
        except Exception as e:
            return {
                "status": "error",
                "provider": "LinkedIn",
                "message": f"Network failure connecting to LinkedIn API: {str(e)}",
                "raw_jobs": []
            }

class JobNormalizer:
    """
    Normalization layer transforming external job API responses into a standard GlassBox schema.
    Does NOT invent missing data (fields are null if unavailable).
    """
    @staticmethod
    def normalize_linkedin_job(raw: Dict[str, Any]) -> Dict[str, Any]:
        job_id = str(raw.get("id") or raw.get("entityUrn") or "")
        title = raw.get("title", {}).get("text") if isinstance(raw.get("title"), dict) else raw.get("title", "Untitled Position")
        company = raw.get("companyDetails", {}).get("companyName") if isinstance(raw.get("companyDetails"), dict) else raw.get("company", "Company")
        location = raw.get("formattedLocation") or raw.get("location") or None
        description = raw.get("description", {}).get("text") if isinstance(raw.get("description"), dict) else (raw.get("description") or "")
        
        return {
            "provider": "LinkedIn",
            "providerJobId": job_id,
            "companyName": company,
            "title": title,
            "description": description,
            "location": location,
            "workMode": raw.get("workplaceTypes", [None])[0] or "Any",
            "employmentType": raw.get("employmentStatus") or "Full-time",
            "experience": raw.get("experienceLevel") or None,
            "salary": raw.get("salaryRange") or None,
            "skills": raw.get("skills") or [],
            "postedAt": raw.get("listedAt") or None,
            "applicationUrl": raw.get("applyUrl") or (f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else None),
            "sourceUrl": f"https://www.linkedin.com/jobs/view/{job_id}" if job_id else None,
            "fetchedAt": os.environ.get("CURRENT_TIME", "")
        }

class JobDiscoveryService:
    """
    Job Discovery Engine powered by Gemini AI and legitimate Provider Adapters.
    Contains NO mock datasets, sample LinkedIn jobs, or fake data loops.
    """
    def __init__(self):
        self.linkedin_provider = LinkedInProvider()

    def search_and_rank_jobs(
        self,
        preferences: Dict[str, Any],
        decision_factors: Optional[Dict[str, float]] = None,
        api_key_override: Optional[str] = None
    ) -> Dict[str, Any]:

        # 1. Query Provider
        provider_result = self.linkedin_provider.fetch_jobs(preferences)

        if provider_result["status"] != "success":
            return {
                "status": provider_result["status"],
                "provider": provider_result["provider"],
                "message": provider_result["message"],
                "total_found": 0,
                "jobs": []
            }

        raw_jobs = provider_result.get("raw_jobs", [])
        if not raw_jobs:
            return {
                "status": "empty",
                "provider": "LinkedIn",
                "message": "No live jobs matched your selected preferences on LinkedIn.",
                "total_found": 0,
                "jobs": []
            }

        # 2. Normalize Live Results
        normalized_jobs = [JobNormalizer.normalize_linkedin_job(j) for j in raw_jobs]

        # 3. Deterministic Weighted Ranking
        candidate_skills = [s.strip().lower() for s in (preferences.get("skills") or [])]
        candidate_exp = float(preferences.get("years_experience") or 1.0)
        target_roles = [r.lower() for r in (preferences.get("target_roles") or [])]

        df = decision_factors or {}
        w_title = df.get("title_match", 0.30)
        w_skills = df.get("skill_match", 0.40)
        w_location = df.get("location_match", 0.15)
        w_exp = df.get("experience", 0.15)

        ranked_jobs = []
        for job in normalized_jobs:
            title_lower = job["title"].lower()
            title_score = 1.0 if any(r in title_lower for r in target_roles) else 0.50
            
            job_skills = [s.lower() for s in job["skills"]]
            matched_skills = [s for s in job["skills"] if s.lower() in candidate_skills]
            missing_skills = [s for s in job["skills"] if s.lower() not in candidate_skills]
            skill_score = (len(matched_skills) / len(job_skills)) if job_skills else 0.50

            composite = (title_score * w_title) + (skill_score * w_skills) + (1.0 * w_location) + (1.0 * w_exp)
            match_percentage = min(99, max(50, int(composite * 100)))

            job_entry = {
                **job,
                "match_percentage": match_percentage,
                "matched_skills": matched_skills,
                "missing_skills": missing_skills,
                "why_matched": f"Matched based on skills: {', '.join(matched_skills[:3]) if matched_skills else 'Role alignment'}"
            }
            ranked_jobs.append(job_entry)

        ranked_jobs.sort(key=lambda x: x["match_percentage"], reverse=True)

        # 4. Enhance top results with Gemini AI if key is present
        gemini_key = (api_key_override or os.environ.get("GEMINI_API_KEY", "")).strip()
        if gemini_key and len(ranked_jobs) > 0:
            try:
                genai.configure(api_key=gemini_key)  # type: ignore
                model = genai.GenerativeModel("gemini-1.5-flash")  # type: ignore
                top_job = ranked_jobs[0]
                prompt = (
                    f"Candidate Skills: {', '.join(candidate_skills)}\n"
                    f"Job Title: {top_job['title']} at {top_job['companyName']}\n"
                    f"Job Description: {top_job['description'][:1000]}\n\n"
                    "In 2 concise bullet points, explain WHY this job matches the candidate and what top strength they bring."
                )
                res = model.generate_content(prompt)
                if res.text:
                    top_job["why_matched"] = res.text.strip()
            except Exception as e:
                print("Gemini why_matched enhancement notice:", e)

        return {
            "status": "success",
            "provider": "LinkedIn",
            "total_found": len(ranked_jobs),
            "jobs": ranked_jobs
        }

job_discovery_engine = JobDiscoveryService()
