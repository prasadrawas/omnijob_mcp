"""
Authentication management for naukri_mcp.
Supports multi-tenant credential resolution (Query Parameter -> HTTP Header -> Tool Argument -> Environment Variable -> .env)
and automated token refresh via Naukri's central login service using nauk_rt with in-memory caching.
"""
import os
import sys
import json
import base64
import time
import urllib.request
import urllib.error
import contextvars
from pathlib import Path
from typing import Tuple, Optional, Dict, Any


LOGIN_STATUS_URL = "https://www.naukri.com/central-login-services/v0/credentials/login-status"

# Context variables for per-request / per-session credential resolution
current_session_id: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_id", default="")
current_session_rt: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_rt", default="")
current_session_resume_url: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_resume_url", default="")
current_session_pdf_url: contextvars.ContextVar[str] = contextvars.ContextVar("current_session_pdf_url", default="")

# In-memory stores for multi-tenant sessions and token caching
# SESSION_STORE: session_id -> {"rt": str, "resume_url": str, "pdf_url": str, "created_at": float, "last_seen": float}
SESSION_STORE: Dict[str, Dict[str, Any]] = {}

# TOKEN_CACHE: rt -> {"at": str, "exp": int}
TOKEN_CACHE: Dict[str, Dict[str, Any]] = {}


def clean_stale_sessions(max_age_seconds: int = 86400) -> None:
    """Purge sessions inactive for longer than max_age_seconds (default: 24h)."""
    now = time.time()
    stale_keys = [
        sid for sid, data in SESSION_STORE.items()
        if now - float(data.get("last_seen", data.get("created_at", now))) > max_age_seconds
    ]
    for sid in stale_keys:
        SESSION_STORE.pop(sid, None)


def decode_jwt_exp(token: str) -> int:
    """Decode expiration timestamp (exp) from a JWT token safely without external libraries."""
    if not token or "." not in token:
        return 0
    try:
        parts = token.split(".")
        if len(parts) < 2:
            return 0
        payload_b64 = parts[1] + "=="
        payload = json.loads(base64.urlsafe_b64decode(payload_b64.encode("utf-8")).decode("utf-8"))
        return int(payload.get("exp", 0))
    except Exception:
        return 0


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
    """Return True if Naukri tokens are valid."""
    try:
        at, _ = resolve_auth_tokens()
        return bool(at)
    except Exception:
        return False


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Naukri authentication status."""
    try:
        at, rt = resolve_auth_tokens()
        exp = decode_jwt_exp(at)
        return {
            "authenticated": True,
            "has_keys": bool(rt or at),
            "access_token_exp": exp,
            "cookies_present": {
                "NAUK_AT": bool(at),
                "NAUK_RT": bool(rt),
            },
        }
    except Exception as e:
        return {
            "authenticated": False,
            "has_keys": bool(os.getenv("NAUK_RT") or os.getenv("NAUK_AT")),
            "error": str(e),
        }


def save_tokens_to_env(new_at: str, new_rt: Optional[str] = None) -> None:
    """Update .env file and environment variables with refreshed tokens if writable."""
    candidate_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parent.parent / ".env"
    ]
    target_path = None
    for p in candidate_paths:
        if p.exists():
            target_path = p
            break
    if not target_path:
        target_path = Path.cwd() / ".env"
        try:
            target_path.touch(mode=0o600)
        except Exception:
            pass

    lines = []
    has_at = False
    has_rt = False

    try:
        if target_path.exists():
            with open(target_path, "r", encoding="utf-8") as f:
                for line in f:
                    if new_at and line.startswith("NAUK_AT="):
                        lines.append(f"NAUK_AT={new_at}\n")
                        has_at = True
                    elif new_rt and line.startswith("NAUK_RT="):
                        lines.append(f"NAUK_RT={new_rt}\n")
                        has_rt = True
                    else:
                        lines.append(line)
            if new_at and not has_at:
                lines.append(f"NAUK_AT={new_at}\n")
            if new_rt and not has_rt:
                lines.append(f"NAUK_RT={new_rt}\n")

            with open(target_path, "w", encoding="utf-8") as f:
                f.writelines(lines)
    except Exception:
        pass

    if new_at:
        os.environ["NAUK_AT"] = new_at
    if new_rt:
        os.environ["NAUK_RT"] = new_rt


def refresh_token_via_nauk_rt(nauk_rt: str) -> Tuple[str, str]:
    """
    Query Naukri's central login service with nauk_rt to mint a fresh nauk_at JWT token.
    Caches the minted token in TOKEN_CACHE for non-blocking multi-tenant reuse.
    """
    clean_rt = (nauk_rt or "").strip()
    if not clean_rt:
        return "", ""

    headers = {
        "User-Agent": "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0",
        "Cookie": f"nauk_rt={clean_rt}",
        "AppId": "105",
        "SystemId": "jobseeker",
        "Content-Type": "application/json",
        "Accept": "application/json"
    }

    req = urllib.request.Request(LOGIN_STATUS_URL, headers=headers, method="GET")
    try:
        with urllib.request.urlopen(req, timeout=15) as resp:
            new_at, new_rt = "", ""
            set_cookies = resp.headers.get_all("Set-Cookie", [])
            for sc in set_cookies:
                if "nauk_at=" in sc:
                    new_at = sc.split("nauk_at=")[1].split(";")[0]
                if "nauk_rt=" in sc:
                    new_rt = sc.split("nauk_rt=")[1].split(";")[0]

            if new_at:
                exp = decode_jwt_exp(new_at)
                effective_rt = new_rt or clean_rt
                TOKEN_CACHE[clean_rt] = {"at": new_at, "exp": exp}
                if effective_rt != clean_rt:
                    TOKEN_CACHE[effective_rt] = {"at": new_at, "exp": exp}
                save_tokens_to_env(new_at, effective_rt)
                return new_at, effective_rt
    except Exception as e:
        sys.stderr.write(f"[auth] Failed to refresh token via login-status: {e}\n")

    return "", clean_rt


def resolve_auth_tokens(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Tuple[str, str]:
    """
    Resolve active authentication tokens in order of precedence:
    1. Explicit function arguments (`nauk_at`, `nauk_rt`).
    2. Multi-tenant session context (`current_session_rt.get()`).
    3. Environment variables / .env file (`NAUK_AT`, `NAUK_RT`).
    4. In-memory token cache (`TOKEN_CACHE`) for fast non-blocking reuse.
    5. Automated token refresh if expired using `nauk_rt`.

    Only prompts/raises if `nauk_rt` was never provided or has actually expired on Naukri.
    """
    load_env_file()
    now = int(time.time())

    # 1. Determine active refresh token candidate
    active_rt = (nauk_rt or "").strip()
    if not active_rt:
        active_rt = current_session_rt.get().strip()
    if not active_rt:
        active_rt = os.getenv("NAUK_RT", "").strip()

    # 2. Check explicit access token argument
    active_at = (nauk_at or "").strip()
    if active_at:
        exp = decode_jwt_exp(active_at)
        if exp > now + 30:
            return active_at, active_rt
        if active_rt:
            refreshed_at, refreshed_rt = refresh_token_via_nauk_rt(active_rt)
            if refreshed_at:
                return refreshed_at, refreshed_rt

    # 3. Check in-memory token cache for active_rt
    if active_rt:
        cached = TOKEN_CACHE.get(active_rt)
        if cached:
            c_at = str(cached.get("at", ""))
            c_exp = int(cached.get("exp", 0))
            if c_at and c_exp > now + 60:
                return c_at, active_rt

        # Not in cache or approaching expiry, trigger refresh via nauk_rt
        refreshed_at, refreshed_rt = refresh_token_via_nauk_rt(active_rt)
        if refreshed_at:
            return refreshed_at, refreshed_rt

        # If refresh failed and active_rt was provided, the refresh token has expired
        raise PermissionError(
            "Your Naukri session cookie (nauk_rt) has expired or is invalid. "
            "Please obtain a fresh 'nauk_rt' cookie from your browser on naukri.com "
            "(DevTools -> Storage/Application -> Cookies -> nauk_rt) and update your MCP configuration "
            "or provide it via the refresh_session_token tool."
        )

    # 4. Check environment NAUK_AT if no RT was found
    env_at = os.getenv("NAUK_AT", "").strip()
    if env_at:
        exp = decode_jwt_exp(env_at)
        if exp > now + 30:
            return env_at, active_rt

    # 5. No token or RT found anywhere
    raise PermissionError(
        "Naukri session token (nauk_rt) is required. "
        "Please provide your 'nauk_rt' cookie (found in browser DevTools -> Cookies on naukri.com) "
        "by calling 'refresh_session_token(nauk_rt=...)' or configure your MCP connector URL "
        "with '?rt=YOUR_NAUK_RT'."
    )
