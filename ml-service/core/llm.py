"""
Single LLM entrypoint for the whole service.

Every feature that needs an LLM goes through `llm_json` / `llm_text`, so the
provider and model are configured in one place. Groq is tried first, Gemini
second; if neither is configured or both fail the caller gets None and is
expected to use its deterministic fallback.

The previous code hardcoded `llama-3.3-70b-versatile` (Groq) and
`gemini-1.5-flash` (Gemini). Both have been retired, so every LLM call was
failing silently and the app was running on regex fallbacks everywhere.
Models are now read from the environment with current defaults.
"""
import os
import re
import json
import time
import hashlib
import threading
from typing import Any, Dict, Optional

import requests
from dotenv import load_dotenv

load_dotenv()

GROQ_MODEL = os.environ.get("GROQ_MODEL", "openai/gpt-oss-120b")
GEMINI_MODEL = os.environ.get("GEMINI_MODEL", "gemini-2.5-flash")
GROQ_URL = "https://api.groq.com/openai/v1/chat/completions"
GEMINI_URL = "https://generativelanguage.googleapis.com/v1beta/models/{model}:generateContent"

_cache: Dict[str, Any] = {}
_cache_lock = threading.Lock()
_last_error: Dict[str, str] = {}


def _groq_key() -> str:
    return os.environ.get("GROQ_API_KEY", "").strip()


def _gemini_key() -> str:
    return os.environ.get("GEMINI_API_KEY", "").strip()


def llm_status() -> Dict[str, Any]:
    return {
        "groq": {"configured": bool(_groq_key()), "model": GROQ_MODEL, "last_error": _last_error.get("groq")},
        "gemini": {"configured": bool(_gemini_key()), "model": GEMINI_MODEL, "last_error": _last_error.get("gemini")},
        "available": bool(_groq_key() or _gemini_key()),
    }


def _parse_json(text: str) -> Optional[Dict[str, Any]]:
    if not text:
        return None
    text = text.strip()
    fenced = re.search(r"```(?:json)?\s*(\{.*\})\s*```", text, re.DOTALL)
    if fenced:
        text = fenced.group(1)
    try:
        return json.loads(text)
    except Exception:
        match = re.search(r"\{.*\}", text, re.DOTALL)
        if match:
            try:
                return json.loads(match.group(0))
            except Exception:
                return None
    return None


# Each Groq model has its own rate limit, so the smaller model is a real
# fallback when the large one hits its tokens-per-minute cap.
GROQ_FALLBACK_MODEL = os.environ.get("GROQ_FALLBACK_MODEL", "openai/gpt-oss-20b")


def _retry_after(r: requests.Response) -> float:
    try:
        return float(r.headers.get("retry-after") or 0)
    except ValueError:
        m = re.search(r"try again in ([\d.]+)s", r.text)
        return float(m.group(1)) if m else 0.0


def _groq_once(model: str, system: str, user: str, json_mode: bool, max_tokens: int, timeout: float, key: str):
    body: Dict[str, Any] = {
        "model": model,
        "messages": [{"role": "system", "content": system}, {"role": "user", "content": user}],
        "temperature": 0.1,
        "max_completion_tokens": max_tokens,
    }
    if json_mode:
        body["response_format"] = {"type": "json_object"}
    if model.startswith("openai/gpt-oss"):
        body["reasoning_effort"] = "low"
    return requests.post(GROQ_URL, json=body, headers={"Authorization": f"Bearer {key}"}, timeout=timeout)


def _call_groq(system: str, user: str, json_mode: bool, max_tokens: int, timeout: float) -> Optional[str]:
    key = _groq_key()
    if not key:
        return None
    models = [GROQ_MODEL] + ([GROQ_FALLBACK_MODEL] if GROQ_FALLBACK_MODEL and GROQ_FALLBACK_MODEL != GROQ_MODEL else [])
    for model in models:
        for attempt in range(2):
            try:
                r = _groq_once(model, system, user, json_mode, max_tokens, timeout, key)
            except Exception as e:
                _last_error["groq"] = str(e)[:160]
                break
            if r.status_code == 200:
                _last_error.pop("groq", None)
                content = r.json()["choices"][0]["message"].get("content")
                if content:
                    return content
                break
            _last_error["groq"] = f"{model} {r.status_code}: {r.text[:160]}"
            wait = _retry_after(r) if r.status_code == 429 else 0
            # A short per-minute wait is worth it; a long one means try the next model.
            if attempt == 0 and 0 < wait <= 8:
                time.sleep(wait + 0.3)
                continue
            break
    return None


def _call_gemini(system: str, user: str, json_mode: bool, max_tokens: int, timeout: float) -> Optional[str]:
    key = _gemini_key()
    if not key:
        return None
    gen_cfg: Dict[str, Any] = {"temperature": 0.1, "maxOutputTokens": max_tokens, "thinkingConfig": {"thinkingBudget": 0}}
    if json_mode:
        gen_cfg["responseMimeType"] = "application/json"
    body = {
        "systemInstruction": {"parts": [{"text": system}]},
        "contents": [{"role": "user", "parts": [{"text": user}]}],
        "generationConfig": gen_cfg,
    }
    try:
        r = requests.post(GEMINI_URL.format(model=GEMINI_MODEL), params={"key": key}, json=body, timeout=timeout)
        if r.status_code != 200:
            _last_error["gemini"] = f"{r.status_code}: {r.text[:160]}"
            return None
        _last_error.pop("gemini", None)
        parts = r.json()["candidates"][0]["content"]["parts"]
        return "".join(p.get("text", "") for p in parts)
    except Exception as e:
        _last_error["gemini"] = str(e)[:160]
        return None


def _cached(kind: str, system: str, user: str, fn):
    key = hashlib.sha256(f"{kind}\n{system}\n{user}".encode("utf-8")).hexdigest()
    with _cache_lock:
        hit = _cache.get(key)
    if hit and time.time() - hit[0] < 6 * 3600:
        return hit[1]
    value = fn()
    if value is not None:
        with _cache_lock:
            if len(_cache) > 500:
                _cache.clear()
            _cache[key] = (time.time(), value)
    return value


def llm_json(system: str, user: str, max_tokens: int = 2048, timeout: float = 45.0) -> Optional[Dict[str, Any]]:
    """Returns a parsed JSON object, or None if no provider produced valid JSON."""
    def run():
        for call in (_call_groq, _call_gemini):
            parsed = _parse_json(call(system, user, True, max_tokens, timeout) or "")
            if parsed is not None:
                return parsed
        return None
    return _cached("json", system, user, run)


def llm_text(system: str, user: str, max_tokens: int = 600, timeout: float = 30.0) -> Optional[str]:
    def run():
        for call in (_call_groq, _call_gemini):
            out = call(system, user, False, max_tokens, timeout)
            if out and out.strip():
                return out.strip()
        return None
    return _cached("text", system, user, run)
