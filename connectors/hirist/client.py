"""
HTTP REST client for Hirist Microservice APIs (Gladiator Gateway).
"""
import json
import time
import uuid
import threading
from pathlib import Path
import urllib.parse
from typing import Tuple, Dict, Any, Optional, List, Union

import httpx

from omnijob_mcp.connectors.hirist.auth import build_cookie_header, resolve_credentials, refresh_hirist_token
from omnijob_mcp.core.cache import TTLCache

CACHE = TTLCache(default_ttl=180, max_size=500)

GLADIATOR_BASE_URL = "https://gladiator.hirist.tech"
AUTH_VALIDATE_URL = f"{GLADIATOR_BASE_URL}/auth/validate"
USER_BASE_URL = f"{GLADIATOR_BASE_URL}/user"
JOB_BASE_URL = f"{GLADIATOR_BASE_URL}/job"
MEDIA_BASE_URL = f"{GLADIATOR_BASE_URL}/media"

DEFAULT_USER_AGENT = (
    "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) AppleWebKit/537.36 "
    "(KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
)

# Concurrency limiter: Allow max 4 simultaneous requests to upstream Hirist API
CONCURRENCY_SEMAPHORE = threading.Semaphore(4)

# Persistent HTTP Client with Connection Pooling & Keep-Alive
# Connect timeout 3.0s, read timeout 6.5s to respond before Gemini Web's 8-10s cutoff
_HTTP_CLIENT = httpx.Client(
    timeout=httpx.Timeout(connect=3.0, read=6.5, write=6.5, pool=6.5),
    limits=httpx.Limits(max_connections=25, max_keepalive_connections=15, keepalive_expiry=30.0),
    follow_redirects=True
)


def get_headers(
    token: str,
    phpsessid: str = "",
    content_type: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None
) -> Dict[str, str]:
    """Generate standardized HTTP headers for Hirist API requests."""
    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Accept": "application/json, text/plain, */*",
        "Origin": "https://www.hirist.tech",
        "Referer": "https://www.hirist.tech/",
        "Cache-Control": "no-cache"
    }
    cookie_header = build_cookie_header(token, phpsessid)
    if cookie_header:
        headers["Cookie"] = cookie_header
    if content_type:
        headers["Content-Type"] = content_type
    if extra_headers:
        headers.update(extra_headers)
    return headers


def execute_request(
    url: str,
    method: str = "GET",
    token: Optional[str] = None,
    phpsessid: Optional[str] = None,
    data: Optional[Union[Dict[str, Any], bytes, str]] = None,
    params: Optional[Dict[str, Any]] = None,
    content_type: Optional[str] = None,
    extra_headers: Optional[Dict[str, str]] = None,
    timeout: float = 6.5,
    auto_refresh: bool = True
) -> Tuple[int, Dict[str, Any]]:
    """
    Execute an HTTP request against Hirist API and return (status_code, json_body).
    Uses persistent connection pooling, capped timeouts (6.5s) to avoid client drops,
    and automatically retries once on 401 or 406 by auto-refreshing HIRIST_CK1 via Gladiator Auth.
    """
    resolved_token, resolved_phpsessid = resolve_credentials(token, phpsessid)

    clean_params = None
    if params:
        clean_params = {k: v for k, v in params.items() if v is not None}

    body_bytes = None
    default_content_type = content_type

    if data is not None:
        if isinstance(data, dict):
            if default_content_type == "application/x-www-form-urlencoded":
                body_bytes = urllib.parse.urlencode(data).encode("utf-8")
            else:
                default_content_type = "application/json"
                body_bytes = json.dumps(data).encode("utf-8")
        elif isinstance(data, str):
            body_bytes = data.encode("utf-8")
        elif isinstance(data, bytes):
            body_bytes = data

    headers = get_headers(
        token=resolved_token,
        phpsessid=resolved_phpsessid,
        content_type=default_content_type,
        extra_headers=extra_headers
    )

    try:
        with CONCURRENCY_SEMAPHORE:
            resp = _HTTP_CLIENT.request(
                method=method,
                url=url,
                params=clean_params,
                content=body_bytes,
                headers=headers,
                timeout=timeout
            )
            status_code = resp.status_code
            try:
                json_data = resp.json()
            except Exception:
                json_data = {"raw": resp.text}

            # Auto-refresh session token on 401 or 406 (expired JWT)
            if auto_refresh and status_code in (401, 406) and "/auth/refresh" not in url:
                new_token, _ = refresh_hirist_token(phpsessid_override=resolved_phpsessid)
                if new_token:
                    return execute_request(
                        url=url,
                        method=method,
                        token=new_token,
                        phpsessid=resolved_phpsessid,
                        data=data,
                        params=params,
                        content_type=content_type,
                        extra_headers=extra_headers,
                        timeout=timeout,
                        auto_refresh=False
                    )

            return status_code, json_data

    except httpx.TimeoutException:
        return 504, {
            "status": "timeout",
            "error": f"Upstream request to Hirist timed out after {timeout}s. Please retry or run actions sequentially.",
            "statusCode": 504
        }
    except httpx.HTTPError as e:
        return 502, {"error": f"Upstream HTTP error: {str(e)}", "statusCode": 502}
    except Exception as e:
        return 500, {"error": str(e), "statusCode": 500}


# ---------------------------------------------------------------------------
# CORE CLIENT METHODS
# ---------------------------------------------------------------------------

SCHEMA_FIELD_MAP = {
    "pd": {
        "picPath": "a1", "name": "a2", "gender": "a3", "dob": "a4",
        "currentLocation": "a5", "preferredLocations": "a6", "phone": "a7",
        "countryCode": "a8", "industry": "a9", "careerObjective": "i3",
        "functionalArea": "b1", "noticePeriod": "b2", "expYear": "b3",
        "expMonth": "b4", "currentCtc": "b5", "currentSalary": "h9",
        "confidential": "b6", "expectedCtc": "b7", "expectedSalary": "i1",
        "negotiable": "b8", "resumePath": "b9", "currentOrganization": "c2",
        "fresher": "j6", "linkedin": "j7", "currentDesignation": "j2",
        "skills": "s1"
    },
    "we": {
        "designation": "c1", "organization": "c2", "fromExpMonth": "c3",
        "fromExpYear": "c4", "toExpMonth": "c5", "toExpYear": "c6",
        "isCurrent": "c7", "salary": "c8", "wantToRejoin": "g7",
        "status": "g6", "description": "i4", "city": "i5"
    },
    "ed": {
        "institute": "c9", "degree": "d1", "courseType": "d2",
        "batchFrom": "d3", "batchTo": "d4", "isPrimary": "d5",
        "status": "h1", "specialization": "j3", "description": "i6"
    },
    "ai": {
        "about": "e7", "handleTeam": "f2", "github": "k2",
        "linkedin": "h6", "facebook": "h7", "twitter": "h8",
        "maritalStatus": "f9", "careerBreak": "g3", "roleAndResponsibility": "l5"
    },
    "co": {
        "course": "d6", "institute": "d7", "fromExpYear": "e1",
        "toExpYear": "e3", "status": "h2", "description": "j5"
    }
}


def validate_session(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Validate current candidate session."""
    return execute_request(AUTH_VALIDATE_URL, method="GET", token=token)


def get_profile(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch complete candidate profile schema (cached in memory for 60s)."""
    resolved_token, _ = resolve_credentials(token)
    cache_key = f"profile:{resolved_token[-16:] if resolved_token else 'default'}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    status, res = execute_request(f"{USER_BASE_URL}/profile", method="GET", token=token, params={"apply": "true"})
    if status == 200:
        CACHE.set(cache_key, res, ttl=60)
    return status, res


def get_full_profile_v2(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch structured multi-section profile with all sections (pd, we, ed, rd, ai, atr) (cached for 60s)."""
    resolved_token, _ = resolve_credentials(token)
    cache_key = f"profile_v2:{resolved_token[-16:] if resolved_token else 'default'}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    status, res = execute_request(f"{USER_BASE_URL}/profile/v2", method="GET", token=token, params={"fields": "11111111"})
    if status == 200:
        CACHE.set(cache_key, res, ttl=60)
    return status, res


def update_profile_section(
    section: str,
    payload_data: Dict[str, Any],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Update a profile section (pd, we, ed, ai, co) using Hirist's schema-validated mapping.
    Automatically generates infoString with the mapped field keys.
    Invalidates profile and skills cache upon successful update.
    """
    field_map = SCHEMA_FIELD_MAP.get(section, {})
    keys_present = [field_map[k] for k in payload_data if k in field_map]
    info_string = "".join(keys_present) if keys_present else "default"

    body: Dict[str, Any] = dict(payload_data)
    body["infoString"] = info_string
    body["requiredString"] = ""

    status, res = execute_request(
        f"{USER_BASE_URL}/profile/v2",
        method="POST",
        token=token,
        data={section: body}
    )
    if status == 200:
        CACHE.invalidate("profile")
        CACHE.invalidate("skills")
    return status, res


def update_personal_details(
    name: Optional[str] = None,
    current_designation: Optional[str] = None,
    current_organization: Optional[str] = None,
    exp_year: Optional[int] = None,
    exp_month: Optional[int] = None,
    current_ctc: Optional[str] = None,
    expected_ctc: Optional[str] = None,
    notice_period: Optional[Union[int, str]] = None,
    phone: Optional[Union[int, str]] = None,
    current_location: Optional[str] = None,
    linkedin: Optional[str] = None,
    career_objective: Optional[str] = None,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Update candidate personal & career details."""
    data: Dict[str, Any] = {}
    if name is not None:
        data["name"] = name
    if current_designation is not None:
        data["currentDesignation"] = current_designation
    if current_organization is not None:
        data["currentOrganization"] = current_organization
    if exp_year is not None:
        data["expYear"] = exp_year
    if exp_month is not None:
        data["expMonth"] = exp_month
    if current_ctc is not None:
        data["currentCtc"] = str(current_ctc)
    if expected_ctc is not None:
        data["expectedCtc"] = str(expected_ctc)
    if notice_period is not None:
        data["noticePeriod"] = str(notice_period)
    if phone is not None:
        data["phone"] = int(phone) if str(phone).isdigit() else phone
    if current_location is not None:
        data["currentLocation"] = str(current_location)
    if linkedin is not None:
        data["linkedin"] = linkedin
    if career_objective is not None:
        data["careerObjective"] = career_objective

    return update_profile_section("pd", data, token=token)


def update_work_experience(
    experiences: List[Dict[str, Any]],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Update work experience history.
    Each item can contain: designation, organization, fromExpMonth, fromExpYear, toExpMonth, toExpYear, isCurrent, salary, description, city.
    """
    field_map = SCHEMA_FIELD_MAP.get("we", {})
    formatted_list = []
    for exp in experiences:
        item = dict(exp)
        if item.get("delete") is True or item.get("status") == 0:
            item["status"] = 0
            item["infoString"] = "g6"
            item["requiredString"] = ""
            item.pop("delete", None)
        else:
            if "status" not in item:
                item["status"] = 1
            item_keys = [field_map[k] for k in item if k in field_map]
            item["infoString"] = "".join(sorted(item_keys))
            item["requiredString"] = ""
        formatted_list.append(item)

    status, res = execute_request(
        f"{USER_BASE_URL}/profile/v2",
        method="POST",
        token=token,
        data={"we": formatted_list}
    )
    if status == 200:
        CACHE.invalidate("profile")
    return status, res


def delete_profile_item(
    item_type: str,
    item_id: Union[int, str],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Delete a specific profile item (work experience 'we'/'employments', education 'ed', course 'co') by ID.
    Sends status=0 with schema-mapped infoString (we='g6', ed='h1', co='h2') against /user/profile/v2.
    """
    clean_type = (item_type or "").lower().strip()
    type_map = {
        "we": ("we", "g6"),
        "work_experience": ("we", "g6"),
        "experience": ("we", "g6"),
        "experiences": ("we", "g6"),
        "employments": ("we", "g6"),
        "employment": ("we", "g6"),
        "ed": ("ed", "h1"),
        "education": ("ed", "h1"),
        "educations": ("ed", "h1"),
        "co": ("co", "h2"),
        "course": ("co", "h2"),
        "courses": ("co", "h2"),
        "certification": ("co", "h2"),
        "certifications": ("co", "h2"),
    }

    if clean_type not in type_map:
        return 400, {
            "error": f"Unsupported item_type '{item_type}'. Supported: 'work_experience' ('employments'), 'education', 'course'",
            "statusCode": 400
        }

    section_key, info_code = type_map[clean_type]
    clean_id = int(item_id) if str(item_id).isdigit() else item_id

    payload = {
        section_key: [{
            "id": clean_id,
            "status": 0,
            "infoString": info_code,
            "requiredString": ""
        }]
    }

    status, res = execute_request(
        f"{USER_BASE_URL}/profile/v2",
        method="POST",
        token=token,
        data=payload
    )
    if status == 200:
        CACHE.invalidate("profile")
    return status, res


def update_education(
    educations: List[Dict[str, Any]],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Update education history.
    Each item can contain: institute, degree, courseType (1=Full-time, 2=Part-time, 3=Correspondence), batchFrom, batchTo, specialization, description.
    """
    field_map = SCHEMA_FIELD_MAP.get("ed", {})
    formatted_list = []
    for edu in educations:
        item = dict(edu)
        if item.get("delete") is True or item.get("status") == 0:
            item["status"] = 0
            item["infoString"] = "h1"
            item["requiredString"] = ""
            item.pop("delete", None)
        else:
            if "status" not in item:
                item["status"] = 1
            item_keys = [field_map[k] for k in item if k in field_map]
            item["infoString"] = "".join(sorted(item_keys))
            item["requiredString"] = ""
        formatted_list.append(item)

    status, res = execute_request(
        f"{USER_BASE_URL}/profile/v2",
        method="POST",
        token=token,
        data={"ed": formatted_list}
    )
    if status == 200:
        CACHE.invalidate("profile")
    return status, res


def update_additional_info(
    about: Optional[str] = None,
    github: Optional[str] = None,
    linkedin: Optional[str] = None,
    handle_team: Optional[bool] = None,
    career_break: Optional[bool] = None,
    role_and_responsibility: Optional[str] = None,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Update additional profile information (about summary, GitHub, team handling, role & responsibility)."""
    data: Dict[str, Any] = {}
    if about is not None:
        data["about"] = about
    if github is not None:
        data["github"] = github
    if linkedin is not None:
        data["linkedin"] = linkedin
    if handle_team is not None:
        data["handleTeam"] = 1 if handle_team else 0
    if career_break is not None:
        data["careerBreak"] = 1 if career_break else 0
    if role_and_responsibility is not None:
        data["roleAndResponsibility"] = role_and_responsibility

    return update_profile_section("ai", data, token=token)


def get_skills(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch candidate key skills list (cached for 60s)."""
    resolved_token, _ = resolve_credentials(token)
    cache_key = f"skills:{resolved_token[-16:] if resolved_token else 'default'}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    status, res = execute_request(f"{USER_BASE_URL}/skills", method="GET", token=token)
    if status == 200:
        CACHE.set(cache_key, res, ttl=60)
    return status, res


def update_skills(skills: List[str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Update candidate skills array. Invalidates cached skills and profile."""
    status, res = execute_request(f"{USER_BASE_URL}/skills", method="POST", token=token, data={"skills": skills})
    if status == 200:
        CACHE.invalidate("skills")
        CACHE.invalidate("profile")
    return status, res


def get_cover_letter(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch candidate cover letter."""
    return execute_request(f"{USER_BASE_URL}/coverletter", method="GET", token=token)


def update_cover_letter(
    coverletter: str,
    include_coverletter: bool = True,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Update candidate cover letter."""
    data = {
        "coverletter": coverletter,
        "includeCoverletter": "1" if include_coverletter else "0"
    }
    return execute_request(
        f"{USER_BASE_URL}/coverletter",
        method="POST",
        token=token,
        data=data,
        content_type="application/x-www-form-urlencoded"
    )


def touch_profile_pulse(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """
    Touch candidate profile activity timestamp.
    Signals recruiters that the candidate is active today.
    """
    data = {"opt": "true", "isUpdate": "true"}
    return execute_request(
        f"{USER_BASE_URL}/updatestamp",
        method="POST",
        token=token,
        data=data,
        content_type="application/x-www-form-urlencoded"
    )


def get_job_feed(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch personalized candidate job feed."""
    return execute_request(
        f"{JOB_BASE_URL}/jobfeed",
        method="GET",
        token=token,
        extra_headers={"version": "2"}
    )


def search_jobs(
    query: str,
    size: int = 20,
    page: int = 1,
    min_exp: Optional[int] = None,
    max_exp: Optional[int] = None,
    location: Optional[str] = None,
    category_id: Optional[Union[int, str]] = None,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Search jobs across keywords, category, experience, and location."""
    params: Dict[str, Any] = {
        "query": query,
        "size": size,
        "page": page
    }
    if min_exp is not None:
        params["minexp"] = min_exp
    if max_exp is not None:
        params["maxexp"] = max_exp
    if location:
        params["city"] = location
    if category_id:
        params["category"] = category_id

    return execute_request(
        f"{JOB_BASE_URL}/search",
        method="GET",
        token=token,
        params=params,
        extra_headers={"version": "2"}
    )


def get_job_details(job_id: Union[int, str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch comprehensive details for a specific job (cached for 15 minutes)."""
    cache_key = f"job_details:{job_id}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    status, res = execute_request(
        f"{JOB_BASE_URL}/detail",
        method="GET",
        token=token,
        params={"jobcode": str(job_id)}
    )
    if status == 200:
        CACHE.set(cache_key, res, ttl=900)  # 15 minutes
    return status, res


def get_job_assessment(job_id: Union[int, str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch assessment / screening questions for a job (cached for 30 minutes)."""
    cache_key = f"job_assessment:{job_id}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    status, res = execute_request(
        f"{JOB_BASE_URL}/assessment",
        method="GET",
        token=token,
        params={"jobcode": str(job_id)}
    )
    if status == 200:
        CACHE.set(cache_key, res, ttl=1800)  # 30 minutes
    return status, res


def apply_to_job(
    job_id: Union[int, str],
    coverletter: Optional[str] = None,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Apply to a job on Hirist.
    Handles direct application, already-applied state, and screening assessment requirements.
    """
    payload: Dict[str, Any] = {}
    if coverletter is not None:
        payload["coverletter"] = coverletter
    status, res = execute_request(
        f"{JOB_BASE_URL}/apply",
        method="POST",
        token=token,
        params={"jobcode": str(job_id)},
        data=payload
    )

    if status == 200:
        return status, {
            "status": "applied",
            "job_id": job_id,
            "message": "Successfully Applied to Job",
            "details": res
        }

    err = res.get("error", {}) if isinstance(res, dict) else {}
    err_name = err.get("name", "") if isinstance(err, dict) else ""
    if err_name == "JOB_ALREADY_APPLIED" or "already applied" in str(res).lower():
        return 200, {
            "status": "already_applied",
            "job_id": job_id,
            "message": "Job is already applied",
            "details": res
        }
    if err_name == "ASSESSMENT_REQUIRED":
        return 400, {
            "status": "assessment_required",
            "job_id": job_id,
            "message": "Assessment/screening questions required. Use get_job_assessment to inspect questions.",
            "details": res
        }

    return status, res


def save_job(job_id: Union[int, str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Save/bookmark a job."""
    return execute_request(
        f"{JOB_BASE_URL}/save/",
        method="POST",
        token=token,
        params={"jobcode": str(job_id)},
        data={}
    )


def unsave_job(job_id: Union[int, str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Remove bookmark from a job."""
    return execute_request(
        f"{JOB_BASE_URL}/unsave/",
        method="POST",
        token=token,
        params={"jobcode": str(job_id)},
        data={}
    )


def do_follow_up(job_id: Union[int, str], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Send follow-up nudge to recruiter for an applied job."""
    return execute_request(
        f"{JOB_BASE_URL}/followup",
        method="POST",
        token=token,
        params={"jobcode": str(job_id)},
        data={}
    )


def get_applied_job_count(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch applied job count statistics."""
    return execute_request(f"{JOB_BASE_URL}/applied/count/", method="GET", token=token)


def get_pending_jobs_count(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch pending jobs count."""
    return execute_request(f"{JOB_BASE_URL}/pending-jobs/count", method="GET", token=token)


def get_user_settings(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch notification, privacy, and account settings."""
    return execute_request(f"{USER_BASE_URL}/settings", method="GET", token=token, params={"version": "v2"})


def update_user_settings(settings: Dict[str, Any], token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Update candidate account/notification settings."""
    return execute_request(
        f"{USER_BASE_URL}/settings",
        method="POST",
        token=token,
        data=settings,
        content_type="application/x-www-form-urlencoded"
    )


def get_blocked_companies(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch list of blocked employers."""
    return execute_request(f"{USER_BASE_URL}/settings/blocked-companies", method="GET", token=token)


def block_or_unblock_company(
    company_id: Union[int, str],
    block: bool = True,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Block or unblock a company from viewing candidate profile."""
    data = {"companyId": str(company_id), "action": "block" if block else "unblock"}
    return execute_request(
        f"{USER_BASE_URL}/settings/blocked-companies",
        method="POST",
        token=token,
        data=data,
        content_type="application/x-www-form-urlencoded"
    )


def suggest_companies(query: str, token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Auto-suggest companies by name (cached for 1 hour)."""
    q_norm = query.lower().strip()
    cache_key = f"suggest_co:{q_norm}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    clean_q = urllib.parse.quote(query).replace("%20", "%2520")
    status, res = execute_request(f"{USER_BASE_URL}/company/autosuggest?name={clean_q}", method="GET", token=token)
    if status == 200:
        CACHE.set(cache_key, res, ttl=3600)
    return status, res


def suggest_institutes(query: str, token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Auto-suggest colleges/universities (cached for 1 hour)."""
    q_norm = query.lower().strip()
    cache_key = f"suggest_inst:{q_norm}"
    cached = CACHE.get(cache_key)
    if cached is not None:
        return 200, cached

    clean_q = urllib.parse.quote(query)
    status, res = execute_request(f"{USER_BASE_URL}/suggest/institute?astext={clean_q}&limit=50", method="GET", token=token)
    if status == 200:
        CACHE.set(cache_key, res, ttl=3600)
    return status, res


def get_resume(token: Optional[str] = None) -> Tuple[int, Dict[str, Any]]:
    """Fetch candidate active resume S3 presigned URL and metadata."""
    return execute_request(f"{MEDIA_BASE_URL}/files", method="GET", token=token, params={"mediaTypes": "TextResume"})


def upload_resume(
    file_path: str,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Upload candidate resume document (PDF, DOCX) to Hirist.
    Automatically encodes file into multipart/form-data and posts to /media/files.
    """
    resolved_token, resolved_phpsessid = resolve_credentials(token)
    path_obj = Path(file_path).expanduser().resolve()
    if not path_obj.exists() or not path_obj.is_file():
        return 400, {"error": f"Resume file not found: {file_path}", "statusCode": 400}

    with open(path_obj, "rb") as f:
        file_bytes = f.read()

    boundary = f"----WebKitFormBoundary{uuid.uuid4().hex}"
    body = bytearray()

    # mediaType field
    body.extend(f"--{boundary}\r\n".encode("latin-1"))
    body.extend(b'Content-Disposition: form-data; name="mediaType"\r\n\r\n')
    body.extend(b"TextResume\r\n")

    # file field
    filename = path_obj.name
    content_type = "application/pdf" if filename.lower().endswith(".pdf") else "application/octet-stream"
    body.extend(f"--{boundary}\r\n".encode("latin-1"))
    body.extend(f'Content-Disposition: form-data; name="file"; filename="{filename}"\r\n'.encode("latin-1"))
    body.extend(f"Content-Type: {content_type}\r\n\r\n".encode("latin-1"))
    body.extend(file_bytes)
    body.extend(b"\r\n")

    # end boundary
    body.extend(f"--{boundary}--\r\n".encode("latin-1"))

    headers = {
        "User-Agent": DEFAULT_USER_AGENT,
        "Cookie": build_cookie_header(resolved_token, resolved_phpsessid),
        "Origin": "https://www.hirist.tech",
        "Referer": "https://www.hirist.tech/myprofile",
        "Content-Type": f"multipart/form-data; boundary={boundary}",
        "Content-Length": str(len(body)),
    }

    try:
        resp = _HTTP_CLIENT.post(
            f"{MEDIA_BASE_URL}/files",
            content=bytes(body),
            headers=headers,
            timeout=25.0
        )
        status_code = resp.status_code
        try:
            res_json = resp.json()
        except Exception:
            res_json = {"raw": resp.text}
        return status_code, res_json
    except httpx.TimeoutException:
        return 504, {"error": "Upload timed out after 25s", "statusCode": 504}
    except Exception as e:
        return 500, {"error": str(e), "statusCode": 500}


def download_resume_text(
    pdf_url: Optional[str] = None,
    max_pages: int = 10,
    token: Optional[str] = None
) -> Dict[str, Any]:
    """Download candidate resume and extract plain text."""
    target_url = (pdf_url or "").strip()
    if not target_url:
        st_res, res_res = get_resume(token=token)
        if st_res == 200 and isinstance(res_res, dict):
            target_url = res_res.get("data", {}).get("textResume", "")

    if not target_url:
        status, profile_data = get_profile(token=token)
        if status == 200 and isinstance(profile_data, dict):
            resume_path = profile_data.get("resumePath")
            return {
                "status": "partial",
                "message": f"Candidate has resume '{resume_path}' on Hirist. To extract full text, pass direct pdf_url.",
                "profile_resume_path": resume_path,
                "profile_id": profile_data.get("id"),
                "profile_name": profile_data.get("name")
            }
        return {"error": "No resume URL provided or found on profile."}

    import io
    try:
        resp = _HTTP_CLIENT.get(target_url, timeout=15.0)
        if resp.status_code != 200:
            return {"error": f"Failed to fetch PDF from URL, HTTP {resp.status_code}", "source_url": target_url}
        pdf_bytes = resp.content

        import pypdf
        reader = pypdf.PdfReader(io.BytesIO(pdf_bytes))
        num_pages = len(reader.pages)
        pages_to_read = min(num_pages, max_pages)

        extracted_text = []
        for i in range(pages_to_read):
            page_text = reader.pages[i].extract_text() or ""
            extracted_text.append(f"--- PAGE {i+1} ---\n{page_text.strip()}")

        return {
            "status": "success",
            "source_url": target_url,
            "total_pages": num_pages,
            "pages_extracted": pages_to_read,
            "resume_text": "\n\n".join(extracted_text)
        }
    except Exception as e:
        return {"error": f"Failed to parse resume PDF: {str(e)}", "source_url": target_url}


# ---------------------------------------------------------------------------
# BATCH OPERATION METHODS (Mitigate Rate Limits & UI Permission Queuing)
# ---------------------------------------------------------------------------

def batch_apply_jobs(
    job_ids: List[Union[int, str]],
    coverletter: Optional[str] = None,
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Apply to multiple jobs sequentially with safe spacing (200ms) to avoid throttling.
    Returns consolidated status report to resolve in a single MCP tool call.
    """
    results: Dict[str, Any] = {
        "total": len(job_ids),
        "applied": [],
        "already_applied": [],
        "assessment_required": [],
        "failed": []
    }
    for idx, jid in enumerate(job_ids):
        if idx > 0:
            time.sleep(0.2)
        code, res = apply_to_job(job_id=jid, coverletter=coverletter, token=token)
        status = res.get("status", "") if isinstance(res, dict) else ""
        if status == "applied":
            results["applied"].append({
                "job_id": jid,
                "message": res.get("message", "Successfully applied"),
                "details": res.get("details", {})
            })
        elif status == "already_applied":
            results["already_applied"].append({
                "job_id": jid,
                "message": res.get("message", "Job already applied")
            })
        elif status == "assessment_required":
            results["assessment_required"].append({
                "job_id": jid,
                "message": res.get("message", "Assessment required"),
                "requires_assessment": True
            })
        else:
            results["failed"].append({
                "job_id": jid,
                "status_code": code,
                "error": res.get("error") if isinstance(res, dict) else str(res)
            })
    return 200, results


def batch_get_job_details(
    job_ids: List[Union[int, str]],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch details for multiple jobs in a single call using cache and sequential requests.
    """
    jobs = []
    for idx, jid in enumerate(job_ids):
        if idx > 0:
            time.sleep(0.08)
        code, res = get_job_details(job_id=jid, token=token)
        if code == 200:
            jobs.append({"job_id": jid, "status": "success", "details": res})
        else:
            jobs.append({"job_id": jid, "status": "failed", "status_code": code, "error": res})
    return 200, {"total": len(job_ids), "jobs": jobs}


def batch_save_jobs(
    job_ids: List[Union[int, str]],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Bookmark/save multiple jobs on Hirist in a single batch.
    """
    saved = []
    failed = []
    for idx, jid in enumerate(job_ids):
        if idx > 0:
            time.sleep(0.1)
        code, res = save_job(job_id=jid, token=token)
        if code == 200:
            saved.append(jid)
        else:
            failed.append({"job_id": jid, "status_code": code, "error": res})
    return 200, {"total": len(job_ids), "saved": saved, "failed": failed}


def batch_follow_up(
    job_ids: List[Union[int, str]],
    token: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Send recruiter follow-up nudges for multiple applied jobs in one operation.
    """
    followed_up = []
    failed = []
    for idx, jid in enumerate(job_ids):
        if idx > 0:
            time.sleep(0.15)
        code, res = do_follow_up(job_id=jid, token=token)
        if code == 200:
            followed_up.append(jid)
        else:
            failed.append({"job_id": jid, "status_code": code, "error": res})
    return 200, {"total": len(job_ids), "followed_up": followed_up, "failed": failed}
