"""
Candidate profile photo upload tools for naukri_mcp.
Enables uploading a candidate display photo (avatar/DP) to boost profile visibility.
"""
import base64
import io
import json
import os
import random
import string
import time
import urllib.request
import urllib.error
from pathlib import Path
from typing import Dict, Any, Optional, Union, Tuple

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    DEFAULT_USER_AGENT,
    PHOTO_FORM_KEY,
    PHOTO_VALIDATE_URL,
    PROFILE_PHOTO_URL_TMPL,
    get_headers,
    make_api_request
)
from omnijob_mcp.connectors.naukri.tools.profile import get_profile


def generate_default_avatar(initials: str = "PR") -> bytes:
    """Generate a clean professional 400x400 avatar JPEG using Pillow."""
    try:
        from PIL import Image, ImageDraw
        img = Image.new("RGB", (400, 400), color=(41, 128, 185))
        d = ImageDraw.Draw(img)
        # Inner circle
        d.ellipse([50, 50, 350, 350], fill=(236, 240, 241), outline=(52, 73, 94), width=6)
        # Text/initials
        d.text((150, 160), initials, fill=(44, 62, 80))
        buf = io.BytesIO()
        img.save(buf, format="JPEG", quality=95)
        return buf.getvalue()
    except Exception:
        # Fallback minimal JPEG header bytes
        buf = io.BytesIO()
        from PIL import Image
        img = Image.new("RGB", (400, 400), color=(52, 152, 219))
        img.save(buf, format="JPEG", quality=90)
        return buf.getvalue()


def resolve_image_source(source: Optional[Union[str, bytes, Path]] = None) -> Tuple[bytes, str]:
    """Resolve image source from local path, base64 string, raw bytes, or generate default avatar."""
    if not source:
        return generate_default_avatar("PR"), "avatar.jpg"

    if isinstance(source, bytes):
        return source, "photo.jpg"

    source_str = str(source).strip()
    if os.path.exists(source_str):
        with open(source_str, "rb") as f:
            return f.read(), Path(source_str).name

    # Check if base64 encoded
    if len(source_str) > 100 and (source_str.startswith("data:image") or " " not in source_str):
        try:
            b64_data = source_str.split(",")[-1]
            return base64.b64decode(b64_data), "photo.jpg"
        except Exception:
            pass

    return generate_default_avatar("PR"), "avatar.jpg"


def upload_photo(
    source: Optional[Union[str, bytes]] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Upload a professional profile photo / display avatar to the candidate's Naukri profile.
    Boosts profile completeness by 5% and elevates recruiter search visibility.

    :param source: Optional local image file path (JPEG/PNG), base64 string, or raw bytes.
                   If omitted, generates a high-quality 400x400 professional avatar JPEG automatically.
    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve candidate profile ID."}

    img_bytes, filename = resolve_image_source(source)
    file_size = len(img_bytes)

    # Step 1: Upload to file validation
    chars = string.ascii_letters + string.digits
    file_key = "U" + "".join(random.choice(chars) for _ in range(13))
    form_key = PHOTO_FORM_KEY
    boundary = f"----geckoformboundary{int(time.time()*1000)}"

    content_type = "image/png" if filename.lower().endswith(".png") else "image/jpeg"

    body = (
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="formKey"\r\n\r\n{form_key}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'
        f"Content-Type: {content_type}\r\n\r\n"
    ).encode("utf-8") + img_bytes + (
        f"\r\n--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileName"\r\n\r\n{filename}\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="uploadCallback"\r\n\r\ntrue\r\n'
        f"--{boundary}\r\n"
        f'Content-Disposition: form-data; name="fileKey"\r\n\r\n{file_key}\r\n'
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
        req = urllib.request.Request(PHOTO_VALIDATE_URL, data=body, headers=file_headers, method="POST")
        with urllib.request.urlopen(req, timeout=25) as resp:
            val_raw = resp.read().decode("utf-8")
            _ = json.loads(val_raw)
    except urllib.error.HTTPError as e:
        err_msg = e.read().decode("utf-8", errors="ignore")
        return {"status": "error", "http_status": e.code, "message": f"Photo validation failed: {err_msg}"}
    except Exception as e:
        return {"status": "error", "message": f"Photo validation request failed: {e}"}

    # Step 2: Attach to profile photo endpoint
    photo_attach_url = PROFILE_PHOTO_URL_TMPL.format(profile_id=pid)
    attach_payload = {"photo": {"fileKey": file_key, "formKey": form_key}}
    attach_headers = get_headers(at, rt, content_type="application/json", is_mutation=False, app_id="105", system_id="js")

    status, attach_resp = make_api_request(
        photo_attach_url,
        method="POST",
        headers=attach_headers,
        data=json.dumps(attach_payload).encode("utf-8")
    )

    if status in (200, 201, 204):
        return {
            "status": "success",
            "message": "Profile photo uploaded and attached successfully.",
            "filename": filename,
            "file_size_bytes": file_size,
            "file_key": file_key,
            "profile_id": pid
        }

    return {
        "status": "error",
        "http_status": status,
        "message": "Failed to attach photo to candidate profile.",
        "details": attach_resp
    }


def delete_photo(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete candidate profile display photo.
    CAUTION: This permanently deletes the photo from the Naukri candidate profile.

    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    photo_url = PROFILE_PHOTO_URL_TMPL.format(profile_id=pid)
    headers = get_headers(at, rt, content_type="application/json", is_mutation=False, app_id="105", system_id="js")
    headers["X-HTTP-Method-Override"] = "DELETE"
    headers["X-Requested-With"] = "XMLHttpRequest"

    status, resp = make_api_request(photo_url, method="POST", headers=headers, data=b"{}")
    if status in (200, 204):
        return {
            "status": "success",
            "message": "Profile photo removed successfully.",
            "profile_id": pid
        }
    return {
        "status": "error",
        "http_status": status,
        "message": "Failed to remove profile photo.",
        "details": resp
    }

