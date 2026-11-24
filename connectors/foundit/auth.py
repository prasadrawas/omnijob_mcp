"""
Authentication and Session Store for Foundit (Monster India/APAC).
Handles Monster SSO tokens (MSSOAT, MSSOCLIENT, MSAL), JWT decoding,
Akamai Bot Manager cookies, and request header assembly.
"""
import os
import base64
import json
import time
from pathlib import Path
from typing import Dict, Any, Optional, Tuple

FOUNDIT_BASE_URL = "https://www.foundit.in"
DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36"


def _load_dotenv() -> None:
    """Load environment variables from .env files if available."""
    search_paths = [
        Path.cwd() / ".env",
        Path(__file__).resolve().parent / ".env",
        Path(__file__).resolve().parents[1] / ".env",
        Path(__file__).resolve().parents[2] / ".env",
        Path(__file__).resolve().parents[3] / ".env",
        Path(__file__).resolve().parents[3] / "foundit_mcp" / ".env",
    ]
    for p in search_paths:
        if p.is_file():
            try:
                with open(p, "r", encoding="utf-8") as f:
                    for line in f:
                        line = line.strip()
                        if line and not line.startswith("#") and "=" in line:
                            k, v = line.split("=", 1)
                            k = k.strip()
                            v = v.strip().strip("'\"")
                            if k not in os.environ:
                                os.environ[k] = v
            except Exception:
                pass
    # Re-read session store from updated os.environ
    for key, env_var in [
        ("mssoat", "FOUNDIT_MSSOAT"),
        ("mssoclient", "FOUNDIT_MSSOCLIENT"),
        ("msal", "FOUNDIT_MSAL"),
        ("abck", "FOUNDIT_ABCK"),
        ("bm_sz", "FOUNDIT_BM_SZ"),
        ("bm_sv", "FOUNDIT_BM_SV"),
        ("ak_bmsc", "FOUNDIT_AK_BMSC"),
    ]:
        if not SESSION_STORE.get(key) and os.environ.get(env_var):
            SESSION_STORE[key] = os.environ[env_var]


# Session Store (Runtime configurable)
SESSION_STORE: Dict[str, Optional[str]] = {
    "mssoat": os.environ.get("FOUNDIT_MSSOAT"),
    "mssoclient": os.environ.get("FOUNDIT_MSSOCLIENT"),
    "msal": os.environ.get("FOUNDIT_MSAL"),
    "abck": os.environ.get("FOUNDIT_ABCK"),
    "bm_sz": os.environ.get("FOUNDIT_BM_SZ"),
    "bm_sv": os.environ.get("FOUNDIT_BM_SV"),
    "ak_bmsc": os.environ.get("FOUNDIT_AK_BMSC"),
    "user_agent": os.environ.get("FOUNDIT_USER_AGENT") or DEFAULT_USER_AGENT,
}

_load_dotenv()


def get_credentials() -> Dict[str, Optional[str]]:
    """Retrieve currently active Foundit credentials."""
    return dict(SESSION_STORE)


def update_credentials(
    mssoat: Optional[str] = None,
    mssoclient: Optional[str] = None,
    msal: Optional[str] = None,
    abck: Optional[str] = None,
    bm_sz: Optional[str] = None,
    bm_sv: Optional[str] = None,
    ak_bmsc: Optional[str] = None,
    user_agent: Optional[str] = None,
) -> None:
    """Update session credentials at runtime."""
    if mssoat is not None:
        SESSION_STORE["mssoat"] = mssoat.strip()
    if mssoclient is not None:
        SESSION_STORE["mssoclient"] = mssoclient.strip()
    if msal is not None:
        SESSION_STORE["msal"] = msal.strip()
    if abck is not None:
        SESSION_STORE["abck"] = abck.strip()
    if bm_sz is not None:
        SESSION_STORE["bm_sz"] = bm_sz.strip()
    if bm_sv is not None:
        SESSION_STORE["bm_sv"] = bm_sv.strip()
    if ak_bmsc is not None:
        SESSION_STORE["ak_bmsc"] = ak_bmsc.strip()
    if user_agent is not None:
        SESSION_STORE["user_agent"] = user_agent.strip()


def decode_mssoat_token(mssoat_str: Optional[str] = None) -> Dict[str, Any]:
    """
    Extract and decode the nested JWT payload from MSSOAT.
    Foundit formats MSSOAT as '<base64_encoded_jwt>::bearer:<timestamp>:'.
    """
    token_val = mssoat_str or SESSION_STORE.get("mssoat")
    if not token_val:
        return {"valid": False, "error": "MSSOAT token is missing"}

    try:
        raw_token = token_val.split("::")[0].strip()
        # Decode outer base64 to obtain standard JWT string
        decoded_jwt = base64.b64decode(raw_token + "==").decode("utf-8")
        parts = decoded_jwt.split(".")
        if len(parts) != 3:
            return {"valid": False, "error": f"Invalid JWT structure ({len(parts)} parts)"}

        # Decode header and payload
        header = json.loads(base64.urlsafe_b64decode(parts[0] + "==").decode("utf-8"))
        payload = json.loads(base64.urlsafe_b64decode(parts[1] + "==").decode("utf-8"))

        exp_timestamp = payload.get("exp", 0)
        is_expired = time.time() > exp_timestamp if exp_timestamp else False

        return {
            "valid": True,
            "header": header,
            "payload": payload,
            "uuid": payload.get("uuid") or payload.get("user_name"),
            "user_type": payload.get("user_type"),
            "authorities": payload.get("authorities", []),
            "client_id": payload.get("client_id"),
            "exp_timestamp": exp_timestamp,
            "is_expired": is_expired,
            "raw_jwt": decoded_jwt,
        }
    except Exception as e:
        return {"valid": False, "error": f"Failed to decode MSSOAT token: {str(e)}"}


def build_cookie_header() -> str:
    """Build the exact Cookie header string needed for Foundit requests."""
    store = SESSION_STORE
    cookies = []

    if store.get("mssoat"):
        cookies.append(f"MSSOAT={store['mssoat']}")
    if store.get("mssoclient"):
        cookies.append(f"MSSOCLIENT={store['mssoclient']}")
    if store.get("msal"):
        cookies.append(f"MSAL={store['msal']}")
    if store.get("abck"):
        cookies.append(f"_abck={store['abck']}")
    if store.get("bm_sz"):
        cookies.append(f"bm_sz={store['bm_sz']}")
    if store.get("bm_sv"):
        cookies.append(f"bm_sv={store['bm_sv']}")
    if store.get("ak_bmsc"):
        cookies.append(f"ak_bmsc={store['ak_bmsc']}")

    return "; ".join(cookies)


def build_headers(referer: str = f"{FOUNDIT_BASE_URL}/", content_type: Optional[str] = None) -> Dict[str, str]:
    """Assemble standard HTTP headers for Foundit API calls."""
    headers = {
        "User-Agent": SESSION_STORE.get("user_agent") or DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Cookie": build_cookie_header(),
        "Referer": referer,
        "Origin": FOUNDIT_BASE_URL,
    }
    if content_type:
        headers["Content-Type"] = content_type
    return headers


def is_authenticated() -> bool:
    """Return True if Foundit MSSOAT token is present and not expired."""
    jwt_info = decode_mssoat_token()
    return bool(jwt_info.get("valid") and not jwt_info.get("is_expired"))


def get_session_status() -> Dict[str, Any]:
    """Inspect and return Foundit authentication status."""
    creds = get_credentials()
    jwt_info = decode_mssoat_token()
    is_valid = bool(jwt_info.get("valid") and not jwt_info.get("is_expired"))
    return {
        "authenticated": is_valid,
        "has_keys": bool(creds.get("mssoat")),
        "is_expired": jwt_info.get("is_expired", False),
        "user_uuid": jwt_info.get("uuid"),
        "user_type": jwt_info.get("user_type"),
        "authorities": jwt_info.get("authorities", []),
        "exp_timestamp": jwt_info.get("exp_timestamp"),
        "cookies_present": {
            "MSSOAT": bool(creds.get("mssoat")),
            "MSSOCLIENT": bool(creds.get("mssoclient")),
            "MSAL": bool(creds.get("msal")),
            "_abck": bool(creds.get("abck")),
            "bm_sz": bool(creds.get("bm_sz")),
            "bm_sv": bool(creds.get("bm_sv")),
            "ak_bmsc": bool(creds.get("ak_bmsc")),
        },
    }

