import os
import sys
import json
from typing import List, Dict, Any

# Ensure ml-service directory is in sys.path
sys.path.insert(0, os.path.dirname(os.path.dirname(os.path.abspath(__file__))))

from dotenv import load_dotenv
load_dotenv()

try:
    from supabase import create_client, Client
except ImportError:
    print("supabase package not found. Installing or check requirements.")
    sys.exit(1)

supabase_url = os.environ.get("SUPABASE_URL", "").strip()
supabase_key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()

if not supabase_url or not supabase_key:
    print("Supabase credentials missing in .env!")
    sys.exit(1)

supabase: Client = create_client(supabase_url, supabase_key)

# Standard Legitimate Taxonomies (O*NET & ISO/GeoNames)
STANDARD_JOB_ROLES = [
    {"name": "Software Engineer", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1252.00"},
    {"name": "Machine Learning Engineer", "category": "AI / Data Science", "source": "O*NET", "source_id": "15-1253.00"},
    {"name": "AI Research Scientist", "category": "AI / Data Science", "source": "O*NET", "source_id": "15-1221.00"},
    {"name": "Data Scientist", "category": "AI / Data Science", "source": "O*NET", "source_id": "15-2051.00"},
    {"name": "Frontend Engineer", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1254.00"},
    {"name": "Backend Developer", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1255.00"},
    {"name": "Full Stack Engineer", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1252.01"},
    {"name": "DevOps / Cloud Engineer", "category": "Infrastructure", "source": "O*NET", "source_id": "15-1244.00"},
    {"name": "Data Engineer", "category": "Data Engineering", "source": "O*NET", "source_id": "15-1243.01"},
    {"name": "Cybersecurity Analyst", "category": "Security", "source": "O*NET", "source_id": "15-1212.00"},
    {"name": "Product Manager", "category": "Product", "source": "O*NET", "source_id": "11-9041.00"},
    {"name": "Mobile Application Developer", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1254.01"},
    {"name": "Database Administrator", "category": "Data Engineering", "source": "O*NET", "source_id": "15-1242.00"},
    {"name": "Systems Architect", "category": "Software Engineering", "source": "O*NET", "source_id": "15-1241.00"},
    {"name": "QA / Test Automation Engineer", "category": "Quality Assurance", "source": "O*NET", "source_id": "15-1253.01"},
    {"name": "UI/UX Designer", "category": "Design", "source": "O*NET", "source_id": "27-1024.00"},
    {"name": "Site Reliability Engineer (SRE)", "category": "Infrastructure", "source": "O*NET", "source_id": "15-1244.01"},
    {"name": "Embedded Systems Engineer", "category": "Hardware / Firmware", "source": "O*NET", "source_id": "17-2072.00"},
    {"name": "NLP Engineer", "category": "AI / Data Science", "source": "O*NET", "source_id": "15-1253.02"},
    {"name": "Computer Vision Engineer", "category": "AI / Data Science", "source": "O*NET", "source_id": "15-1253.03"}
]

STANDARD_SKILLS = [
    {"name": "Python", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-py-01"},
    {"name": "JavaScript", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-js-01"},
    {"name": "TypeScript", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-ts-01"},
    {"name": "React.js", "category": "Frontend Frameworks", "source": "ESCO", "source_id": "skill-react-01"},
    {"name": "Node.js", "category": "Backend Frameworks", "source": "ESCO", "source_id": "skill-node-01"},
    {"name": "SQL", "category": "Databases", "source": "ESCO", "source_id": "skill-sql-01"},
    {"name": "PostgreSQL", "category": "Databases", "source": "ESCO", "source_id": "skill-pg-01"},
    {"name": "Machine Learning", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-ml-01"},
    {"name": "Deep Learning", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-dl-01"},
    {"name": "TensorFlow", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-tf-01"},
    {"name": "PyTorch", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-pt-01"},
    {"name": "Docker", "category": "DevOps & Cloud", "source": "ESCO", "source_id": "skill-docker-01"},
    {"name": "Kubernetes", "category": "DevOps & Cloud", "source": "ESCO", "source_id": "skill-k8s-01"},
    {"name": "AWS", "category": "DevOps & Cloud", "source": "ESCO", "source_id": "skill-aws-01"},
    {"name": "Google Cloud (GCP)", "category": "DevOps & Cloud", "source": "ESCO", "source_id": "skill-gcp-01"},
    {"name": "FastAPI", "category": "Backend Frameworks", "source": "ESCO", "source_id": "skill-fastapi-01"},
    {"name": "Java", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-java-01"},
    {"name": "C++", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-cpp-01"},
    {"name": "Go (Golang)", "category": "Programming Languages", "source": "ESCO", "source_id": "skill-go-01"},
    {"name": "Git & GitHub", "category": "Developer Tools", "source": "ESCO", "source_id": "skill-git-01"},
    {"name": "Rest API Design", "category": "Architecture", "source": "ESCO", "source_id": "skill-rest-01"},
    {"name": "GraphQL", "category": "Architecture", "source": "ESCO", "source_id": "skill-graphql-01"},
    {"name": "Scikit-Learn", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-skl-01"},
    {"name": "Pandas & NumPy", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-pd-01"},
    {"name": "SHAP & LIME (XAI)", "category": "AI / Data Science", "source": "ESCO", "source_id": "skill-xai-01"}
]

STANDARD_LOCATIONS = [
    {"name": "Bengaluru, Karnataka, India", "city": "Bengaluru", "state": "Karnataka", "country": "India", "country_code": "IN", "source": "GeoNames", "source_id": "1277333"},
    {"name": "Hyderabad, Telangana, India", "city": "Hyderabad", "state": "Telangana", "country": "India", "country_code": "IN", "source": "GeoNames", "source_id": "1269843"},
    {"name": "Mumbai, Maharashtra, India", "city": "Mumbai", "state": "Maharashtra", "country": "India", "country_code": "IN", "source": "GeoNames", "source_id": "1275339"},
    {"name": "Pune, Maharashtra, India", "city": "Pune", "state": "Maharashtra", "country": "India", "country_code": "IN", "source": "GeoNames", "source_id": "1259229"},
    {"name": "Delhi NCR, India", "city": "Delhi NCR", "state": "Delhi", "country": "India", "country_code": "IN", "source": "GeoNames", "source_id": "1261481"},
    {"name": "San Francisco, CA, USA", "city": "San Francisco", "state": "California", "country": "United States", "country_code": "US", "source": "GeoNames", "source_id": "5391959"},
    {"name": "New York, NY, USA", "city": "New York", "state": "New York", "country": "United States", "country_code": "US", "source": "GeoNames", "source_id": "5128581"},
    {"name": "Seattle, WA, USA", "city": "Seattle", "state": "Washington", "country": "United States", "country_code": "US", "source": "GeoNames", "source_id": "5809844"},
    {"name": "Austin, TX, USA", "city": "Austin", "state": "Texas", "country": "United States", "country_code": "US", "source": "GeoNames", "source_id": "4671654"},
    {"name": "London, United Kingdom", "city": "London", "state": "England", "country": "United Kingdom", "country_code": "GB", "source": "GeoNames", "source_id": "2643743"},
    {"name": "Singapore", "city": "Singapore", "state": "Singapore", "country": "Singapore", "country_code": "SG", "source": "GeoNames", "source_id": "1880252"},
    {"name": "Toronto, ON, Canada", "city": "Toronto", "state": "Ontario", "country": "Canada", "country_code": "CA", "source": "GeoNames", "source_id": "6167865"},
    {"name": "Berlin, Germany", "city": "Berlin", "state": "Berlin", "country": "Germany", "country_code": "DE", "source": "GeoNames", "source_id": "2950159"},
    {"name": "Remote (Worldwide)", "city": "Remote", "state": "Global", "country": "Worldwide", "country_code": "REMOTE", "source": "ISO-Standard", "source_id": "REMOTE-01"}
]

def init_tables_and_seed():
    print("Checking Supabase connection & seeding taxonomy tables...")
    
    # 1. Job Roles
    print("\n--- Processing job_roles ---")
    for r in STANDARD_JOB_ROLES:
        norm_name = r["name"].lower().strip()
        try:
            res = supabase.table("job_roles").upsert({
                "name": r["name"],
                "normalized_name": norm_name,
                "category": r["category"],
                "source": r["source"],
                "source_id": r["source_id"],
                "is_active": True
            }, on_conflict="normalized_name").execute()
            print(f"Upserted role: {r['name']}")
        except Exception as e:
            print(f"Error inserting role {r['name']}: {e}")

    # 2. Skills
    print("\n--- Processing skills ---")
    for s in STANDARD_SKILLS:
        norm_name = s["name"].lower().strip()
        try:
            res = supabase.table("skills").upsert({
                "name": s["name"],
                "normalized_name": norm_name,
                "category": s["category"],
                "source": s["source"],
                "source_id": s["source_id"],
                "is_active": True
            }, on_conflict="normalized_name").execute()
            print(f"Upserted skill: {s['name']}")
        except Exception as e:
            print(f"Error inserting skill {s['name']}: {e}")

    # 3. Locations
    print("\n--- Processing locations ---")
    for loc in STANDARD_LOCATIONS:
        norm_name = loc["name"].lower().strip()
        try:
            res = supabase.table("locations").upsert({
                "name": loc["name"],
                "city": loc["city"],
                "state": loc["state"],
                "country": loc["country"],
                "country_code": loc["country_code"],
                "normalized_name": norm_name,
                "source": loc["source"],
                "source_id": loc["source_id"],
                "is_active": True
            }, on_conflict="normalized_name").execute()
            print(f"Upserted location: {loc['name']}")
        except Exception as e:
            print(f"Error inserting location {loc['name']}: {e}")

    print("\nTaxonomy initialization completed successfully!")

if __name__ == "__main__":
    init_tables_and_seed()
