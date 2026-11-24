"""
Resume upload and validation tool for naukri_mcp.
Supports local file path, remote HTTP URL, or base64 PDF strings.
"""
import io
import time
import json
import base64
from pathlib import Path
import urllib.request
import urllib.error
from typing import Dict, Any, Optional

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    RESUME_VALIDATE_URL,
    ADV_RESUME_URL_TMPL,
    RESUME_DOWNLOAD_URL_TMPL,
    PROFILE_AGGREGATOR_URL,
    RESUME_FORM_KEY,
    RESUME_FILE_KEY,
    DEFAULT_USER_AGENT,
    get_headers,
    make_api_request
)
from omnijob_mcp.connectors.naukri.tools.profile import get_profile, extract_profile_id
from omnijob_mcp.connectors.naukri.utils import resolve_pdf_source


def upload_resume(
    source: Optional[str] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload and attach a PDF resume to candidate's Naukri profile.

    :param source: Local PDF file path, remote HTTP/HTTPS download URL, base64-encoded PDF string, or None (to use RESUME_PDF_PATH env).
    :param nauk_at: Optional bearer access token (falls back to NAUK_AT).
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve candidate profile ID."}

    try:
        pdf_bytes, filename = resolve_pdf_source(source)
    except Exception as e:
        return {"status": "error", "message": f"Failed to resolve PDF source: {e}"}

    file_size = len(pdf_bytes)

    # Step 1: Upload to filevalidation.naukri.com
    boundary = f"----geckoformboundary{int(time.time()*1000)}"
    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="formKey"\r\n\r\n{RESUME_FORM_KEY}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: application/pdf\r\n\r\n"
    ).encode("utf-8") + pdf_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileName"\r\n\r\n{filename}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="uploadCallback"\r\n\r\ntrue\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileKey"\r\n\r\n{RESUME_FILE_KEY}\r\n'
        f"--{boundary}--\r\n"
    ).encode("utf-8")

    file_headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/javascript, */*; q=0.01",
        "appId": "105",
        "systemId": "fileupload",
        "Origin": "https://www.naukri.com",
        "Referer": "https://www.naukri.com/",
        "Content-Type": f"multipart/form-data; boundary={boundary}"
    }

    try:
        req = urllib.request.Request(RESUME_VALIDATE_URL, data=body, headers=file_headers, method="POST")
        with urllib.request.urlopen(req, timeout=25) as resp:
            _ = resp.status
    except Exception as e:
        return {"status": "error", "message": f"Resume validation service upload failed: {e}"}

    # Step 2: Attach to advResume in CloudGateway
    adv_url = ADV_RESUME_URL_TMPL.format(profile_id=pid)
    attach_payload = {
        "textCV": {
            "formKey": RESUME_FORM_KEY,
            "fileKey": RESUME_FILE_KEY,
            "textCvContent": None
        }
    }
    attach_headers = get_headers(at, rt, is_mutation=True)
    attach_headers["AppId"] = "105"
    attach_headers["SystemId"] = "105"

    status, resp_data = make_api_request(
        adv_url,
        method="POST",
        headers=attach_headers,
        data=json.dumps(attach_payload).encode("utf-8")
    )

    if status in (200, 201):
        return {
            "status": "success",
            "filename": filename,
            "file_size_bytes": file_size,
            "message": "Resume uploaded and attached to Naukri profile successfully."
        }

    return {
        "status": "error",
        "http_status": status,
        "message": "Failed to attach validated resume to profile.",
        "details": resp_data
    }


def download_resume(
    output_path: Optional[str] = None,
    extract_text: bool = True,
    include_base64: bool = False,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Download and read the candidate's active PDF resume from Naukri.com.
    Returns the resume metadata, extracted full text content, and optionally saves the PDF to disk.

    :param output_path: Optional local filesystem path to write the downloaded PDF file.
    :param extract_text: Whether to extract and return plain text content from the PDF (default: True).
    :param include_base64: Whether to include base64-encoded PDF bytes in the response (default: False).
    :param nauk_at: Optional bearer access token (falls back to session or NAUK_AT).
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")

    # Step 1: Fetch profile to get profile ID and cvInfo metadata
    status, prof_data = make_api_request(PROFILE_AGGREGATOR_URL, method="GET", headers=headers)
    if status != 200 or not isinstance(prof_data, dict):
        return {"status": "error", "http_status": status, "message": f"Could not retrieve candidate profile: {prof_data}"}

    pid = extract_profile_id(prof_data)
    if not pid:
        return {"status": "error", "message": "Could not determine candidate profile ID."}

    p0 = prof_data.get("profile", [{}])[0] if prof_data.get("profile") else {}
    cv_info = p0.get("cvInfo", {})
    file_name = cv_info.get("fileName", "Resume")
    cv_format = cv_info.get("cvFormat", "pdf")
    full_filename = f"{file_name}.{cv_format}" if not file_name.endswith(f".{cv_format}") else file_name

    user = prof_data.get("user", {})
    username = user.get("userName", "") or user.get("email", "")
    dl_headers = dict(headers)
    if username:
        dl_headers["au-username"] = username

    # Step 2: Download raw resume bytes from Naukri CloudGateway
    dl_url = RESUME_DOWNLOAD_URL_TMPL.format(profile_id=pid)
    req = urllib.request.Request(dl_url, headers=dl_headers, method="GET")

    try:
        with urllib.request.urlopen(req, timeout=30) as resp:
            pdf_bytes = resp.read()
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {
            "status": "error",
            "http_status": e.code,
            "message": f"Failed to download resume from Naukri API: {e.reason}",
            "details": err_msg
        }
    except Exception as e:
        return {"status": "error", "message": f"Network error downloading resume: {e}"}

    if not pdf_bytes:
        return {"status": "error", "message": "Received empty resume file from Naukri."}

    # Step 3: Extract text if requested
    extracted_text = ""
    num_pages = 0
    if extract_text:
        try:
            import pypdf
            reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
            num_pages = len(reader.pages)
            extracted_text = "\n\n".join(page.extract_text() or "" for page in reader.pages).strip()
        except ImportError:
            extracted_text = "[pypdf not installed: install pypdf to enable text extraction]"
        except Exception as e:
            extracted_text = f"[Text extraction error: {e}]"

    # Step 4: Save to file if output_path is provided
    saved_path = None
    if output_path:
        try:
            p = Path(output_path).expanduser().resolve()
            p.parent.mkdir(parents=True, exist_ok=True)
            p.write_bytes(pdf_bytes)
            saved_path = str(p)
        except Exception as e:
            return {
                "status": "error",
                "message": f"Downloaded PDF successfully but failed to write to '{output_path}': {e}"
            }

    response: Dict[str, Any] = {
        "status": "success",
        "file_name": full_filename,
        "file_size_bytes": len(pdf_bytes),
        "num_pages": num_pages,
        "text": extracted_text,
        "cv_info": cv_info
    }
    if saved_path:
        response["saved_to"] = saved_path
    if include_base64:
        response["pdf_base64"] = base64.b64encode(pdf_bytes).decode("ascii")

    return response
