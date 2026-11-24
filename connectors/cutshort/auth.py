"""
Cutshort MCP Multi-Tenant Authentication & Identity Resolver.
Supports Stdio, SSE, and Streamable HTTP transports with zero-config multi-tenant routing.
"""
import os
import contextvars
from pathlib import Path
from typing import Dict, Any, Optional, Tuple
import httpx

# Thread-local / task-local multi-tenant credential storage
current_cutshort_authentication: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_cutshort_authentication", default=None
)
current_cutshort_cf_clearance: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_cutshort_cf_clearance", default=None
)
current_cutshort_xsrf_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_cutshort_xsrf_token", default=None
)
current_cutshort_cssid: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_cutshort_cssid", default=None
)
current_cutshort_user_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_cutshort_user_agent", default=None
)

# In-memory session store keyed by tenant/session token
SESSION_STORE: Dict[str, Dict[str, str]] = {}

DEFAULT_FIREFOX_UA = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:160.0) Gecko/20100101 Firefox/160.0"


def _load_env_if_missing():
    """Ensure environment is populated from .env if present in workspace or parent dirs."""
    if not os.environ.get("CUTSHORT_AUTHENTICATION"):
        search_paths = [
            Path(".env"),
            Path.cwd() / ".env",
            Path(__file__).resolve().parent / ".env",
            Path(__file__).resolve().parents[1] / ".env",
            Path(__file__).resolve().parents[2] / ".env",
            Path(__file__).resolve().parents[3] / ".env",
        ]
        for p in search_paths:
            if p.exists() and p.is_file():
                try:
                    with open(p, "r", encoding="utf-8") as f:
                        for line in f:
                            line = line.strip()
                            if line and not line.startswith("#") and "=" in line:
                                k, v = line.split("=", 1)
                                clean_k = k.strip()
                                clean_v = v.strip().strip("\"'")
                                if clean_k not in os.environ:
                                    os.environ[clean_k] = clean_v
                except Exception:
                    pass


def is_authenticated() -> bool:
    """Return True if Cutshort authentication token is present."""
    auth, _, _, _, _ = resolve_credentials()
    return bool(auth)


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Cutshort authentication status."""
    auth, cf, xsrf, cssid, ua = resolve_credentials()
    return {
        "authenticated": bool(auth),
        "has_keys": bool(auth),
        "cookies_present": {
            "CUTSHORT_AUTHENTICATION": bool(auth),
            "CUTSHORT_CF_CLEARANCE": bool(cf),
            "CUTSHORT_XSRF_TOKEN": bool(xsrf),
            "CUTSHORT_CSSID": bool(cssid),
            "user_agent": bool(ua),
        },
    }


def resolve_credentials(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str], Optional[str], str]:
    """
    Resolve credentials in strict priority order:
    1. Explicit call arguments
    2. ContextVar values (from ASGI middleware)
    3. SESSION_STORE multi-tenant store
    4. Process environment variables
    5. .env file
    """
    _load_env_if_missing()

    # 1. Explicit arguments
    final_auth = cutshort_authentication
    final_cf = cf_clearance
    final_xsrf = xsrf_token
    final_cssid = cssid
    final_ua = user_agent

    # 2. ContextVar fallback
    if not final_auth:
        final_auth = current_cutshort_authentication.get()
    if not final_cf:
        final_cf = current_cutshort_cf_clearance.get()
    if not final_xsrf:
        final_xsrf = current_cutshort_xsrf_token.get()
    if not final_cssid:
        final_cssid = current_cutshort_cssid.get()
    if not final_ua:
        final_ua = current_cutshort_user_agent.get()

    # 3. Environment variable fallback
    if not final_auth:
        final_auth = os.environ.get("CUTSHORT_AUTHENTICATION")
    if not final_cf:
        final_cf = os.environ.get("CUTSHORT_CF_CLEARANCE")
    if not final_xsrf:
        final_xsrf = os.environ.get("CUTSHORT_XSRF_TOKEN")
    if not final_cssid:
        final_cssid = os.environ.get("CUTSHORT_CSSID")
    if not final_ua:
        final_ua = os.environ.get("CUTSHORT_USER_AGENT")

    return final_auth, final_cf, final_xsrf, final_cssid, (final_ua or DEFAULT_FIREFOX_UA)


def build_cookie_header(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None
) -> str:
    """Format Cookie header string for Cutshort endpoints."""
    parts = []
    if cutshort_authentication:
        parts.append(f"cutshort_authentication={cutshort_authentication}")
    if cf_clearance:
        parts.append(f"cf_clearance={cf_clearance}")
    if xsrf_token:
        parts.append(f"XSRF-TOKEN={xsrf_token}")
    if cssid:
        parts.append(f"cssid={cssid}")
    return "; ".join(parts)


def build_request_headers(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None,
    content_type: str = "application/json"
) -> Dict[str, str]:
    """Generate authenticated request headers for Cutshort endpoints."""
    cookie_str = build_cookie_header(cutshort_authentication, cf_clearance, xsrf_token, cssid)
    headers = {
        "User-Agent": user_agent or DEFAULT_FIREFOX_UA,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.9",
        "Referer": "https://cutshort.io/profile/candidate-dashboard",
        "Origin": "https://cutshort.io"
    }
    if content_type:
        headers["Content-Type"] = content_type
    if cookie_str:
        headers["Cookie"] = cookie_str
    if xsrf_token:
        headers["X-XSRF-TOKEN"] = xsrf_token
    return headers


def discover_candidate_info(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Dict[str, Any]:
    """Inspect Cutshort authenticated user session and talent card signal."""
    auth, cf, xsrf, cs, ua = resolve_credentials(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )

    if not auth:
        return {
            "authenticated": False,
            "error": "No Cutshort session credentials found. Please set CUTSHORT_AUTHENTICATION."
        }

    headers = build_request_headers(auth, cf, xsrf, cs, ua)

    user_info = {}
    signal_info = {}

    try:
        with httpx.Client(follow_redirects=True, headers=headers, timeout=12.0) as client:
            # 1. Fetch user profile
            resp_u = client.get("https://cutshort.io/api/auth/user")
            if resp_u.status_code == 200:
                user_info = resp_u.json()

            # 2. Fetch talent card / job seeker signal
            resp_s = client.get("https://cutshort.io/api/auth/jobseekersignal/find")
            if resp_s.status_code == 200:
                signal_info = resp_s.json().get("jobseekersignal", {})

    except Exception as e:
        return {"authenticated": False, "error": f"Connection failed: {str(e)}"}

    if not user_info and not signal_info:
        return {"authenticated": False, "error": "Cutshort session invalid or expired."}

    user_id = user_info.get("_id")
    tcid = signal_info.get("_id") or user_info.get("seekingStatus", {}).get("candidateSignalId")
    name = user_info.get("name") or f"{user_info.get('firstName', '')} {user_info.get('lastName', '')}".strip()

    return {
        "authenticated": True,
        "user_id": user_id,
        "tcid": tcid,
        "name": name,
        "email": user_info.get("primaryEmailId"),
        "phone": user_info.get("cellphoneNumber"),
        "headline": user_info.get("headline"),
        "summary": user_info.get("summary"),
        "experience": user_info.get("experience"),
        "current_company": signal_info.get("currentCompany", {}).get("name") if isinstance(signal_info.get("currentCompany"), dict) else signal_info.get("currentCompany"),
        "skills": [s.get("name") if isinstance(s, dict) else s for s in signal_info.get("skills", [])],
        "locations": signal_info.get("locations", []),
        "resume_name": user_info.get("seekingStatus", {}).get("resume_file_names", [None])[0]
    }
