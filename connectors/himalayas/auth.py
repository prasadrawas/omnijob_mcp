"""
Authentication and Multi-Tenant Session Management for Himalayas Connector.
Supports Himalayas Access JWT, Refresh Token, Rails user.id, App Session, Cloudflare clearance,
and optional Himalayas Remote Jobs API Key.
"""
import os
import json
import base64
import time
import contextvars
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

# Context variables for per-request / per-session multi-tenant credential resolution
current_himalayas_access_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_access_token", default=None
)
current_himalayas_refresh_token: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_refresh_token", default=None
)
current_himalayas_app_session: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_app_session", default=None
)
current_himalayas_user_id: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_user_id", default=None
)
current_himalayas_cf_clearance: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_cf_clearance", default=None
)
current_himalayas_user_agent: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_user_agent", default=None
)
current_himalayas_api_key: contextvars.ContextVar[Optional[str]] = contextvars.ContextVar(
    "current_himalayas_api_key", default=None
)

SESSION_STORE: Dict[str, Dict[str, str]] = {}

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:160.0) Gecko/20100101 Firefox/160.0"


def _load_env_if_missing() -> None:
    """Ensure environment variables are loaded from available .env files."""
    if not os.environ.get("HIMALAYAS_ACCESS_TOKEN"):
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


def decode_jwt_payload(token: str) -> Dict[str, Any]:
    """Decode JWT payload without verifying signature for diagnostic and identity introspection."""
    try:
        parts = token.strip().split(".")
        if len(parts) >= 2:
            padded = parts[1] + "=" * ((4 - len(parts[1]) % 4) % 4)
            decoded = base64.urlsafe_b64decode(padded)
            return json.loads(decoded)
    except Exception:
        pass
    return {}


def resolve_credentials(
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    app_session: Optional[str] = None,
    user_id: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None,
    api_key: Optional[str] = None,
) -> Tuple[str, str, str, str, str, str, Optional[str]]:
    """
    Resolve credentials following priority:
    1. Direct tool arguments
    2. Context variables (per-request tenant headers/query params)
    3. Environment variables
    """
    _load_env_if_missing()

    final_access = (
        (access_token or "").strip()
        or (current_himalayas_access_token.get() or "").strip()
        or os.environ.get("HIMALAYAS_ACCESS_TOKEN", "").strip()
        or os.environ.get("HIMALAYAS_TOKEN", "").strip()
    )

    final_refresh = (
        (refresh_token or "").strip()
        or (current_himalayas_refresh_token.get() or "").strip()
        or os.environ.get("HIMALAYAS_REFRESH_TOKEN", "").strip()
    )

    final_session = (
        (app_session or "").strip()
        or (current_himalayas_app_session.get() or "").strip()
        or os.environ.get("HIMALAYAS_APP_SESSION", "").strip()
    )

    final_user_id = (
        (user_id or "").strip()
        or (current_himalayas_user_id.get() or "").strip()
        or os.environ.get("HIMALAYAS_USER_ID", "").strip()
    )

    final_cf = (
        (cf_clearance or "").strip()
        or (current_himalayas_cf_clearance.get() or "").strip()
        or os.environ.get("HIMALAYAS_CF_CLEARANCE", "").strip()
        or os.environ.get("CF_CLEARANCE", "").strip()
    )

    final_ua = (
        (user_agent or "").strip()
        or (current_himalayas_user_agent.get() or "").strip()
        or os.environ.get("HIMALAYAS_USER_AGENT", "").strip()
        or DEFAULT_USER_AGENT
    )

    final_api_key = (
        (api_key or "").strip()
        or (current_himalayas_api_key.get() or "").strip()
        or os.environ.get("HIMALAYAS_API_KEY", "").strip()
        or None
    )

    return (
        final_access,
        final_refresh,
        final_session,
        final_user_id,
        final_cf,
        final_ua,
        final_api_key,
    )


def is_authenticated() -> bool:
    """Return True if active access token is present and not expired."""
    access_token, _, _, _, _, _, _ = resolve_credentials()
    if not access_token:
        return False
    payload = decode_jwt_payload(access_token)
    exp = payload.get("exp")
    if exp and isinstance(exp, (int, float)):
        return exp > time.time()
    return bool(access_token)


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Himalayas session details."""
    access_token, refresh_token, session, user_id, cf, ua, api_key = resolve_credentials()
    payload = decode_jwt_payload(access_token) if access_token else {}
    exp = payload.get("exp")
    now = time.time()
    is_expired = bool(exp and exp < now)

    talent = payload.get("talent") or {}
    talent_guid = talent.get("guid") or ""

    return {
        "authenticated": bool(access_token and not is_expired),
        "has_keys": bool(access_token or api_key),
        "is_expired": is_expired,
        "user_id": payload.get("id") or payload.get("user_id"),
        "first_name": payload.get("firstName"),
        "last_name": payload.get("lastName"),
        "email": payload.get("email"),
        "talent_guid": talent_guid,
        "talent_handle": talent_guid.replace("https://himalayas.app/", "") if talent_guid else None,
        "exp_timestamp": exp,
        "api_key_configured": bool(api_key),
        "cookies_present": {
            "himalayas_access_token": bool(access_token),
            "himalayas_refresh_token": bool(refresh_token),
            "himalayas_app_session": bool(session),
            "user.id": bool(user_id),
            "cf_clearance": bool(cf),
            "user_agent": bool(ua),
        },
    }


def build_cookies_dict(
    access_token: Optional[str] = None,
    refresh_token: Optional[str] = None,
    app_session: Optional[str] = None,
    user_id: Optional[str] = None,
    cf_clearance: Optional[str] = None,
) -> Dict[str, str]:
    """Construct cookie dictionary for HTTP requests."""
    acc, ref, sess, uid, cf, _, _ = resolve_credentials(
        access_token, refresh_token, app_session, user_id, cf_clearance
    )
    cookies: Dict[str, str] = {}
    if acc:
        cookies["himalayas_access_token"] = acc
    if ref:
        cookies["himalayas_refresh_token"] = ref
    if sess:
        cookies["himalayas_app_session"] = sess
    if uid:
        cookies["user.id"] = uid
    if cf:
        cookies["cf_clearance"] = cf
    return cookies


def build_headers_dict(
    user_agent: Optional[str] = None,
    api_key: Optional[str] = None,
    include_referer: bool = True,
) -> Dict[str, str]:
    """Construct headers dictionary for Himalayas requests."""
    _, _, _, _, _, ua, resolved_key = resolve_credentials(user_agent=user_agent, api_key=api_key)
    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/html, */*",
    }
    if include_referer:
        headers["Referer"] = "https://himalayas.app/"
        headers["Origin"] = "https://himalayas.app"
    if resolved_key:
        headers["Authorization"] = f"Bearer {resolved_key}"
    return headers
