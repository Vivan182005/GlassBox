import pandas as pd
import json
import re
import random
import os

FIRST_NAMES_GROUP_A = ["Alex", "Jordan", "Taylor", "Morgan", "Sam", "Chris", "Pat", "Riley"]
FIRST_NAMES_GROUP_B = ["Darnell", "Jamal", "DeAndre", "Keisha", "Tanisha", "Lakisha", "Mateo", "Aaliyah"]
LAST_NAMES = ["Smith", "Johnson", "Williams", "Brown", "Jones", "Garcia", "Miller", "Davis", "Rodriguez", "Martinez"]

TIER1_KEYWORDS = ["stanford", "mit", "massachusetts institute", "carnegie mellon", "berkeley", "harvard", "cornell", "princeton", "georgia tech", "oxford", "cambridge"]

def process_kaggle_dataset():
    url = 'https://huggingface.co/datasets/batuhanmtl/job_resume_fit/resolve/main/job_resume_fit.csv'
    print(f"Downloading real Kaggle resume dataset from {url}...")
    df = pd.read_csv(url, nrows=250)
    
    random.seed(42)
    cached_candidates = []
    
    for idx, row in df.iterrows():
        i = int(str(idx))
        raw_resume = str(row.get('resume_text', '')).strip()
        if not raw_resume or len(raw_resume) < 50:
            continue
            
        category = str(row.get('category', 'Software Engineering')).strip()
        
        # Demographic proxy assignment (Synthetic benchmark proxy)
        group = "Group A" if i % 2 == 0 else "Group B"
        first = random.choice(FIRST_NAMES_GROUP_A if group == "Group A" else FIRST_NAMES_GROUP_B)
        last = random.choice(LAST_NAMES)
        full_name = f"{first} {last}"
        
        # Skill extraction
        skills_raw = str(row.get('resume_skill_list', ''))
        skills = [s.strip().title() for s in re.split(r"[,\;\|]", skills_raw) if len(s.strip()) > 1]
        if not skills:
            skills = ["Python", "SQL", "Communication", "Project Management"]
        skill_count = len(skills)
        
        # College tier detection
        resume_lower = raw_resume.lower()
        is_tier1 = any(kw in resume_lower for kw in TIER1_KEYWORDS)
        college_tier = "Tier 1" if is_tier1 else "Tier 2/3"
        college_name = "Top Tier University (Stanford/MIT/CMU)" if is_tier1 else "State University"
        
        # Years experience extraction
        exp_match = re.search(r"(\d+[\.\d]*)\+?\s*years", resume_lower)
        if exp_match:
            try:
                years_exp = float(exp_match.group(1))
                if years_exp > 25: years_exp = 12.0
            except ValueError:
                years_exp = round(random.uniform(2.0, 9.0), 1)
        else:
            years_exp = round(random.uniform(1.5, 8.5), 1)
            
        # Employment gap detection
        gap_match = re.search(r"(\d+)\s*month\s*gap", resume_lower)
        if gap_match:
            gap_months = int(gap_match.group(1))
        else:
            has_gap = random.random() < 0.20
            gap_months = random.choice([3, 6, 9, 12]) if has_gap else 0
            
        # New Feature 1: Internship detection
        has_internship = bool(re.search(r"\bintern\b|\binternship\b", resume_lower))
        internship_months = random.choice([3, 6, 9]) if has_internship else 0
        
        # New Feature 2: GPA / CGPA extraction
        gpa_match = re.search(r"gpa\s*[:\-]?\s*([34]\.\d+)", resume_lower)
        if gpa_match:
            try: gpa = float(gpa_match.group(1))
            except: gpa = round(random.uniform(3.1, 3.9), 2)
        else:
            gpa = round(random.uniform(3.0, 3.95), 2)
            
        # New Feature 3: Project Count
        projects_count = len(re.findall(r"\bproject\b|\bbuilt\b|\bdeveloped\b", resume_lower))
        projects_count = max(1, min(10, projects_count))
        
        # New Feature 4: Graduation Year
        grad_match = re.search(r"\b(201[5-9]|202[0-5])\b", raw_resume)
        grad_year = int(grad_match.group(1)) if grad_match else random.choice([2021, 2022, 2023, 2024])
        
        # New Feature 5: Has Employee Referral (synthetic bias proxy)
        has_referral = (i % 3 == 0)
        
        cached_candidates.append({
            "candidate_id": f"KAG-{i+1:04d}",
            "full_name": full_name,
            "demographic_proxy": group,
            "domain": category,
            "target_role": f"{category} Specialist",
            "college": college_name,
            "college_tier": college_tier,
            "years_experience": years_exp,
            "employment_gap_months": gap_months,
            "has_internship": has_internship,
            "internship_months": internship_months,
            "gpa": gpa,
            "project_count": projects_count,
            "graduation_year": grad_year,
            "has_referral": has_referral,
            "skills": skills[:10],
            "skill_count": len(skills[:10]),
            "raw_resume_text": raw_resume
        })
        
    output_path = os.path.join(os.path.dirname(__file__), "cached_resumes.json")
    with open(output_path, "w", encoding="utf-8") as f:
        json.dump(cached_candidates, f, indent=2)
        
    print(f"Successfully processed {len(cached_candidates)} real Kaggle resumes with expanded student & bias factors saved to {output_path}")

if __name__ == "__main__":
    process_kaggle_dataset()
