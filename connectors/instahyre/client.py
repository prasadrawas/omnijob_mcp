"""
Instahyre API Client.
Encapsulates communication with Instahyre web services (Django REST APIs),
handling candidate profile management, matching opportunities, job search,
application pipeline, recruiter messages, and settings.
"""
import io
import json
import re
from pathlib import Path
from typing import Any, Dict, List, Optional, Tuple, Union
import httpx
from pypdf import PdfReader

from omnijob_mcp.connectors.instahyre import auth
from omnijob_mcp.core.cache import TTLCache

BASE_URL = "https://www.instahyre.com"
CACHE = TTLCache(default_ttl=120, max_size=500)


def execute_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    data: Optional[Dict[str, Any]] = None,
    files: Optional[Dict[str, Any]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None,
    referer: Optional[str] = None,
    timeout: float = 30.0
) -> Tuple[int, Dict[str, Any]]:
    """
    Execute an HTTP request to Instahyre with authentic session cookies,
    CSRF headers, and matching User-Agent.
    """
    sid, csrf, cf, ua = auth.resolve_credentials(sessionid, csrftoken, cf_clearance, user_agent)
    cookie_hdr = auth.build_cookie_header(sid, csrf, cf)

    headers = {
        "User-Agent": ua,
        "Accept": "application/json, text/plain, */*",
        "Cookie": cookie_hdr,
        "Referer": referer or f"{BASE_URL}/candidate/opportunities/?matching=true"
    }
    if csrf:
        headers["X-CSRFToken"] = csrf

    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"

    try:
        with httpx.Client(timeout=timeout) as client:
            resp = client.request(
                method=method.upper(),
                url=url,
                params=params,
                json=json_data,
                data=data,
                files=files,
                headers=headers,
                follow_redirects=False
            )

            if resp.status_code == 302:
                loc = resp.headers.get("Location", "")
                if "login" in loc:
                    return 401, {"error": "Authentication required or session expired (redirected to /login)", "statusCode": 401}
                return 302, {"location": loc, "statusCode": 302}

            if resp.status_code == 403:
                if "challenge" in resp.headers.get("cf-mitigated", "") or "Just a moment..." in resp.text:
                    return 403, {
                        "error": "Cloudflare bot challenge triggered. Please refresh cf_clearance and match user_agent.",
                        "statusCode": 403
                    }

            try:
                res_json = resp.json()
                return resp.status_code, res_json
            except Exception:
                return resp.status_code, {"raw_text": resp.text[:1000], "statusCode": resp.status_code}
    except Exception as exc:
        return 500, {"error": str(exc), "statusCode": 500}


def get_candidate_identity(
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[Optional[str], Optional[str], Optional[str]]:
    """
    Discover active candidate ID, user ID, and full name.
    Cached in TTLCache to avoid repeated discovery requests.
    Returns: (candidate_id, user_id, user_name)
    """
    cache_key = f"identity_{sessionid}_{cf_clearance}"
    cached = CACHE.get(cache_key)
    if cached:
        return cached

    info = auth.discover_candidate_info(sessionid, csrftoken, cf_clearance, user_agent)
    cid = info.get("candidate_id")
    uid = info.get("user_id")
    name = info.get("name")
    if cid:
        CACHE.set(cache_key, (cid, uid, name), ttl=600)
    return cid, uid, name


# =======================================================================
# 1. PROFILE & CANDIDATE LIFECYCLE
# =======================================================================

def get_candidate_profile(
    candidate_id: Optional[Union[int, str]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch comprehensive candidate profile: personal info, experience,
    skills, education, resume metadata, and Job Seeker Profile (JSP).
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id. Please provide valid session credentials."}

    cache_key = f"profile_{clean_id}"
    cached = CACHE.get(cache_key)
    if cached:
        return 200, cached

    status, res = execute_request(
        f"/api/v1/candidate_misc/profile/candidate/{clean_id}",
        method="GET",
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    if status == 200:
        CACHE.set(cache_key, res, ttl=180)
    return status, res


def update_candidate_profile(
    candidate_id: Optional[Union[int, str]] = None,
    personal: Optional[Dict[str, Any]] = None,
    jsp: Optional[Dict[str, Any]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Update candidate details (designation, company, experience, phone, skills, salary, location preferences).
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id for update."}

    results = {}
    last_status = 200

    if personal:
        status, res = execute_request(
            f"/api/v1/candidate_misc/profile/candidate/{clean_id}",
            method="PATCH",
            json_data=personal,
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )
        results["candidate"] = res
        last_status = status

    if jsp:
        # Fetch current profile to obtain JSP ID if not provided
        jsp_id = jsp.get("id")
        if not jsp_id:
            st, prof = get_candidate_profile(clean_id, sessionid, csrftoken, cf_clearance, user_agent)
            if st == 200 and "jsp" in prof and isinstance(prof["jsp"], dict):
                jsp_id = prof["jsp"].get("id")

        if jsp_id:
            status_jsp, res_jsp = execute_request(
                f"/api/v1/candidate_misc/profile/candidate_jsp/{jsp_id}",
                method="PATCH",
                json_data=jsp,
                sessionid=sessionid,
                csrftoken=csrftoken,
                cf_clearance=cf_clearance,
                user_agent=user_agent
            )
            results["jsp"] = res_jsp
            last_status = status_jsp
        else:
            results["jsp"] = {"warning": "Could not locate jsp_id to apply JSP preferences."}

    CACHE.invalidate(f"profile_{clean_id}")
    return last_status, results


def touch_profile_pulse(
    candidate_id: Optional[Union[int, str]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Refresh candidate activity timestamp and bump recruiter visibility ranking.
    Updates candidate modal check and seen activity flags.
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id."}

    payload = {
        "seen_active_check_modal_at": True
    }
    status, res = execute_request(
        f"/api/v1/candidate_misc/profile/candidate/{clean_id}",
        method="PATCH",
        json_data=payload,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    if status in (200, 202, 204):
        CACHE.invalidate(f"profile_{clean_id}")
        return 200, {
            "success": True,
            "message": "Candidate pulse updated successfully. Recruiter search ranking refreshed.",
            "candidate_id": clean_id
        }
    return status, res


def download_resume(
    resume_url: Optional[str] = None,
    candidate_id: Optional[Union[int, str]] = None,
    extract_text: bool = True,
    max_pages: int = 10,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch candidate resume metadata and optionally parse/extract text from the PDF.
    """
    target_url = resume_url
    if not target_url:
        st, prof = get_candidate_profile(candidate_id, sessionid, csrftoken, cf_clearance, user_agent)
        if st == 200 and "resume" in prof and isinstance(prof["resume"], dict):
            target_url = prof["resume"].get("pdf_file") or prof["resume"].get("url")

    if not target_url:
        return 404, {"error": "No resume URL found for candidate"}

    try:
        with httpx.Client(timeout=30.0) as client:
            resp = client.get(target_url)
            if resp.status_code != 200:
                return resp.status_code, {"error": f"Failed to download resume from {target_url}"}

            result_data = {
                "resume_url": target_url,
                "file_size_bytes": len(resp.content),
                "content_type": resp.headers.get("Content-Type", "application/pdf")
            }

            if extract_text:
                reader = PdfReader(io.BytesIO(resp.content))
                pages_text = []
                num_pages = min(len(reader.pages), max_pages)
                for i in range(num_pages):
                    text = reader.pages[i].extract_text() or ""
                    pages_text.append(text.strip())
                result_data["page_count"] = len(reader.pages)
                result_data["extracted_text"] = "\n\n--- Page Break ---\n\n".join(pages_text)

            return 200, result_data
    except Exception as exc:
        return 500, {"error": f"Error downloading/parsing resume: {exc}"}


def upload_resume(
    file_path: str,
    candidate_id: Optional[Union[int, str]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Upload a new resume PDF or DOCX file to Instahyre profile.
    """
    p = Path(file_path).resolve()
    if not p.exists() or not p.is_file():
        return 400, {"error": f"Resume file not found at path: {file_path}"}

    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id for resume upload."}

    try:
        with open(p, "rb") as f:
            file_bytes = f.read()

        files = {
            "resume": (p.name, file_bytes, "application/pdf")
        }
        form_data = {
            "candidate": f"/api/v1/candidate_misc/profile/limited_candidate/{clean_id}",
            "calculate_opps": "true"
        }

        status, res = execute_request(
            "/api/v1/candidate_misc/profile/resume/",
            method="POST",
            data=form_data,
            files=files,
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )
        if status in (200, 201):
            CACHE.invalidate(f"profile_{clean_id}")
        return status, res
    except Exception as exc:
        return 500, {"error": f"Error uploading resume: {exc}"}


# =======================================================================
# 2. MATCHING OPPORTUNITIES & JOB SEARCH
# =======================================================================

def get_matching_opportunities(
    limit: int = 30,
    offset: int = 0,
    interest_facet: int = 0,
    location: Optional[str] = None,
    job_functions: Optional[str] = None,
    job_categories: Optional[str] = None,
    companies: Optional[str] = None,
    company_size: Optional[str] = None,
    industry_type: Optional[str] = None,
    job_type: Optional[str] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch personalized curated matching opportunities feed from Instahyre.
    interest_facet: 0 = Matching (Undecided), 1 = Interested (Applied), 2 = Declined (Archived)
    """
    params = {
        "interest_facet": interest_facet,
        "limit": limit,
        "offset": offset,
        "location": location or "",
        "job_functions": job_functions or "",
        "job_categories": job_categories or "",
        "companies": companies or "",
        "company_size": company_size or "",
        "industry_type": industry_type or "",
        "job_type": job_type or ""
    }

    status, res = execute_request(
        "/api/v1/candidate_opportunities/candidate_matching",
        method="GET",
        params=params,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def search_jobs(
    query: Optional[str] = None,
    location: Optional[str] = None,
    job_functions: Optional[str] = None,
    limit: int = 30,
    offset: int = 0,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Search tech openings across Instahyre's entire job index (40,000+ jobs)
    or fetch personalized curated matching feed if query is omitted.
    """
    if not query:
        # Fall back to curated matching opportunities feed
        return get_matching_opportunities(
            limit=limit,
            offset=offset,
            interest_facet=0,
            location=location,
            job_functions=job_functions,
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )

    params: Dict[str, Any] = {
        "query": query,
        "limit": limit,
        "offset": offset
    }
    if location:
        params["locations"] = location
    if job_functions:
        params["job_functions"] = job_functions

    status, res = execute_request(
        "/api/v1/job_search",
        method="GET",
        params=params,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def get_job_details(
    job_id: Optional[Union[int, str]] = None,
    opportunity_url: Optional[str] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Inspect job description, company details, skills tags, and requirements.
    Resolves Schema.org JobPosting structured metadata from the job page.
    """
    target_path = opportunity_url
    if not target_path and job_id:
        target_path = f"/job-{job_id}/"

    if not target_path:
        return 400, {"error": "Either job_id or opportunity_url must be provided"}

    full_url = target_path if target_path.startswith("http") else f"{BASE_URL}{target_path}"

    sid, csrf, cf, ua = auth.resolve_credentials(sessionid, csrftoken, cf_clearance, user_agent)
    headers = {
        "User-Agent": ua,
        "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
        "Referer": f"{BASE_URL}/candidate/opportunities/?matching=true",
        "Cookie": auth.build_cookie_header(sid, csrf, cf)
    }

    try:
        with httpx.Client(timeout=25.0) as client:
            resp = client.get(full_url, headers=headers, follow_redirects=True)
            if resp.status_code != 200:
                return resp.status_code, {"error": f"Failed to retrieve job page at {full_url}"}

            html = resp.text
            # Extract Schema.org JobPosting JSON-LD
            postings = re.findall(r'<script[^>]*type=[\'\"]application/ld\+json[\'\"][^>]*>(.*?)</script>', html, re.DOTALL)
            job_posting = None
            for p in postings:
                if "JobPosting" in p:
                    try:
                        job_posting = json.loads(p.strip())
                        break
                    except Exception:
                        pass

            # Extract basic HTML identifiers
            m_pid = re.search(r'publicJobId\s*[:=]\s*[\'\"]?(\d+)', html)
            m_eid = re.search(r'employerId\s*[:=]\s*[\'\"]?(\d+)', html)

            data: Dict[str, Any] = {
                "url": str(resp.url),
                "job_id": job_id or (m_pid.group(1) if m_pid else None),
                "employer_id": m_eid.group(1) if m_eid else None,
                "job_posting": job_posting
            }

            if job_posting:
                data["title"] = job_posting.get("title")
                data["company_name"] = job_posting.get("identifier", {}).get("name")
                data["employment_type"] = job_posting.get("employmentType")
                data["locations"] = job_posting.get("jobLocation")
                data["description"] = job_posting.get("description")
                data["date_posted"] = job_posting.get("datePosted")

            return 200, data
    except Exception as exc:
        return 500, {"error": f"Error fetching job details: {exc}"}


# =======================================================================
# 3. APPLICATION PIPELINE & MATCHING ACTIONS
# =======================================================================

def apply_to_opportunity(
    job_id: Union[int, str],
    is_interested: bool = True,
    is_non_matching: bool = False,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Express interest (Apply) or decline (Pass) an opportunity.
    is_interested=True -> Applied
    is_interested=False -> Declined / Archived
    """
    payload = {
        "job_id": int(job_id) if str(job_id).isdigit() else job_id,
        "is_interested": is_interested
    }
    if is_non_matching:
        payload["is_non_matching_application"] = True

    status, res = execute_request(
        "/api/v1/candidate_opportunities/candidate_matching/apply/",
        method="POST",
        json_data=payload,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def apply_bulk(
    job_ids: List[Union[int, str]],
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Express interest / apply to multiple opportunities in a single operation.
    """
    clean_ids = [int(jid) if str(jid).isdigit() else jid for jid in job_ids]
    payload = {"job_ids": clean_ids}

    status, res = execute_request(
        "/api/v1/candidate_opportunities/candidate_matching/apply_bulk/",
        method="POST",
        json_data=payload,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def get_pipeline_metrics(
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch pipeline counts: total matching, applied, declined, top locations, and job functions.
    """
    status, res = execute_request(
        "/api/v1/candidate_opportunities/candidate_matching/fetch_filter_counts",
        method="GET",
        params={
            "interest_facet": 0,
            "companies": "",
            "company_size": "",
            "industry_type": "",
            "job_categories": "",
            "job_functions": "",
            "job_type": "",
            "location": ""
        },
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


# =======================================================================
# 4. ACCOUNT, PRIVACY & RECRUITER MESSAGING
# =======================================================================

def get_settings(
    candidate_id: Optional[Union[int, str]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch account settings, privacy preferences, and blocked companies list.
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id for settings."}

    status, res = execute_request(
        f"/api/v1/candidate_misc/settings/candidate_settings/{clean_id}",
        method="GET",
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def update_settings(
    candidate_id: Optional[Union[int, str]] = None,
    settings_data: Optional[Dict[str, Any]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Update candidate settings (blocked companies, privacy, notification preferences).
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id."}

    # Fetch current settings first to perform clean merge
    st, current = get_settings(clean_id, sessionid, csrftoken, cf_clearance, user_agent)
    payload = dict(current) if st == 200 and isinstance(current, dict) else {}
    if settings_data:
        payload.update(settings_data)

    status, res = execute_request(
        f"/api/v1/candidate_misc/settings/candidate_settings/{clean_id}",
        method="PUT",
        json_data=payload,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    return status, res


def block_or_unblock_company(
    company_name: str,
    action: str = "block",
    candidate_id: Optional[Union[int, str]] = None,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Add or remove a competitor company from the candidate's blocked companies list.
    """
    clean_id = candidate_id
    if not clean_id:
        cid, _, _ = get_candidate_identity(sessionid, csrftoken, cf_clearance, user_agent)
        clean_id = cid

    if not clean_id:
        return 400, {"error": "Could not determine candidate_id."}

    st, current_settings = get_settings(clean_id, sessionid, csrftoken, cf_clearance, user_agent)
    if st != 200 or not isinstance(current_settings, dict):
        return st, {"error": "Failed to fetch current settings before updating blocked companies"}

    blocked: List[str] = list(current_settings.get("companies_to_block", []))
    target = company_name.strip()

    if action == "block":
        if target not in blocked:
            blocked.append(target)
    elif action == "unblock":
        blocked = [c for c in blocked if c.lower() != target.lower()]

    current_settings["companies_to_block"] = blocked
    return update_settings(
        candidate_id=clean_id,
        settings_data=current_settings,
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )


def get_inbox_conversations(
    limit: int = 20,
    offset: int = 0,
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch recruiter conversations and unread message metrics.
    """
    status, res = execute_request(
        "/api/v1/inbox_page/candidate_conversation/",
        method="GET",
        params={"limit": limit, "offset": offset},
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )

    st_cnt, res_cnt = execute_request(
        "/api/v1/resume_modal/emails/message/message_count?unread=1",
        method="GET",
        sessionid=sessionid,
        csrftoken=csrftoken,
        cf_clearance=cf_clearance,
        user_agent=user_agent
    )
    unread_count = res_cnt.get("message_count", 0) if st_cnt == 200 and isinstance(res_cnt, dict) else 0

    if status == 200 and isinstance(res, dict):
        res["unread_message_count"] = unread_count
    return status, res


def get_taxonomy(
    taxonomy_type: str = "locations",
    sessionid: Optional[str] = None,
    csrftoken: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Fetch platform taxonomy options: 'locations', 'job_functions', or 'top_employers'.
    """
    clean_type = (taxonomy_type or "").lower().strip()
    if clean_type in ("locations", "location", "cities"):
        return execute_request(
            "/api/v1/candidate_misc/profile/candidate_locations/location_data",
            method="GET",
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )
    elif clean_type in ("job_functions", "functions", "roles"):
        return execute_request(
            "/api/v1/job_function",
            method="GET",
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )
    elif clean_type in ("top_employers", "branding_companies", "employers"):
        return execute_request(
            "/api/v1/employer_misc/employer_profile/anon_employer/branding_companies/",
            method="GET",
            sessionid=sessionid,
            csrftoken=csrftoken,
            cf_clearance=cf_clearance,
            user_agent=user_agent
        )
    else:
        return 400, {
            "error": f"Unsupported taxonomy_type '{taxonomy_type}'. Supported: 'locations', 'job_functions', 'top_employers'"
        }
