"""
Authentication and session management for hirist_mcp.
Supports multi-tenant credential resolution (Query Parameter -> HTTP Header -> Tool Argument -> Environment Variable -> .env).
"""
import os
import json
import base64
import time
import threading
import contextvars
from pathlib import Path
from typing import Tuple, Optional, Dict, Any

# Context variables for per-request / per-session credential resolution
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_id", default="")
current_session_token: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_token", default="")
current_session_phpsessid: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_phpsessid", default="")
current_session_resume_url: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_resume_url", default="")

# In-memory session store for multi-tenant SSE / Streamable HTTP connections
# SESSION_STORE: session_id -> {"token": str, "phpsessid": str, "resume_url": str, "created_at": float, "last_seen": float}
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


def decode_jwt(token: str) -> Dict[str, Any]:
    """Decode payload from a JWT token safely without external libraries."""
    if not token or "." not in token:
        return {}
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return {}
        payload_b64 = parts[1]
        # Pad base64
        padded = payload_b64 + "=" * (-len(payload_b64) % 4)
        return json.loads(base64.urlsafe_b64decode(padded.encode("utf-8")).decode("utf-8"))
    except Exception:
        return {}


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
    """Return True if Hirist token is present."""
    token, _ = resolve_credentials()
    return bool(token)


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Hirist authentication status."""
    token, phpsessid = resolve_credentials()
    jwt_data = decode_jwt(token)
    return {
        "authenticated": bool(token),
        "has_keys": bool(token),
        "user_id": jwt_data.get("sub") or jwt_data.get("user_id"),
        "exp": jwt_data.get("exp"),
        "cookies_present": {
            "HIRIST_CK1": bool(token),
            "PHPSESSID": bool(phpsessid),
        },
    }


def resolve_credentials(
    token_override: Optional[str] = None,
    phpsessid_override: Optional[str] = None
) -> Tuple[str, str]:
    """
    Resolve active Hirist credentials in strict priority order:
    1. Explicit tool argument override
    2. Active contextvars (set by per-request URL query parameter or HTTP header)
    3. Active session store lookup via current_session_id
    4. Environment variables (HIRIST_CK1 / HIRIST_TOKEN, PHPSESSID)
    5. .env file fallback

    Returns:
        (token, phpsessid)
    """
    token = (token_override or "").strip()
    phpsessid = (phpsessid_override or "").strip()

    if not token:
        token = current_session_token.get().strip()
    if not phpsessid:
        phpsessid = current_session_phpsessid.get().strip()

    sess_id = current_session_id.get().strip()
    if sess_id and sess_id in SESSION_STORE:
        sess_data = SESSION_STORE[sess_id]
        sess_data["last_seen"] = time.time()
        if not token:
            token = str(sess_data.get("token", "")).strip()
        if not phpsessid:
            phpsessid = str(sess_data.get("phpsessid", "")).strip()

    if not token:
        load_env_file()
        token = (
            os.getenv("HIRIST_CK1")
            or os.getenv("HIRIST_TOKEN")
            or os.getenv("HIRIST_SEEKER_ENC")
            or ""
        ).strip()

    if not phpsessid:
        phpsessid = os.getenv("PHPSESSID", "").strip()

    return token, phpsessid


def build_cookie_header(token: str, phpsessid: str = "") -> str:
    """
    Construct the Cookie header for Hirist API requests.
    Hirist authentication accepts HIRIST_CK1 and hirist_seeker_enc.
    """
    cookies = []
    if token:
        cookies.append(f"HIRIST_CK1={token}")
        cookies.append(f"hirist_seeker_enc={token}")
    if phpsessid:
        cookies.append(f"PHPSESSID={phpsessid}")
    return "; ".join(cookies)


# Global lock and debounce timestamp to prevent 401 stampedes during parallel tool calls
REFRESH_LOCK = threading.Lock()
LAST_REFRESH_TIMESTAMP = 0.0


def refresh_hirist_token(
    phpsessid_override: Optional[str] = None,
    token_override: Optional[str] = None
) -> Tuple[str, str]:
    """
    Query Hirist central auth service with PHPSESSID and existing token to mint a fresh HIRIST_CK1 token.
    Uses a mutex lock and 5s debouncing to prevent thundering herd / 401 stampedes across concurrent requests.
    """
    global LAST_REFRESH_TIMESTAMP
    token, phpsessid = resolve_credentials(token_override, phpsessid_override)
    if not phpsessid:
        return "", ""

    with REFRESH_LOCK:
        # Debounce: if refreshed within last 5 seconds, return current active credentials
        now = time.time()
        if now - LAST_REFRESH_TIMESTAMP < 5.0:
            latest_token, latest_phpsessid = resolve_credentials(token_override, phpsessid_override)
            if latest_token:
                return latest_token, latest_phpsessid

        url = "https://gladiator.hirist.tech/auth/refresh"
        headers = {
            "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36",
            "Cookie": build_cookie_header(token, phpsessid),
            "Origin": "https://www.hirist.tech",
            "Referer": "https://www.hirist.tech/"
        }

        try:
            import httpx
            with httpx.Client(timeout=httpx.Timeout(5.0, connect=3.0)) as c:
                resp = c.get(url, headers=headers)
                if resp.status_code == 200:
                    body = resp.json()
                    new_token = body.get("token", "")
                    if new_token:
                        LAST_REFRESH_TIMESTAMP = time.time()
                        current_session_token.set(new_token)
                        os.environ["HIRIST_CK1"] = new_token
                        sess_id = current_session_id.get()
                        if sess_id and sess_id in SESSION_STORE:
                            SESSION_STORE[sess_id]["token"] = new_token
                        return new_token, phpsessid
        except Exception:
            pass
        return "", ""
