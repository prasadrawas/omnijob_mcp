"""
Utility helpers for naukri_mcp:
Handles resolving local paths, remote HTTP URLs, and raw payload data.
"""
import os
import json
import base64
import urllib.request
import urllib.parse
from pathlib import Path
from typing import Any, Tuple, Dict, Optional, Union


def resolve_json_source(source: Optional[Union[str, Dict[str, Any]]] = None) -> Dict[str, Any]:
    """
    Resolve JSON data from:
    1. A Python dictionary directly.
    2. An HTTP/HTTPS URL (downloads and parses JSON).
    3. A local filesystem path.
    4. A raw JSON string.
    """
    if not source:
        from omnijob_mcp.connectors.naukri.auth import current_session_resume_url
        session_resume = current_session_resume_url.get().strip() or os.getenv("MASTER_RESUME_PATH", "").strip()
        if session_resume:
            return resolve_json_source(session_resume)
        return {}
    if isinstance(source, dict):
        return source
    if not isinstance(source, str):
        return {}

    trimmed = source.strip()
    if not trimmed:
        from omnijob_mcp.connectors.naukri.auth import current_session_resume_url
        session_resume = current_session_resume_url.get().strip() or os.getenv("MASTER_RESUME_PATH", "").strip()
        if session_resume:
            return resolve_json_source(session_resume)
        return {}

    # 1. Check if it's an HTTP/HTTPS URL
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        req = urllib.request.Request(
            trimmed,
            headers={"User-Agent": "Naukri-MCP/1.0"}
        )
        with urllib.request.urlopen(req, timeout=15) as resp:
            content = resp.read().decode("utf-8")
            data = json.loads(content)
            return data if isinstance(data, dict) else {}

    # 2. Check if it's an existing local file
    try:
        p = Path(trimmed)
        if p.exists() and p.is_file():
            with open(p, "r", encoding="utf-8") as f:
                data = json.load(f)
                return data if isinstance(data, dict) else {}
    except Exception:
        pass

    # 3. Check if it's a raw JSON string
    if (trimmed.startswith("{") and trimmed.endswith("}")) or (trimmed.startswith("[") and trimmed.endswith("]")):
        try:
            data = json.loads(trimmed)
            return data if isinstance(data, dict) else {}
        except Exception:
            pass

    return {}


def resolve_pdf_source(source: Optional[Union[str, bytes]] = None) -> Tuple[bytes, str]:
    """
    Resolve PDF binary bytes and filename from:
    1. Raw bytes.
    2. An HTTP/HTTPS URL (downloads binary).
    3. A local filesystem path.
    4. A base64-encoded string.
    5. Fallback to RESUME_PDF_PATH environment variable if source is None or empty.
    """
    if isinstance(source, bytes):
        return source, "resume.pdf"

    raw_str = source if isinstance(source, str) else ""
    if not raw_str:
        from omnijob_mcp.connectors.naukri.auth import current_session_pdf_url
        raw_str = current_session_pdf_url.get().strip() or os.getenv("RESUME_PDF_PATH", "").strip()
        if not raw_str:
            raise ValueError(
                "No PDF source provided and neither session resume PDF nor "
                "RESUME_PDF_PATH environment variable is set."
            )

    trimmed = raw_str.strip()

    # 1. Check if HTTP/HTTPS URL
    if trimmed.startswith("http://") or trimmed.startswith("https://"):
        parsed = urllib.parse.urlparse(trimmed)
        filename = os.path.basename(parsed.path) or "resume.pdf"
        if not filename.lower().endswith(".pdf"):
            filename = f"{filename}.pdf"

        req = urllib.request.Request(
            trimmed,
            headers={"User-Agent": "Naukri-MCP/1.0"}
        )
        with urllib.request.urlopen(req, timeout=25) as resp:
            return resp.read(), filename

    # 2. Check if local filesystem path
    try:
        p = Path(trimmed)
        if p.exists() and p.is_file():
            with open(p, "rb") as f:
                return f.read(), p.name
    except Exception:
        pass

    # 3. Check if base64 string
    try:
        # Strip data URL prefix if present (e.g. data:application/pdf;base64,...)
        if "base64," in trimmed:
            trimmed = trimmed.split("base64,")[-1]
        decoded = base64.b64decode(trimmed, validate=True)
        if decoded.startswith(b"%PDF"):
            return decoded, "resume.pdf"
    except Exception:
        pass

    raise ValueError(f"Could not resolve PDF binary from input source: '{raw_str[:60]}...'")
