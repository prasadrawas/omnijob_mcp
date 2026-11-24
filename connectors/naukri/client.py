"""
HTTP REST client for Naukri CloudGateway APIs.
"""
import json
import urllib.request
import urllib.error
from typing import Tuple, Dict, Any, Optional

# Endpoints catalog
NAUKRI_BASE_URL = "https://www.naukri.com"
PROFILE_AGGREGATOR_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v2/users/self?expand_level=4"
PROFILE_MUTATE_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/fullprofiles"
DELETE_URL_TMPL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/{profile_id}/{resource_type}/{resource_id}"

DASHBOARD_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/dashboard"
INBOX_URL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/inbox/users/self/mails"
NOTIFY_URL = "https://www.naukri.com/recommendapi/v1/notify"
SALARY_LABELS_URL = "https://www.naukri.com/servicegateway-mynaukri/resman-aggregator-services/v0/users/self/fetchSalaryLabels"
BLOCKED_COMPANIES_URL = "https://www.naukri.com/servicegateway-mynaukri/settings-services/v0/user/self/blockedCompanies"
CENTRAL_ENTITY_URL = "https://www.naukri.com/servicegateway-central-services/central-entity-services/v0/entity"

RESUME_VALIDATE_URL = "https://filevalidation.naukri.com/file"
ADV_RESUME_URL_TMPL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/{profile_id}/advResume"
RESUME_DOWNLOAD_URL_TMPL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v1/users/self/profiles/{profile_id}/resume"
RESUME_FORM_KEY = "F51f8e7e54e205"
RESUME_FILE_KEY = "UUJbZ0Fi7JjgMr"

PHOTO_VALIDATE_URL = "https://filevalidation.naukri.com/file"
PROFILE_PHOTO_URL_TMPL = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/profiles/{profile_id}/photo"
PHOTO_FORM_KEY = "Fjb56fnotys359"

JOB_SEARCH_URL = "https://www.naukri.com/jobapi/v3/search"
JOB_APPLY_URL = "https://www.naukri.com/cloudgateway-jobapplication/apply-services/v1/apply"
JOB_DETAILS_URL_TMPL = "https://www.naukri.com/jobapi/v3/job/{job_id}"

DEFAULT_USER_AGENT = "Mozilla/5.0 (Macintosh; Intel Mac OS X 10.15; rv:135.0) Gecko/20100101 Firefox/135.0"


def get_headers(
    nauk_at: str,
    nauk_rt: str = "",
    content_type: Optional[str] = None,
    is_mutation: bool = False,
    app_id: str = "105",
    system_id: str = "Naukri",
    referer: str = "https://www.naukri.com/mnjuser/profile"
) -> Dict[str, str]:
    """Generate standardized HTTP headers for CloudGateway API requests."""
    cookie_parts = []
    if nauk_at:
        cookie_parts.append(f"nauk_at={nauk_at}")
    if nauk_rt:
        cookie_parts.append(f"nauk_rt={nauk_rt}")
    cookie_str = "; ".join(cookie_parts)

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Accept-Language": "en-US,en;q=0.5",
        "AppId": app_id,
        "SystemId": system_id,
        "appid": app_id,
        "systemid": system_id,
        "nauk_at": nauk_at,
        "client-id": "d3sk70p",
        "Referer": referer,
        "Origin": NAUKRI_BASE_URL
    }

    if cookie_str:
        headers["Cookie"] = cookie_str
    if nauk_at:
        headers["Authorization"] = f"Bearer {nauk_at}"
    if is_mutation:
        headers["X-Requested-With"] = "XMLHttpRequest"
        headers["X-HTTP-Method-Override"] = "PUT"
        headers["Content-Type"] = "application/json"
    elif content_type:
        headers["Content-Type"] = content_type

    return headers


def make_api_request(
    url: str,
    method: str = "GET",
    headers: Optional[Dict[str, str]] = None,
    data: Optional[bytes] = None,
    timeout: int = 20
) -> Tuple[int, Any]:
    """Execute an HTTP request with error decoding."""
    req_headers = headers or {}
    req = urllib.request.Request(url, data=data, headers=req_headers, method=method)

    try:
        with urllib.request.urlopen(req, timeout=timeout) as resp:
            body_bytes = resp.read()
            body_str = body_bytes.decode("utf-8", errors="replace")
            try:
                return resp.status, json.loads(body_str)
            except Exception:
                return resp.status, body_str
    except urllib.error.HTTPError as e:
        err_bytes = e.read()
        err_str = err_bytes.decode("utf-8", errors="replace")
        try:
            return e.code, json.loads(err_str)
        except Exception:
            return e.code, err_str
    except Exception as e:
        return 0, str(e)


def delete_subresource(
    profile_id: str,
    resource_type: str,
    resource_id: str,
    nauk_at: str,
    nauk_rt: str = ""
) -> Tuple[bool, Any]:
    """Delete a subresource using CloudGateway DELETE."""
    url = DELETE_URL_TMPL.format(
        profile_id=profile_id,
        resource_type=resource_type,
        resource_id=resource_id
    )
    headers = get_headers(
        nauk_at,
        nauk_rt,
        is_mutation=False,
        content_type="application/json"
    )
    headers["X-HTTP-Method-Override"] = "DELETE"
    headers["X-Requested-With"] = "XMLHttpRequest"

    status, data = make_api_request(url, method="POST", headers=headers, data=b"{}")
    success = status in (200, 204)
    return success, data
