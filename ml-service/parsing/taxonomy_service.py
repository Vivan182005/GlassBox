import os
import json
import re
from typing import List, Dict, Any, Optional
from dotenv import load_dotenv

load_dotenv()

# Initialize Supabase client if available
supabase_client = None
try:
    from supabase import create_client
    s_url = os.environ.get("SUPABASE_URL", "").strip()
    s_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if s_url and s_key:
        supabase_client = create_client(s_url, s_key)
except Exception as e:
    print("Supabase client init in taxonomy_service:", e)

# Load local fallback taxonomy JSON
TAXONOMY_FILE = os.path.join(os.path.dirname(os.path.dirname(os.path.abspath(__file__))), "data", "taxonomy.json")
LOCAL_TAXONOMY = {"job_roles": [], "skills": [], "locations": []}
if os.path.exists(TAXONOMY_FILE):
    try:
        with open(TAXONOMY_FILE, "r", encoding="utf-8") as f:
            LOCAL_TAXONOMY = json.load(f)
    except Exception as err:
        print("Error loading local taxonomy file:", err)

class TaxonomyService:
    @staticmethod
    def search_job_roles(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        q_lower = query.lower().strip()
        if supabase_client:
            try:
                if q_lower:
                    res = supabase_client.table("job_roles").select("*").ilike("name", f"%{q_lower}%").limit(limit).execute()
                else:
                    res = supabase_client.table("job_roles").select("*").limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return res.data
            except Exception:
                pass
        
        # Local JSON Fallback
        items = LOCAL_TAXONOMY.get("job_roles", [])
        if q_lower:
            matched = [item for item in items if q_lower in item["name"].lower() or q_lower in item.get("category", "").lower()]
            return matched[:limit]
        return items[:limit]

    @staticmethod
    def search_skills(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        q_lower = query.lower().strip()
        if supabase_client:
            try:
                if q_lower:
                    res = supabase_client.table("skills").select("*").ilike("name", f"%{q_lower}%").limit(limit).execute()
                else:
                    res = supabase_client.table("skills").select("*").limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return res.data
            except Exception:
                pass
        
        # Local JSON Fallback
        items = LOCAL_TAXONOMY.get("skills", [])
        if q_lower:
            matched = [item for item in items if q_lower in item["name"].lower() or q_lower in item.get("category", "").lower()]
            return matched[:limit]
        return items[:limit]

    @staticmethod
    def search_locations(query: str = "", limit: int = 20) -> List[Dict[str, Any]]:
        q_lower = query.lower().strip()
        if supabase_client:
            try:
                if q_lower:
                    res = supabase_client.table("locations").select("*").ilike("name", f"%{q_lower}%").limit(limit).execute()
                else:
                    res = supabase_client.table("locations").select("*").limit(limit).execute()
                if res.data and len(res.data) > 0:
                    return res.data
            except Exception:
                pass
        
        # Local JSON Fallback
        items = LOCAL_TAXONOMY.get("locations", [])
        if q_lower:
            matched = [item for item in items if q_lower in item["name"].lower() or q_lower in item.get("city", "").lower() or q_lower in item.get("country", "").lower()]
            return matched[:limit]
        return items[:limit]

    @staticmethod
    def normalize_and_map_roles(raw_roles: List[str], max_roles: int = 5) -> List[Dict[str, Any]]:
        """Maps arbitrary extracted role strings to nearest Supabase taxonomy records or custom extracted items."""
        mapped = []
        seen_names = set()
        all_db_roles = TaxonomyService.search_job_roles("", limit=100)

        for raw in raw_roles:
            if len(mapped) >= max_roles:
                break
            raw_clean = raw.strip().lower()
            if not raw_clean or raw_clean in seen_names:
                continue

            best_match = None
            for db_role in all_db_roles:
                db_norm = (db_role.get("normalized_name") or db_role.get("name") or "").lower()
                if raw_clean == db_norm or raw_clean in db_norm or db_norm in raw_clean:
                    best_match = db_role
                    break
            
            if not best_match and all_db_roles:
                tokens = set(re.findall(r"\w+", raw_clean))
                for db_role in all_db_roles:
                    db_norm = (db_role.get("normalized_name") or db_role.get("name") or "")
                    db_tokens = set(re.findall(r"\w+", db_norm))
                    if len(tokens.intersection(db_tokens)) >= 1:
                        best_match = db_role
                        break

            if best_match:
                if best_match["name"].lower() not in seen_names:
                    seen_names.add(best_match["name"].lower())
                    mapped.append({
                        "id": best_match["id"],
                        "name": best_match["name"],
                        "category": best_match.get("category"),
                        "is_ai_extracted": True
                    })
            else:
                role_name = raw.strip().title()
                seen_names.add(role_name.lower())
                mapped.append({
                    "id": f"ext_role_{len(mapped)+1}",
                    "name": role_name,
                    "category": "Extracted Role",
                    "is_ai_extracted": True
                })

        return mapped[:max_roles]

    @staticmethod
    def normalize_and_map_skills(raw_skills: List[str], max_skills: int = 15) -> List[Dict[str, Any]]:
        """Maps arbitrary extracted skill strings to nearest Supabase taxonomy records or custom extracted items."""
        mapped = []
        seen_names = set()
        all_db_skills = TaxonomyService.search_skills("", limit=100)

        for raw in raw_skills:
            if len(mapped) >= max_skills:
                break
            raw_clean = raw.strip().lower()
            if not raw_clean or raw_clean in seen_names:
                continue

            best_match = None
            for db_skill in all_db_skills:
                db_norm = (db_skill.get("normalized_name") or db_skill.get("name") or "").lower()
                if raw_clean == db_norm or raw_clean in db_norm or db_norm in raw_clean:
                    best_match = db_skill
                    break

            if best_match:
                if best_match["name"].lower() not in seen_names:
                    seen_names.add(best_match["name"].lower())
                    mapped.append({
                        "id": best_match["id"],
                        "name": best_match["name"],
                        "category": best_match.get("category"),
                        "is_ai_extracted": True
                    })
            else:
                skill_name = raw.strip()
                seen_names.add(skill_name.lower())
                mapped.append({
                    "id": f"ext_skill_{len(mapped)+1}",
                    "name": skill_name,
                    "category": "Extracted Skill",
                    "is_ai_extracted": True
                })

        return mapped[:max_skills]

    @staticmethod
    def normalize_and_map_locations(raw_location: str) -> List[Dict[str, Any]]:
        """Maps raw location string to nearest Supabase location record or custom extracted item."""
        all_locs = TaxonomyService.search_locations("", limit=100)
        raw_clean = (raw_location or "").strip().lower()

        if raw_clean:
            for loc in all_locs:
                loc_norm = (loc.get("normalized_name") or loc.get("name") or "").lower()
                if raw_clean in loc_norm or loc_norm in raw_clean or loc.get("city", "").lower() in raw_clean:
                    return [{
                        "id": loc["id"],
                        "name": loc["name"],
                        "city": loc.get("city"),
                        "country": loc.get("country"),
                        "is_ai_extracted": True
                    }]

            loc_name = raw_location.strip().title()
            return [{
                "id": "ext_loc_1",
                "name": loc_name,
                "city": loc_name,
                "country": "",
                "is_ai_extracted": True
            }]

        return []

taxonomy_service = TaxonomyService()
