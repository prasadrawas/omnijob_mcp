"""
Authentication and multi-tenant session management for wellfound_mcp.
Supports priority credential resolution:
1. Tool argument overrides (wellfound_cookie, cf_clearance)
2. Active contextvars (set by per-request URL query parameters or HTTP headers)
3. In-memory session store lookup via current_session_id
4. Environment variables (WELLFOUND_COOKIE / _WELLFOUND, CF_CLEARANCE)
5. .env file fallback
"""
import os
import time
import contextvars
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

# Context variables for per-request / per-session credential resolution
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_id", default="")
current_session_cookie: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_cookie", default="")
current_session_cf_clearance: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_cf_clearance", default="")
current_session_resume_url: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_resume_url", default="")

# In-memory session store for multi-tenant SSE / Streamable HTTP connections
# SESSION_STORE: session_id -> {"wellfound_cookie": str, "cf_clearance": str, "resume_url": str, "created_at": float, "last_seen": float}
SESSION_STORE: Dict[str, Dict[str, Any]] = {}


def clean_stale_sessions(max_age_seconds: int = 86400) -> None:
    """Purge sessions inactive for longer than max_age_seconds (default: 24h)."""
    now = time.time()
    stale_keys = [
        sid for sid, data in SESSION_STORE.items()
        if now - float(data.get("last_seen", data.get("created_at", now))) > max_age_seconds
    ]
    for sid in stale_keys:
        SESSION_STORE.pop(sid, None)


def load_env_file(custom_env_path: Optional[str] = None) -> None:
    """Load configuration from .env file into os.environ if present."""
    candidate_paths = [
        Path(custom_env_path) if custom_env_path else None,
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
    ]
    for p in candidate_paths:
        if p and p.exists() and p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if not line or line.startswith("#") or "=" not in line:
                            continue
                        k, v = line.split("=", 1)
                        clean_k = k.strip()
                        clean_v = v.strip().strip('"').strip("'")
                        if clean_k and clean_k not in os.environ:
                            os.environ[clean_k] = clean_v
            except Exception:
                pass


def is_authenticated() -> bool:
    """Return True if Wellfound cookie is present."""
    cookie, _ = resolve_credentials()
    return bool(cookie)


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Wellfound authentication status."""
    cookie, cf = resolve_credentials()
    return {
        "authenticated": bool(cookie),
        "has_keys": bool(cookie),
        "cookies_present": {
            "WELLFOUND_COOKIE": bool(cookie),
            "CF_CLEARANCE": bool(cf),
        },
    }


def resolve_credentials(
    cookie_override: Optional[str] = None,
    cf_clearance_override: Optional[str] = None
) -> Tuple[str, str]:
    """
    Resolve active Wellfound credentials in strict priority order:
    1. Explicit tool argument override
    2. Active contextvars (set by per-request URL query parameter or HTTP header)
    3. Active session store lookup via current_session_id
    4. Environment variables (WELLFOUND_COOKIE / _WELLFOUND, CF_CLEARANCE)
    5. .env file fallback

    Returns:
        (wellfound_cookie, cf_clearance)
    """
    cookie = (cookie_override or "").strip()
    cf_clearance = (cf_clearance_override or "").strip()

    if not cookie:
        cookie = current_session_cookie.get().strip()
    if not cf_clearance:
        cf_clearance = current_session_cf_clearance.get().strip()

    sess_id = current_session_id.get().strip()
    if sess_id and sess_id in SESSION_STORE:
        sess_data = SESSION_STORE[sess_id]
        sess_data["last_seen"] = time.time()
        if not cookie:
            cookie = str(sess_data.get("wellfound_cookie", "")).strip()
        if not cf_clearance:
            cf_clearance = str(sess_data.get("cf_clearance", "")).strip()

    if not cookie:
        load_env_file()
        cookie = (
            os.getenv("WELLFOUND_COOKIE")
            or os.getenv("_WELLFOUND")
            or os.getenv("WELLFOUND_SESSION")
            or ""
        ).strip()

    if not cf_clearance:
        cf_clearance = (
            os.getenv("CF_CLEARANCE")
            or os.getenv("WELLFOUND_CF_CLEARANCE")
            or ""
        ).strip()

    # Normalize if user passed a raw cookie string containing key=value
    if cookie.startswith("_wellfound="):
        cookie = cookie.split("_wellfound=", 1)[1].split(";", 1)[0].strip()
    if cf_clearance.startswith("cf_clearance="):
        cf_clearance = cf_clearance.split("cf_clearance=", 1)[1].split(";", 1)[0].strip()

    return cookie, cf_clearance


def build_cookie_header(wellfound_cookie: str, cf_clearance: str = "") -> str:
    """
    Construct the Cookie header for Wellfound requests.
    Accepts raw _wellfound session and cf_clearance tokens.
    """
    cookies = []
    if wellfound_cookie:
        cookies.append(f"_wellfound={wellfound_cookie}")
    if cf_clearance:
        cookies.append(f"cf_clearance={cf_clearance}")
    # Common standard analytics / tracking cookies to preserve browser affinity
    cookies.append("wellfound_default_consent=1|implied-full")
    return "; ".join(cookies)
