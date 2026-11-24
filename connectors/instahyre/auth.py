"""
Authentication and multi-tenant session management for instahyre_mcp.
Supports priority credential resolution:
1. Tool argument overrides (sessionid, csrftoken, cf_clearance, user_agent)
2. Active contextvars (set by per-request URL query parameters or HTTP headers)
3. In-memory session store lookup via current_session_id
4. Environment variables (INSTAHYRE_SESSIONID, INSTAHYRE_CSRFTOKEN, INSTAHYRE_CF_CLEARANCE, INSTAHYRE_USER_AGENT)
5. .env file fallback
"""
import os
import re
import time
import contextvars
from pathlib import Path
from typing import Tuple, Optional, Dict, Any
import httpx

# Default User-Agent matching the browser fingerprint where cf_clearance was generated
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:160.0) Gecko/20100101 Firefox/160.0"

# Context variables for per-request / per-session credential resolution
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_id", default="")
current_session_sessionid: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_sessionid", default="")
current_session_csrftoken: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_csrftoken", default="")
current_session_cf_clearance: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_cf_clearance", default="")
current_session_user_agent: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_user_agent", default="")
current_session_resume_url: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_resume_url", default="")

# In-memory session store for multi-tenant SSE / Streamable HTTP connections
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
    """Return True if sessionid is present."""
    sessionid, _, _, _ = resolve_credentials()
    return bool(sessionid)


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Instahyre authentication status."""
    sessionid, csrftoken, cf, ua = resolve_credentials()
    return {
        "authenticated": bool(sessionid),
        "has_keys": bool(sessionid),
        "cookies_present": {
            "sessionid": bool(sessionid),
            "csrftoken": bool(csrftoken),
            "cf_clearance": bool(cf),
            "user_agent": bool(ua),
        },
    }


def resolve_credentials(
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str], str]:
    """
    Resolve active Instahyre authentication credentials following priority rules.
    Returns: (sessionid, csrftoken, cf_clearance, user_agent)
    """
    load_env_file()

    # 1. Tool argument overrides
    res_sessionid = (sessionid or "").strip()
    res_csrftoken = (csrftoken or "").strip()
    res_cf = (cf_clearance or "").strip()
    res_ua = (user_agent or "").strip()

    # 2. ContextVar values
    if not res_sessionid:
        res_sessionid = current_session_sessionid.get().strip()
    if not res_csrftoken:
        res_csrftoken = current_session_csrftoken.get().strip()
    if not res_cf:
        res_cf = current_session_cf_clearance.get().strip()
    if not res_ua:
        res_ua = current_session_user_agent.get().strip()

    # 3. In-memory session store lookup
    active_sid = current_session_id.get().strip()
    if active_sid and active_sid in SESSION_STORE:
        s_data = SESSION_STORE[active_sid]
        s_data["last_seen"] = time.time()
        if not res_sessionid:
            res_sessionid = (s_data.get("sessionid") or "").strip()
        if not res_csrftoken:
            res_csrftoken = (s_data.get("csrftoken") or "").strip()
        if not res_cf:
            res_cf = (s_data.get("cf_clearance") or "").strip()
        if not res_ua:
            res_ua = (s_data.get("user_agent") or "").strip()

    # 4. Environment variables
    if not res_sessionid:
        res_sessionid = os.environ.get("INSTAHYRE_SESSIONID", "").strip()
    if not res_csrftoken:
        res_csrftoken = os.environ.get("INSTAHYRE_CSRFTOKEN", "").strip()
    if not res_cf:
        res_cf = os.environ.get("INSTAHYRE_CF_CLEARANCE", "").strip()
    if not res_ua:
        res_ua = os.environ.get("INSTAHYRE_USER_AGENT", "").strip()

    final_ua = res_ua if res_ua else DEFAULT_USER_AGENT
    return (
        res_sessionid if res_sessionid else None,
        res_csrftoken if res_csrftoken else None,
        res_cf if res_cf else None,
        final_ua
    )


def build_cookie_header(
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None
) -> str:
    """Construct Cookie header string with available tokens."""
    parts = []
    if csrftoken:
        parts.append(f"csrftoken={csrftoken.strip()}")
    if sessionid:
        parts.append(f"sessionid={sessionid.strip()}")
    if cf_clearance:
        parts.append(f"cf_clearance={cf_clearance.strip()}")
    return "; ".join(parts)


def discover_candidate_info(
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """
    Discover candidate identity metadata from Instahyre homepage / opportunities HTML.
    Extracts candidateId, userId, userName.
    """
    sid, csrf, cf, ua = resolve_credentials(sessionid, csrftoken, cf_clearance, user_agent)
    if not sid:
        return {"authenticated": False, "error": "No sessionid provided or found"}

    cookie_hdr = build_cookie_header(sid, csrf, cf)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": "https://www.instahyre.com/",
        "Cookie": cookie_hdr
    }
    if csrf:
        headers["X-CSRFToken"] = csrf

    try:
        with httpx.Client(timeout=15.0) as client:
            resp = client.get("https://www.instahyre.com/candidate/opportunities/?matching=true", headers=headers, follow_redirects=False)
            if resp.status_code == 302 and "login" in resp.headers.get("Location", ""):
                return {
                    "authenticated": False,
                    "status_code": 302,
                    "error": "Session expired or invalid (redirected to /login)"
                }
            if resp.status_code == 403:
                return {
                    "authenticated": False,
                    "status_code": 403,
                    "error": "Cloudflare challenge triggered. Verify cf_clearance and user_agent."
                }
            if resp.status_code == 200:
                html = resp.text
                m_cid = re.search(r'candidateId\s*=\s*[\'\"]([^\'\"]*)[\'\"]', html)
                m_uid = re.search(r'userId\s*=\s*[\'\"]([^\'\"]*)[\'\"]', html)
                m_name = re.search(r'userName\s*=\s*[\'\"]([^\'\"]*)[\'\"]', html)
                return {
                    "authenticated": True,
                    "status_code": 200,
                    "candidate_id": m_cid.group(1) if m_cid else None,
                    "user_id": m_uid.group(1) if m_uid else None,
                    "name": m_name.group(1) if m_name else None
                }
            return {
                "authenticated": False,
                "status_code": resp.status_code,
                "error": f"Unexpected response status {resp.status_code}"
            }
    except Exception as exc:
        return {"authenticated": False, "error": str(exc)}
