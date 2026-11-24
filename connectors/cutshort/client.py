"""
Cutshort Production API Client.
Encapsulates all REST calls for Profile Management, Jobs Search,
One-Click Apply Pipeline, and Recruiter Interactions.
"""
import re
import json
import time
from typing import Dict, Any, Optional, List, Union, Tuple
import httpx

from omnijob_mcp.core.cache import TTLCache
from omnijob_mcp.connectors.cutshort.auth import (
    resolve_credentials,
    build_request_headers,
    discover_candidate_info,
    DEFAULT_FIREFOX_UA
)

BASE_URL = "https://cutshort.io"
_global_cache = TTLCache(default_ttl_seconds=300)
_job_cache: Dict[str, Dict[str, Any]] = {}


def execute_request(
    endpoint: str,
    method: str = "GET",
    params: Optional[Dict[str, Any]] = None,
    json_data: Optional[Dict[str, Any]] = None,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None,
    timeout: float = 15.0
) -> Tuple[int, Dict[str, Any]]:
    """Execute authenticated HTTP request to Cutshort."""
    auth, cf, xsrf, cs, ua = resolve_credentials(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )

    url = endpoint if endpoint.startswith("http") else f"{BASE_URL}{endpoint}"
    headers = build_request_headers(auth, cf, xsrf, cs, ua)

    try:
        with httpx.Client(follow_redirects=True, headers=headers, timeout=timeout) as client:
            if method.upper() == "GET":
                resp = client.get(url, params=params)
            elif method.upper() == "POST":
                resp = client.post(url, params=params, json=json_data or {})
            elif method.upper() == "PUT":
                resp = client.put(url, params=params, json=json_data or {})
            elif method.upper() == "DELETE":
                resp = client.delete(url, params=params)
            else:
                return 405, {"error": f"Unsupported HTTP method: {method}"}

            try:
                data = resp.json()
            except Exception:
                data = {"text": resp.text, "status_code": resp.status_code}

            return resp.status_code, data

    except Exception as e:
        return 500, {"error": f"Request failed: {str(e)}"}


# ===========================================================================
# 1. PROFILE MANAGEMENT
# ===========================================================================

def get_candidate_profile(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Retrieve full candidate profile, talent card metadata, and preferences."""
    cache_key = "profile:full"
    cached = _global_cache.get(cache_key)
    if cached:
        return 200, cached

    # 1. User Profile
    st_u, res_u = execute_request(
        "/api/auth/user",
        method="GET",
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    if st_u != 200:
        return st_u, res_u

    # 2. Talent Card Signal
    st_s, res_s = execute_request(
        "/api/auth/jobseekersignal/find",
        method="GET",
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    sig = res_s.get("jobseekersignal", {}) if st_s == 200 and isinstance(res_s, dict) else {}

    # 3. Preferences
    st_p, res_p = execute_request(
        "/get-candidate-matching-preferences",
        method="GET",
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    prefs = res_p if st_p == 200 and isinstance(res_p, dict) else {}

    combined = {
        "success": True,
        "user_id": res_u.get("_id"),
        "tcid": sig.get("_id") or res_u.get("seekingStatus", {}).get("candidateSignalId"),
        "name": res_u.get("name") or f"{res_u.get('firstName', '')} {res_u.get('lastName', '')}".strip(),
        "headline": res_u.get("headline"),
        "summary": res_u.get("summary"),
        "experience_years": res_u.get("experience"),
        "email": res_u.get("primaryEmailId"),
        "phone": res_u.get("cellphoneNumber"),
        "current_company": sig.get("currentCompany", {}).get("name") if isinstance(sig.get("currentCompany"), dict) else sig.get("currentCompany"),
        "skills": [s.get("name") if isinstance(s, dict) else s for s in sig.get("skills", [])],
        "locations": sig.get("locations", []),
        "salary": sig.get("salary"),
        "resume_name": res_u.get("seekingStatus", {}).get("resume_file_names", [None])[0],
        "resume_text": sig.get("resumeText") or "",
        "preferences": prefs,
        "is_active": not res_u.get("isAccountDeactivated", False)
    }

    _global_cache.set(cache_key, combined, ttl_seconds=180)
    return 200, combined


def update_candidate_profile(
    headline: Optional[str] = None,
    summary: Optional[str] = None,
    experience: Optional[int] = None,
    current_company: Optional[str] = None,
    skills: Optional[List[str]] = None,
    locations: Optional[List[str]] = None,
    preferred_salary: Optional[int] = None,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Update candidate profile attributes via Cutshort user settings and matching preferences."""
    payload: Dict[str, Any] = {}
    if headline is not None:
        payload["headline"] = headline
    if summary is not None:
        payload["summary"] = summary
    if experience is not None:
        payload["experience"] = experience

    updated_fields = list(payload.keys())

    status, res = execute_request(
        "/setusersettings",
        method="POST",
        json_data=payload,
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )

    # Invalidate cache
    _global_cache.invalidate("profile:full")

    # If locations or salary preference provided, also update matching preferences
    pref_res = None
    if locations is not None or preferred_salary is not None:
        # Cutshort requires the existing preference dictionary merged with updates
        st_get_pref, curr_prefs = execute_request(
            "/get-candidate-matching-preferences",
            method="GET",
            cutshort_authentication=cutshort_authentication,
            cf_clearance=cf_clearance,
            xsrf_token=xsrf_token,
            cssid=cssid,
            user_agent=user_agent
        )
        pref_payload = curr_prefs if st_get_pref == 200 and isinstance(curr_prefs, dict) else {}
        if locations is not None:
            pref_payload["preferenceLocations"] = locations
        if preferred_salary is not None:
            pref_payload["preferredSalaryVanity"] = preferred_salary

        st_pref, res_pref = execute_request(
            "/save-candidate-matching-preferences",
            method="POST",
            json_data=pref_payload,
            cutshort_authentication=cutshort_authentication,
            cf_clearance=cf_clearance,
            xsrf_token=xsrf_token,
            cssid=cssid,
            user_agent=user_agent
        )
        pref_res = res_pref
        updated_fields.extend([k for k in ["preferenceLocations", "preferredSalaryVanity"] if k in pref_payload])

        # Also sync talent card signal preferences if tcid is available
        info = discover_candidate_info(
            cutshort_authentication=cutshort_authentication,
            cf_clearance=cf_clearance,
            xsrf_token=xsrf_token,
            cssid=cssid,
            user_agent=user_agent
        )
        tcid = info.get("tcid")
        if tcid:
            sig_payload: Dict[str, Any] = {"id": tcid}
            if locations is not None:
                sig_payload["preferenceLocations"] = locations
            execute_request(
                "/setmatchprefsignal",
                method="POST",
                json_data=sig_payload,
                cutshort_authentication=cutshort_authentication,
                cf_clearance=cf_clearance,
                xsrf_token=xsrf_token,
                cssid=cssid,
                user_agent=user_agent
            )

    return status, {
        "success": status == 200,
        "message": "Candidate profile updated successfully.",
        "updated_fields": updated_fields,
        "details": res,
        "preferences_update": pref_res
    }


def touch_profile_pulse(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Refresh candidate activity pulse (Active Today).
    Calls /setmatchprefsignal to verify activity, bump recruiter ranking, and trigger elastic sync.
    """
    info = discover_candidate_info(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    tcid = info.get("tcid")
    payload = {"id": tcid} if tcid else {}

    status, res = execute_request(
        "/setmatchprefsignal",
        method="POST",
        json_data=payload,
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    now_ts = int(time.time())
    return status, {
        "success": status in [200, 201],
        "message": "Cutshort candidate availability signal refreshed successfully (Rank boosted & ElasticSearch synced).",
        "timestamp": now_ts,
        "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts)),
        "tcid": tcid,
        "elastic_sync": res.get("syncToElasticRequestedOn") if isinstance(res, dict) else None,
        "verified_recently": "dataVerifiedRecently" in (res.get("talentDBBucketScoreReasons") or []) if isinstance(res, dict) else False,
        "result": res
    }


def get_resume_info(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Retrieve candidate resume document information and parsed text."""
    st, res = get_candidate_profile(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    if st != 200:
        return st, res

    return 200, {
        "success": True,
        "candidate_id": res.get("user_id"),
        "tcid": res.get("tcid"),
        "resume_name": res.get("resume_name"),
        "resume_text": res.get("resume_text", ""),
        "has_resume": bool(res.get("resume_name")),
        "message": f"Resume active: {res.get('resume_name')}" if res.get("resume_name") else "No resume document uploaded."
    }


# ===========================================================================
# 2. JOB SEARCH & DETAILS
# ===========================================================================

CATEGORY_SLUG_MAP = {
    "python": "python-jobs",
    "flutter": "flutter-jobs",
    "react": "react-js-jobs",
    "fullstack": "fullstack-developer-jobs",
    "backend": "backend-developer-jobs",
    "frontend": "frontend-developer-jobs",
    "node": "node-js-jobs",
    "android": "android-developer-jobs",
    "ai": "artificial-intelligence-ai-jobs",
    "ml": "machine-learning-ml-jobs",
    "devops": "devops-engineer-jobs"
}


def search_jobs(
    query: Optional[str] = None,
    category: Optional[str] = None,
    location: Optional[str] = None,
    remote: bool = False,
    min_exp: Optional[int] = None,
    max_exp: Optional[int] = None,
    limit: int = 20,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Search active tech jobs on Cutshort.
    Supports query by role/skill keyword or defaults to candidate's primary tech stack.
    """
    category_slug = "python-jobs"
    if category:
        category_slug = category if category.endswith("-jobs") else f"{category}-jobs"
    elif query:
        q_lower = query.lower().strip()
        matched = False
        for k, v in CATEGORY_SLUG_MAP.items():
            if k in q_lower:
                category_slug = v
                matched = True
                break
        if not matched:
            category_slug = "python-jobs"

    cache_key = f"jobs:{category_slug}:{query}:{location}:{remote}"
    cached = _global_cache.get(cache_key)
    if cached:
        return 200, cached

    auth, cf, xsrf, cs, ua = resolve_credentials(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    headers = build_request_headers(auth, cf, xsrf, cs, ua)

    url = f"https://cutshort.io/jobs/{category_slug}"

    try:
        with httpx.Client(follow_redirects=True, headers=headers, timeout=15.0) as client:
            resp = client.get(url)
            if resp.status_code != 200 and category_slug != "python-jobs":
                resp = client.get("https://cutshort.io/jobs/python-jobs")

            if resp.status_code != 200:
                return resp.status_code, {"error": f"Cutshort search failed with HTTP {resp.status_code}"}

            m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp.text)
            if not m:
                return 502, {"error": "Could not parse Next.js data from Cutshort jobs page"}

            d = json.loads(m.group(1))
            page_props = d.get("props", {}).get("pageProps") or {}
            dehydrated = page_props.get("dehydratedState") or {}
            queries = dehydrated.get("queries") or []

            raw_jobs = []
            for q in queries:
                qk = q.get("queryKey") or []
                if qk and qk[0] == "jobListData":
                    st_val = q.get("state") or {}
                    dt_val = st_val.get("data") or {}
                    if isinstance(dt_val, dict):
                        inner_dt = dt_val.get("data") or {}
                        if isinstance(inner_dt, dict):
                            page_data = inner_dt.get("pageData") or {}
                            raw_jobs = page_data.get("jobs") or []
                            break

            # Fallback to python-jobs if specific category yielded zero jobs
            if not raw_jobs and category_slug != "python-jobs":
                resp_fallback = client.get("https://cutshort.io/jobs/python-jobs")
                if resp_fallback.status_code == 200:
                    m2 = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', resp_fallback.text)
                    if m2:
                        d2 = json.loads(m2.group(1))
                        q2 = (d2.get("props", {}).get("pageProps", {}).get("dehydratedState") or {}).get("queries") or []
                        for q in q2:
                            qk = q.get("queryKey") or []
                            if qk and qk[0] == "jobListData":
                                st_val = q.get("state") or {}
                                dt_val = st_val.get("data") or {}
                                if isinstance(dt_val, dict):
                                    inner_dt = dt_val.get("data") or {}
                                    if isinstance(inner_dt, dict):
                                        page_data = inner_dt.get("pageData") or {}
                                        raw_jobs = page_data.get("jobs") or []
                                        break

            parsed_jobs = []
            for j in raw_jobs:
                jid = str(j.get("_id", ""))
                comp_info = j.get("companyDetails", {}) or {}
                exp_info = j.get("expRange", {}) or {}

                # Filter by remote if requested
                if remote and j.get("remoteType") not in ["remote_only", "hybrid"]:
                    continue

                # Filter by location if specified
                locs = j.get("locations", [])
                if location and locs:
                    if not any(location.lower() in str(loc).lower() for loc in locs):
                        continue

                # Filter by experience
                min_e = exp_info.get("min", 0)
                max_e = exp_info.get("max", 100)
                if min_exp is not None and max_e < min_exp:
                    continue
                if max_exp is not None and min_e > max_exp:
                    continue

                job_obj = {
                    "id": jid,
                    "title": j.get("headline"),
                    "company": comp_info.get("name"),
                    "company_id": comp_info.get("_id"),
                    "locations": locs or ["Remote / Pan India"],
                    "locations_text": j.get("locationsText"),
                    "experience_range": f"{min_e} - {max_e} years",
                    "salary_range": j.get("salaryRangeText") or "Not disclosed",
                    "remote_type": j.get("remoteType", "office"),
                    "skills": j.get("allSkills", []),
                    "recruiter": j.get("createdBy", {}).get("name"),
                    "public_url": j.get("publicUrl"),
                    "auth_apply_url": j.get("authApplyUrl"),
                    "posted_date": j.get("jobFactSummary", {}).get("postedDateLabel"),
                    "is_saved": j.get("isJobSaved", False)
                }

                parsed_jobs.append(job_obj)
                _job_cache[jid] = {**job_obj, "raw_data": j}

            result = {
                "success": True,
                "category": category_slug,
                "total_count": len(parsed_jobs),
                "jobs": parsed_jobs[:limit]
            }

            _global_cache.set(cache_key, result, ttl_seconds=120)
            return 200, result

    except Exception as e:
        return 500, {"error": f"Failed to search jobs: {str(e)}"}


def get_job_details(
    job_id: Optional[str] = None,
    slug: Optional[str] = None,
    opportunity_url: Optional[str] = None,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Retrieve full job description, company profile, and requirements."""
    # Check cache first
    if job_id and job_id in _job_cache:
        cached_job = _job_cache[job_id]
        raw = cached_job.get("raw_data", {})
        return 200, {
            "success": True,
            "id": job_id,
            "title": cached_job.get("title"),
            "company": cached_job.get("company"),
            "company_details": raw.get("companyDetails"),
            "description_html": raw.get("sanitizedComment"),
            "salary": cached_job.get("salary_range"),
            "experience": cached_job.get("experience_range"),
            "skills": cached_job.get("skills"),
            "locations": cached_job.get("locations"),
            "remote_type": cached_job.get("remote_type"),
            "recruiter": cached_job.get("recruiter"),
            "public_url": cached_job.get("public_url")
        }

    target_slug = slug
    if not target_slug and opportunity_url:
        m_slug = re.search(r"/job/([^/?#]+)", opportunity_url)
        if m_slug:
            target_slug = m_slug.group(1)

    # If slug is available, fetch job description page directly
    if target_slug:
        try:
            auth, cf, xsrf, cs, ua = resolve_credentials(
                cutshort_authentication=cutshort_authentication,
                cf_clearance=cf_clearance,
                xsrf_token=xsrf_token,
                cssid=cssid,
                user_agent=user_agent
            )
            headers = build_request_headers(auth, cf, xsrf, cs, ua)
            with httpx.Client(follow_redirects=True, headers=headers, timeout=15.0) as client:
                r_job = client.get(f"https://cutshort.io/job/{target_slug}")
                if r_job.status_code == 200:
                    m = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', r_job.text)
                    if m:
                        d = json.loads(m.group(1))
                        queries = (d.get("props", {}).get("pageProps", {}).get("dehydratedState") or {}).get("queries") or []
                        for q in queries:
                            if q.get("queryKey", [None])[0] == "jobData":
                                pd = (q.get("state", {}).get("data", {}).get("data") or {}).get("pageData") or {}
                                jid = str(pd.get("_id", ""))
                                exp_info = pd.get("expRange", {}) or {}
                                min_e = exp_info.get("min", 0)
                                max_e = exp_info.get("max", 0)
                                job_data = {
                                    "success": True,
                                    "id": jid,
                                    "title": pd.get("headline"),
                                    "company": pd.get("companyDetails", {}).get("name"),
                                    "company_details": pd.get("companyDetails"),
                                    "description_html": pd.get("sanitizedComment"),
                                    "salary": pd.get("salaryRange") or "Not disclosed",
                                    "experience": f"{min_e} - {max_e} years",
                                    "skills": pd.get("allSkills", []),
                                    "locations": pd.get("locations", []),
                                    "remote_type": pd.get("remoteType", "office"),
                                    "recruiter": pd.get("createdBy", {}).get("name"),
                                    "public_url": pd.get("publicUrl")
                                }
                                if jid:
                                    _job_cache[jid] = {**job_data, "raw_data": pd, "salary_range": job_data["salary"], "experience_range": job_data["experience"], "remote_type": job_data["remote_type"]}
                                return 200, job_data
        except Exception:
            pass

    # If not in cache, search popular categories to hydrate cache
    for cat in ["python", "fullstack", "flutter"]:
        search_jobs(cat, cutshort_authentication=cutshort_authentication, cf_clearance=cf_clearance, xsrf_token=xsrf_token)
        if job_id and job_id in _job_cache:
            return get_job_details(job_id=job_id)

    # If still not found, return 404
    return 404, {"error": f"Job details for '{job_id or slug}' could not be found."}


# ===========================================================================
# 3. ONE-CLICK APPLICATION PIPELINE
# ===========================================================================

def apply_to_job(
    job_id: str,
    application_source: str = "jobCard",
    context: Optional[Dict[str, Any]] = None,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """
    Submit direct 1-click job application with candidate's Talent Card.
    Endpoint: POST /make-application-with-tc
    """
    cand = discover_candidate_info(
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    tcid = cand.get("tcid")
    if not tcid:
        return 400, {"error": "Could not resolve candidate Talent Card ID (tcid)."}

    payload = {
        "tcid": tcid,
        "jobid": str(job_id).strip(),
        "applicationSource": application_source,
        "context": context or {}
    }

    status, res = execute_request(
        "/make-application-with-tc",
        method="POST",
        json_data=payload,
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )

    return status, {
        "success": status in [200, 201],
        "job_id": job_id,
        "candidate": cand.get("name"),
        "tcid": tcid,
        "status": "applied" if status in [200, 201] else "failed",
        "result": res
    }


def save_job(
    job_id: str,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Bookmark / save job listing to candidate watchlist."""
    status, res = execute_request(
        "/save-job",
        method="POST",
        json_data={"jobId": str(job_id).strip()},
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    return status, {
        "success": status in [200, 201],
        "job_id": job_id,
        "message": f"Job #{job_id} bookmarked successfully.",
        "result": res
    }


def pass_job(
    job_id: str,
    reason: Optional[str] = None,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Decline / archive an irrelevant job listing."""
    reason_code = reason or "not_relevant"
    status, res = execute_request(
        "/markJobAsIrrelevant",
        method="POST",
        json_data={"jobId": str(job_id).strip(), "reasons": [reason_code]},
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    return status, {
        "success": status in [200, 201],
        "job_id": job_id,
        "message": f"Job #{job_id} marked as irrelevant / passed.",
        "result": res
    }


def get_pipeline_metrics(
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Fetch live candidate application breakdown counts."""
    status, res = execute_request(
        "/count-conversations/candidate",
        method="GET",
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    return status, {
        "success": status == 200,
        "total_active_conversations": res.get("total", 0) if isinstance(res, dict) else 0,
        "unread_conversations": res.get("unread", 0) if isinstance(res, dict) else 0,
        "awaiting_replies": res.get("awaiting", 0) if isinstance(res, dict) else 0,
        "shortlisted": res.get("shortlisted", 0) if isinstance(res, dict) else 0,
        "metrics": res if status == 200 else {}
    }


def get_conversations(
    page: int = 1,
    limit: int = 10,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Retrieve candidate's active recruiter conversation threads and stages."""
    status, res = execute_request(
        f"/conversations-v2/candidate?page={page}&limit={limit}",
        method="GET",
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    return status, {
        "success": status == 200,
        "total_count": res.get("totalCount", 0) if isinstance(res, dict) else 0,
        "page": page,
        "threads": res.get("results", []) if isinstance(res, dict) else []
    }


def send_reply_to_recruiter(
    thread_id: str,
    message: str,
    cutshort_authentication: Optional[str] = None,
    cf_clearance: Optional[str] = None,
    xsrf_token: Optional[str] = None,
    cssid: Optional[str] = None,
    user_agent: Optional[str] = None
) -> Tuple[int, Dict[str, Any]]:
    """Send message reply directly to a recruiter thread."""
    status, res = execute_request(
        "/sendreply",
        method="POST",
        json_data={"threadId": thread_id, "text": message},
        cutshort_authentication=cutshort_authentication,
        cf_clearance=cf_clearance,
        xsrf_token=xsrf_token,
        cssid=cssid,
        user_agent=user_agent
    )
    return status, {
        "success": status in [200, 201],
        "thread_id": thread_id,
        "result": res
    }
