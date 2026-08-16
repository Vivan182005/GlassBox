import re
import io
from typing import Dict, Any, List, Tuple
import pdfplumber
import docx

STANDARD_HEADERS = [
    "experience", "work experience", "professional experience", "employment history",
    "education", "academic background",
    "skills", "technical skills", "core competencies",
    "projects", "key projects", "personal projects",
    "certifications", "summary", "professional summary"
]

NON_STANDARD_HEADERS_MAP = {
    "what i've built": "projects",
    "my journey": "experience",
    "where i've worked": "experience",
    "superpowers": "skills",
    "tech stack": "skills",
    "background": "summary",
    "credentials": "certifications"
}

def extract_pdf_structure(file_bytes: bytes) -> Dict[str, Any]:
    text_blocks = []
    full_raw = ""
    
    try:
        with pdfplumber.open(io.BytesIO(file_bytes)) as pdf:
            for page_num, page in enumerate(pdf.pages):
                words = page.extract_words(keep_blank_chars=True)
                page_text = page.extract_text() or ""
                full_raw += page_text + "\n"
                
                # Group words into physical lines by top coordinate
                lines_dict = {}
                for w in words:
                    top = round(w["top"], 1)
                    if top not in lines_dict:
                        lines_dict[top] = []
                    lines_dict[top].append(w)
                    
                sorted_tops = sorted(lines_dict.keys())
                for top in sorted_tops:
                    line_words = sorted(lines_dict[top], key=lambda x: x["x0"])
                    line_str = " ".join(w["text"] for w in line_words)
                    min_x = line_words[0]["x0"]
                    max_x = line_words[-1]["x1"]
                    text_blocks.append({
                        "text": line_str,
                        "top": top,
                        "min_x": min_x,
                        "max_x": max_x,
                        "page": page_num,
                        "page_height": page.height,
                        "page_width": page.width
                    })
    except Exception as e:
        full_raw = ""
        
    return {
        "raw_text": full_raw.strip(),
        "blocks": text_blocks
    }

def extract_docx_text(file_bytes: bytes) -> str:
    try:
        doc = docx.Document(io.BytesIO(file_bytes))
        paragraphs = [p.text for p in doc.paragraphs if p.text.strip()]
        return "\n".join(paragraphs)
    except Exception:
        return ""

def simulate_degradation(
    raw_text: str,
    blocks: List[Dict[str, Any]],
    ats_profile: Dict[str, Any]
) -> Dict[str, Any]:
    behavior = ats_profile.get("parsing_behavior", {})
    handles_columns = behavior.get("handles_columns", False)
    strict_headers = behavior.get("strict_headers", False)
    drops_header_footer = behavior.get("drops_header_footer", False)
    drops_icons = behavior.get("drops_icons", True)
    
    degraded_lines = []
    mangled_spans = []
    warnings = []
    
    lines = [line.strip() for line in raw_text.split("\n") if line.strip()]
    
    if not lines and blocks:
        lines = [b["text"] for b in blocks]
        
    # 1. Header/Footer Contact Dropping
    if drops_header_footer:
        filtered_lines = []
        for i, line in enumerate(lines):
            is_header_footer_pos = (i == 0 or i == 1 or i >= len(lines) - 2)
            has_contact_info = bool(re.search(r"email:|phone:|linkedin|\@|\d{3}-\d{3}-\d{4}", line, re.IGNORECASE))
            if is_header_footer_pos and has_contact_info and not re.search(r"summary|experience|education", line, re.IGNORECASE):
                mangled_spans.append({
                    "type": "contact_dropped",
                    "text": line,
                    "reason": f"{ats_profile['name']} often drops contact details isolated in page headers/footers."
                })
                warnings.append(f"Dropped contact info from header/footer: '{line[:40]}...'")
                continue
            filtered_lines.append(line)
        lines = filtered_lines
        
    # 2. Multi-column Concatenation Simulation
    if not handles_columns:
        # Check if text looks like two horizontal columns merged line by line
        initial_column_spans = len(mangled_spans)
        new_lines = []
        for line in lines:
            # If line has large spacing gap in middle, simulate left-right merging
            if "   " in line:
                parts = [p.strip() for p in re.split(r"\s{3,}", line) if p.strip()]
                if len(parts) >= 2:
                    merged = parts[0] + " | " + parts[1]
                    mangled_spans.append({
                        "type": "column_merged",
                        "text": line,
                        "reason": f"{ats_profile['name']} parser merges horizontal multi-column layouts into single concatenated lines."
                    })
                    new_lines.append(merged)
                    continue
            new_lines.append(line)
        lines = new_lines
        if len(mangled_spans) > initial_column_spans:
            warnings.append(f"Simulated {ats_profile['name']} multi-column text interleave.")

    # 3. Non-standard Headers Handling
    final_output_lines = []
    for line in lines:
        clean_lower = line.strip().lower().rstrip(":")
        
        # Icon stripping
        if drops_icons:
            line_no_icons = re.sub(r"[\u2600-\u27BF\U0001F600-\U0001F64F\u260E\u2709\u2615\u25C0-\u25FE]", "", line).strip()
            if line_no_icons != line:
                mangled_spans.append({
                    "type": "icon_stripped",
                    "text": line,
                    "reason": "Graphic icons stripped by parser engine."
                })
                line = line_no_icons
                
        if clean_lower in NON_STANDARD_HEADERS_MAP:
            standardized = NON_STANDARD_HEADERS_MAP[clean_lower]
            if strict_headers:
                mangled_spans.append({
                    "type": "unrecognized_header",
                    "text": line,
                    "reason": f"Non-standard header '{line}' unrecognized by {ats_profile['name']}. Content below may be misfiled."
                })
                warnings.append(f"Unrecognized header '{line}' (suggested: '{standardized.title()}')")
                final_output_lines.append(f"[UNRECOGNIZED SECTION: {line.upper()}]")
                continue
        final_output_lines.append(line)
        
    survived_text = "\n".join(final_output_lines)
    
    # Calculate integrity score
    total_orig_len = max(len(raw_text), 1)
    retained_len = len(survived_text)
    mangled_penalty = len(mangled_spans) * 8
    survived_percentage = max(0, min(100, int((retained_len / total_orig_len) * 100) - mangled_penalty))

    return {
        "original_text": raw_text,
        "parsed_text": survived_text,
        "parsing_score": survived_percentage,
        "ats_profile": ats_profile,
        "mangled_spans": mangled_spans,
        "warnings": warnings
    }
