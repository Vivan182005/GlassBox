"""
Optional Supabase client shared by every module.

Supabase is an optional cache/persistence layer. If it isn't configured or its
host can't be reached (for example a paused free-tier project), every module
falls back to local files instead of waiting on a dead host on every request.
"""
import os
import socket
from functools import lru_cache
from urllib.parse import urlparse

from dotenv import load_dotenv

load_dotenv()


@lru_cache(maxsize=1)
def get_supabase():
    url = os.environ.get("SUPABASE_URL", "").strip()
    key = os.environ.get("SUPABASE_SERVICE_ROLE_KEY", "").strip() or os.environ.get("SUPABASE_ANON_KEY", "").strip()
    if not url or not key:
        return None
    host = urlparse(url).hostname or ""
    try:
        socket.getaddrinfo(host, 443)
    except Exception:
        print(f"Supabase host {host} is unreachable; using local storage only.")
        return None
    try:
        from supabase import create_client
        return create_client(url, key)
    except Exception as e:
        print("Supabase client init failed:", e)
        return None
