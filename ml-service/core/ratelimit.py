"""
Who may call the API, and how often.

Browsers: only GlassBox's own sites. CORS alone stops other sites from reading
responses, but a multipart upload from another site is still sent, so a request
whose Origin isn't ours is refused outright.

Everyone (browsers, scripts, curl): per-IP sliding-window limits by cost, plus
a daily cap per cost class across all callers, so the Groq/Gemini and JSearch
quotas survive even a caller who rotates IPs.

Limits live in this process's memory. That fits the single free Render
instance; a restart clears them.
"""

import os
import threading
import time
from collections import defaultdict, deque
from typing import Deque, Dict, Optional, Tuple

DEFAULT_ORIGINS = [
    "https://glass-box-psi.vercel.app",
    "https://glass-box1.vercel.app",
    "http://localhost:3000",
    "http://127.0.0.1:3000",
]


def allowed_origins() -> list:
    """Our sites, plus any listed in ALLOWED_ORIGINS (comma-separated)."""
    extra = [o.strip().rstrip("/") for o in os.environ.get("ALLOWED_ORIGINS", "").split(",") if o.strip()]
    return list(dict.fromkeys(DEFAULT_ORIGINS + [o for o in extra if o != "*"]))


# Cost classes: (requests per IP, window in seconds, requests per day for all callers).
LIMITS: Dict[str, Tuple[int, int, int]] = {
    "search": (15, 3600, 300),     # job search: company boards + JSearch credits
    "llm": (60, 3600, 2000),       # resume reading, checks, tailoring, form answers
    "default": (240, 60, 0),       # health, meta, descriptions, files (0 = no daily cap)
}

_LLM_PATHS = (
    "/api/resume/analyze", "/api/resume/ats-view", "/api/check", "/api/apply/",
    "/api/company/lookup", "/api/company/confirm", "/api/assistant",
)


def cost_class(path: str) -> str:
    if path == "/api/jobs/search":
        return "search"
    if path.startswith(_LLM_PATHS):
        return "llm"
    return "default"


def client_ip(headers, peer: Optional[str]) -> str:
    """The caller's address. Render sits behind Cloudflare, which sets
    CF-Connecting-IP itself; X-Forwarded-For is the fallback elsewhere."""
    ip = headers.get("cf-connecting-ip") or (headers.get("x-forwarded-for") or "").split(",")[0].strip()
    return ip or peer or "unknown"


class Limiter:
    def __init__(self, limits: Dict[str, Tuple[int, int, int]] = LIMITS):
        self.limits = limits
        self._hits: Dict[Tuple[str, str], Deque[float]] = defaultdict(deque)
        self._day: Dict[str, Tuple[int, int]] = {}
        self._lock = threading.Lock()

    def check(self, ip: str, cls: str, now: Optional[float] = None) -> Optional[Tuple[str, int]]:
        """None when allowed (and counted); otherwise (message, retry-after seconds)."""
        now = time.time() if now is None else now
        per_ip, window, per_day = self.limits[cls]
        with self._lock:
            hits = self._hits[(ip, cls)]
            while hits and hits[0] <= now - window:
                hits.popleft()
            if len(hits) >= per_ip:
                wait = int(hits[0] + window - now) + 1
                return f"Too many requests from your connection. Try again in {_human(wait)}.", wait
            day = int(now // 86400)
            used_day, count = self._day.get(cls, (day, 0))
            if used_day != day:
                count = 0
            if per_day and count >= per_day:
                wait = int((day + 1) * 86400 - now) + 1
                return "GlassBox has reached today's limit for this. Try again tomorrow.", wait
            hits.append(now)
            self._day[cls] = (day, count + 1)
            if len(self._hits) > 50000:  # forget idle callers
                for key in [k for k, v in self._hits.items() if not v or v[-1] < now - 3600]:
                    del self._hits[key]
        return None


def _human(seconds: int) -> str:
    if seconds < 90:
        return f"{seconds} seconds"
    return f"{(seconds + 59) // 60} minutes"
