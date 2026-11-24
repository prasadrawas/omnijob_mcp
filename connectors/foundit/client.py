"""
Foundit (Monster India/APAC) API Client.
Provides complete integration with Foundit candidate and job endpoints:
- Candidate profile inspection (personal details, IT skills, employments, resumes)
- Search jobs across categories, locations, and experience levels
- Job details and dynamic questionnaire inspection
- 1-Click candidate job application pipeline (/middleware/jobApply & /middleware/canJobApply)
- Job bookmarks / saved jobs management (/middleware/jobSave & /middleware/jobUnSave)
- Application tracking history (/middleware/appliedJobs)
- Algorithmic recruiter recommendations (/middleware/recommended)
"""
import re
import html
from typing import Dict, Any, List, Optional, Tuple, Union

import httpx

from omnijob_mcp.core.cache import TTLCache
from omnijob_mcp.connectors.foundit.auth import (
    FOUNDIT_BASE_URL,
    build_headers,
    decode_mssoat_token,
)

# Global TTL cache for jobs and profile (3 min default)
client_cache = TTLCache(default_ttl=180, max_size=500)

DEFAULT_TIMEOUT = 12.0


def _clean_html_text(html_content: Optional[str]) -> str:
    """Convert HTML string to readable plain text / markdown representation."""
    if not html_content:
        return ""
    text = html_content
    text = html.unescape(text)
    text = html.unescape(text)
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n### \1\n', text, flags=re.I)
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</p>', '\n\n', text, flags=re.I)
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n* \1', text, flags=re.I)
    text = re.sub(r'<[^>]+>', '', text)
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


# ===========================================================================
# 1. CANDIDATE PROFILE
# ===========================================================================

def get_profile(fields: Optional[List[str]] = None, use_cache: bool = True) -> Dict[str, Any]:
    """
    Retrieve candidate profile details from Foundit.
    GET /home/api/profileDetails?fields=personal_details,skills,it_skills,employments,resumes,...
    """
    default_fields = [
        "personal_details",
        "skills",
        "it_skills",
        "employments",
        "educations",
        "job_preferences",
        "resumes",
        "auto_apply_status",
    ]
    target_fields = fields or default_fields
    fields_query = ",".join(target_fields)

    cache_key = f"foundit_profile_{fields_query}"
    cached = client_cache.get(cache_key) if use_cache else None
    if cached:
        return cached

    url = f"{FOUNDIT_BASE_URL}/home/api/profileDetails?fields={fields_query}"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile")

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 401:
                return {
                    "status_code": 401,
                    "error": "Session unauthorized or expired. Please update MSSOAT and Akamai cookies.",
                }
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "error": f"Failed to retrieve profile: {str(e)}",
        }

    # Structure into user-friendly format
    pd = data.get("personalDetailSection", {}).get("personalDetails", {})
    skills_sec = data.get("skillSection", {}).get("skills", [])
    it_skills_sec = data.get("itSkillSection", {}).get("itSkills", [])
    employments_sec = data.get("employmentDetailSection", {}).get("employments", [])
    educations_sec = data.get("educationDetailSection", {}).get("educations", [])
    resumes_sec = data.get("resumeSection", {}).get("resumes", [])
    job_pref = data.get("jobPreferenceSection", {}).get("jobPreference", {})
    auto_apply = data.get("auto_apply_status", {})

    parsed_skills = [
        s.get("skill", {}).get("text") if isinstance(s.get("skill"), dict) else s.get("text")
        for s in skills_sec
        if (isinstance(s.get("skill"), dict) and s.get("skill", {}).get("text")) or s.get("text")
    ]
    parsed_it_skills = [
        s.get("skill", {}).get("text")
        for s in it_skills_sec
        if isinstance(s.get("skill"), dict) and s.get("skill", {}).get("text")
    ]

    emails = [e.get("email") for e in pd.get("emails", []) if e.get("email")]
    mobiles = [
        m.get("mobileNumber")
        for m in (pd.get("mobiles") or pd.get("mobileNumbers") or [])
        if m.get("mobileNumber")
    ]

    loc_obj = pd.get("additionalPersonalDetail", {}).get("currentLocation", {})
    exp_obj = pd.get("additionalPersonalDetail", {}).get("experience", {})
    city_val = loc_obj.get("text") or pd.get("city")
    total_exp_val = (
        f"{exp_obj.get('years', 0)} Years {exp_obj.get('months', 0)} Months"
        if exp_obj and (exp_obj.get("years") is not None or exp_obj.get("months") is not None)
        else pd.get("totalExperience")
    )

    profile_summary = {
        "status_code": 200,
        "full_name": pd.get("fullName") or pd.get("displayName", "Prasad Rawas"),
        "user_id": pd.get("userId"),
        "uuid": pd.get("uuid"),
        "primary_email": emails[0] if emails else None,
        "all_emails": emails,
        "primary_mobile": mobiles[0] if mobiles else None,
        "all_mobiles": mobiles,
        "city": city_val,
        "country": pd.get("country", "IN"),
        "total_experience": total_exp_val,
        "skills": parsed_skills,
        "it_skills": parsed_it_skills,
        "employments": [
            {
                "id": e.get("id"),
                "company": e.get("company", {}).get("text") if isinstance(e.get("company"), dict) else (e.get("companyName") or e.get("company")),
                "designation": e.get("designation", {}).get("text") if isinstance(e.get("designation"), dict) else e.get("designation"),
                "current": e.get("current", e.get("currentCompany", False)),
                "start_date": e.get("startDate"),
                "salary": e.get("salary", {}).get("absoluteValue") if isinstance(e.get("salary"), dict) else e.get("salary"),
                "notice_days": e.get("noticePeriod", {}).get("days") if isinstance(e.get("noticePeriod"), dict) else None,
            }
            for e in employments_sec
        ],
        "educations": [
            {
                "id": ed.get("id"),
                "degree": ed.get("highestQualification", {}).get("text") if isinstance(ed.get("highestQualification"), dict) else (ed.get("degree", {}).get("text") if isinstance(ed.get("degree"), dict) else ed.get("degree")),
                "specialization": ed.get("specialization", {}).get("text") if isinstance(ed.get("specialization"), dict) else ed.get("specialization"),
                "college": ed.get("college", {}).get("text") if isinstance(ed.get("college"), dict) else ed.get("college"),
                "year_of_passing": ed.get("yearOfPassing"),
            }
            for ed in educations_sec
        ],
        "resumes": [
            {
                "resume_id": r.get("resumeId"),
                "title": r.get("title"),
                "active": r.get("active", False),
                "last_modified": r.get("updatedAt"),
            }
            for r in resumes_sec
        ],
        "job_preferences": {
            "preferred_roles": [r.get("text") for r in job_pref.get("roles", []) if isinstance(r, dict)],
            "preferred_locations": [l.get("text") or l.get("city") for l in job_pref.get("locations", []) if isinstance(l, dict)],
        },
        "auto_apply": auto_apply,
        "raw_sections": list(data.keys()),
    }

    client_cache.set(cache_key, profile_summary, ttl=180)
    return profile_summary


def update_basic_profile(
    full_name: str,
    years: int,
    months: int = 0,
    city_text: str = "Pune",
    city_id: str = "0fb3f865-7da3-424a-8f14-a0d9db705ec1",
    experience_level: str = "EXPERIENCED",
) -> Dict[str, Any]:
    """
    Update candidate full name, experience years/months, and city location.
    POST /seeker-profile/api/workExperience
    """
    url = f"{FOUNDIT_BASE_URL}/seeker-profile/api/workExperience"
    jwt_info = decode_mssoat_token()
    raw_jwt = jwt_info.get("raw_jwt")

    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json; charset=utf-8")
    headers["x-source-site-context"] = "rexmonster"
    headers["x-language-code"] = "EN"
    if raw_jwt:
        headers["Authorization"] = f"Bearer {raw_jwt}"

    payload = {
        "fullName": full_name,
        "additionalPersonalDetail": {
            "experience": {
                "years": years,
                "months": months,
            },
            "currentLocation": {
                "id": city_id,
                "text": city_text,
            },
        },
        "experienceLevel": experience_level,
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            client_cache.clear()
            return {
                "status_code": resp.status_code,
                "success": resp.status_code in (200, 201),
                "message": "Basic profile details updated successfully" if resp.status_code in (200, 201) else "Failed to update basic profile details",
                "response": resp.json() if resp.status_code in (200, 201) else resp.text,
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def update_profile_summary(summary_text: str) -> Dict[str, Any]:
    """
    Update candidate professional summary.
    POST /middleware/setAiSummary
    """
    url = f"{FOUNDIT_BASE_URL}/middleware/setAiSummary"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json")
    payload = {"summary": summary_text.strip()}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            client_cache.clear()
            success = resp.status_code == 200
            return {
                "status_code": resp.status_code,
                "success": success,
                "message": "Profile summary updated successfully" if success else "Failed to update profile summary",
                "summary": summary_text,
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def add_skills(skills: List[Union[str, Dict[str, Any]]]) -> Dict[str, Any]:
    """
    Add technical skills to candidate profile.
    POST /middleware/createSkills
    """
    url = f"{FOUNDIT_BASE_URL}/middleware/createSkills"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json")

    formatted_skills = []
    for s in skills:
        if isinstance(s, str):
            formatted_skills.append({"skill": {"text": s.strip()}})
        elif isinstance(s, dict):
            if "skill" in s:
                formatted_skills.append(s)
            else:
                formatted_skills.append({"skill": s})

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=formatted_skills, headers=headers)
            client_cache.clear()
            data = resp.json() if resp.status_code == 200 else {}
            success = data.get("Status") == 200
            return {
                "status_code": resp.status_code,
                "success": success,
                "message": "Skills added successfully" if success else "Failed to add skills",
                "added_count": len(formatted_skills),
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def update_job_preferences(
    roles: Optional[List[Dict[str, Any]]] = None,
    locations: Optional[List[Dict[str, Any]]] = None,
    skills: Optional[List[Dict[str, Any]]] = None,
) -> Dict[str, Any]:
    """
    Update seeker preferred job roles, locations, and skills.
    PUT /seeker-profile/api/jobPreferences
    """
    url = f"{FOUNDIT_BASE_URL}/seeker-profile/api/jobPreferences"
    jwt_info = decode_mssoat_token()
    raw_jwt = jwt_info.get("raw_jwt")

    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json; charset=utf-8")
    headers["x-source-site-context"] = "rexmonster"
    headers["x-language-code"] = "EN"
    if raw_jwt:
        headers["Authorization"] = f"Bearer {raw_jwt}"

    pref_payload: Dict[str, Any] = {}
    if roles is not None:
        pref_payload["roles"] = roles
    if locations is not None:
        pref_payload["locations"] = locations
    if skills is not None:
        pref_payload["skills"] = skills

    payload = {"jobPreference": pref_payload}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.put(url, json=payload, headers=headers)
            client_cache.clear()
            success = resp.status_code == 200
            return {
                "status_code": resp.status_code,
                "success": success,
                "message": "Job preferences updated successfully" if success else "Failed to update job preferences",
                "response": resp.json() if success else resp.text,
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def update_employment(
    employment_id: Optional[int],
    company_text: str,
    designation_text: str,
    start_date: str = "2021-08-01",
    current: bool = True,
    salary: Optional[int] = 1200000,
    notice_days: int = 30,
) -> Dict[str, Any]:
    """
    Update employment details on candidate profile.
    PUT /seeker-profile/api/updateEmploymentDetails
    """
    url = f"{FOUNDIT_BASE_URL}/seeker-profile/api/updateEmploymentDetails"
    jwt_info = decode_mssoat_token()
    raw_jwt = jwt_info.get("raw_jwt")

    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json; charset=utf-8")
    headers["x-source-site-context"] = "rexmonster"
    headers["x-language-code"] = "EN"
    if raw_jwt:
        headers["Authorization"] = f"Bearer {raw_jwt}"

    emp_obj: Dict[str, Any] = {
        "startDate": start_date,
        "current": current,
        "company": {"text": company_text},
        "designation": {"text": designation_text},
        "noticePeriod": {
            "days": notice_days,
            "serving": False,
        },
    }
    if employment_id:
        emp_obj["id"] = employment_id
    if salary:
        emp_obj["salary"] = {
            "currency": "INR",
            "absoluteValue": salary,
            "salaryMode": {
                "id": "7cad9bf9-222e-11e9-9330-1418775c7275",
                "text": "Annually",
            },
            "confidential": True,
        }

    payload = {"employments": [emp_obj]}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.put(url, json=payload, headers=headers)
            client_cache.clear()
            success = resp.status_code == 200
            return {
                "status_code": resp.status_code,
                "success": success,
                "message": "Employment updated successfully" if success else "Failed to update employment",
                "response": resp.json() if success else resp.text,
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def add_education(
    qualification_id: str = "7de0a237-15bc-4ab0-8546-c1a7d8b1d724",
    qualification_text: str = "Masters in Technology (M.Tech/M.E)",
    specialization_id: str = "cbdfaea4-43bd-450f-9688-d5e1f4622552",
    specialization_text: str = "Computers",
    college_id: str = "3f945c5e-0aec-11ec-9a03-0242ac130003",
    college_text: str = "Pune Institute of Computer Technology, Society for Computer Technology and Research",
    year_of_passing: int = 2022,
    education_type_id: str = "f583b140-fc6b-11e8-92d8-000c290b6677",
    education_type_text: str = "Full time",
) -> Dict[str, Any]:
    """
    Add education record to candidate profile.
    POST /seeker-profile/api/educationDetails
    """
    url = f"{FOUNDIT_BASE_URL}/seeker-profile/api/educationDetails"
    jwt_info = decode_mssoat_token()
    raw_jwt = jwt_info.get("raw_jwt")

    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile", content_type="application/json; charset=utf-8")
    headers["x-source-site-context"] = "rexmonster"
    headers["x-language-code"] = "EN"
    if raw_jwt:
        headers["Authorization"] = f"Bearer {raw_jwt}"

    payload = {
        "educations": [
            {
                "college": {
                    "id": college_id,
                    "text": college_text,
                },
                "highestQualification": {
                    "id": qualification_id,
                    "text": qualification_text,
                },
                "specialization": {
                    "id": specialization_id,
                    "text": specialization_text,
                },
                "educationType": {
                    "id": education_type_id,
                    "text": education_type_text,
                },
                "yearOfPassing": year_of_passing,
            }
        ]
    }

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            client_cache.clear()
            success = resp.status_code in (200, 201)
            return {
                "status_code": resp.status_code,
                "success": success,
                "message": "Education record saved successfully" if success else "Failed to save education record",
                "response": resp.json() if success else resp.text,
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def lookup_taxonomy(
    type_name: str,
    name: str = "",
    parent_uuids: Optional[str] = None,
    limit: int = 10,
) -> Dict[str, Any]:
    """
    Query Foundit master data taxonomy (SKILL, LOCATION, DESIGNATION, COMPANY, HIGHEST_QUALIFICATION, COLLEGE, Specialization).
    GET /seeker-profile/api/getMasterData?type=...&name=...
    """
    t_clean = type_name.strip()
    url = f"{FOUNDIT_BASE_URL}/seeker-profile/api/getMasterData?type={t_clean}&limit={limit}"
    if name:
        url += f"&name={name.strip()}"
    if parent_uuids:
        url += f"&parentUuids={parent_uuids.strip()}"

    jwt_info = decode_mssoat_token()
    raw_jwt = jwt_info.get("raw_jwt")
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/profile")
    headers["x-source-site-context"] = "rexmonster"
    headers["x-language-code"] = "EN"
    if raw_jwt:
        headers["Authorization"] = f"Bearer {raw_jwt}"

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json().get("data", [])
                return {
                    "status_code": 200,
                    "type": t_clean,
                    "query": name,
                    "total": len(data),
                    "items": [
                        {
                            "id": item.get("uuid") or item.get("id"),
                            "text": item.get("name"),
                        }
                        for item in data
                    ],
                }
            return {"status_code": resp.status_code, "items": []}
    except Exception as e:
        return {"status_code": 500, "error": str(e), "items": []}


# ===========================================================================
# 2. JOB SEARCH & DETAILS
# ===========================================================================

def search_jobs(
    query: str,
    location: Optional[str] = None,
    experience: Optional[int] = None,
    start: int = 0,
    limit: int = 20,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Search jobs on Foundit matching keyword, location, and experience.
    GET /middleware/jobsearch?query=...&start=0&limit=20
    """
    q_str = query.strip()
    cache_key = f"foundit_search_{q_str}_{location}_{experience}_{start}_{limit}"
    cached = client_cache.get(cache_key) if use_cache else None
    if cached:
        return cached

    url = f"{FOUNDIT_BASE_URL}/middleware/jobsearch?query={q_str}&start={start}&limit={limit}"
    if location:
        url += f"&locations={location.strip()}"
    if experience is not None:
        url += f"&experienceRanges={experience}"

    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/srp/results?query={q_str}")

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 401:
                return {"status_code": 401, "error": "Unauthorized session."}
            resp.raise_for_status()
            raw_data = resp.json()
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "error": f"Failed to execute job search: {str(e)}",
            "jobs": [],
            "total_found": 0,
        }

    job_search_res = raw_data.get("jobSearchResponse", {})
    raw_jobs = job_search_res.get("data", []) if isinstance(job_search_res, dict) else []

    formatted_jobs = []
    for j in raw_jobs:
        if not isinstance(j, dict):
            continue
        jid = j.get("jobId") or j.get("id")
        if not jid:
            # Skip promotional banners and adsense cards inserted by Foundit
            continue
        title = j.get("title", "")
        company = j.get("companyName", "")

        # Locations
        locs = j.get("locations") or []
        loc_names = [l.get("city") or l.get("country", "") for l in locs if isinstance(l, dict)]
        if not loc_names and isinstance(locs, str):
            loc_names = [locs]

        # Experience
        min_exp = j.get("minimumExperience", {}).get("years", 0) if isinstance(j.get("minimumExperience"), dict) else j.get("minimumExperience")
        max_exp = j.get("maximumExperience", {}).get("years", 0) if isinstance(j.get("maximumExperience"), dict) else j.get("maximumExperience")

        # Skills
        skills = [s.get("text") for s in (j.get("skills") or []) if isinstance(s, dict)]
        it_skills = [s.get("text") for s in (j.get("itSkills") or []) if isinstance(s, dict)]

        # Quick Apply flag (in-platform 1-click apply supported)
        quick_apply = bool(j.get("quickApplyJob") or j.get("isQuickApply") or j.get("redirectStage") == 0)

        formatted_jobs.append({
            "job_id": jid,
            "title": title,
            "company_name": company,
            "locations": loc_names,
            "experience_range": f"{min_exp} - {max_exp} Yrs",
            "skills": skills + it_skills,
            "job_source": j.get("jobSource", "ORGANIC"),
            "quick_apply": quick_apply,
            "redirect_stage": j.get("redirectStage"),
            "is_applied": bool(j.get("isApplied")),
            "is_saved": bool(j.get("isSaved")),
            "apply_url": j.get("applyUrl") or f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}",
            "jd_url": f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}",
        })

    meta = job_search_res.get("meta", {}) if isinstance(job_search_res, dict) else {}
    total_found = meta.get("totalCount") or len(formatted_jobs)

    result = {
        "status_code": 200,
        "query": query,
        "location": location,
        "experience": experience,
        "total_found": total_found,
        "returned_count": len(formatted_jobs),
        "jobs": formatted_jobs,
    }

    client_cache.set(cache_key, result, ttl=180)
    return result


def get_job_details(job_id: Union[int, str], use_cache: bool = True) -> Dict[str, Any]:
    """
    Retrieve full JD, company information, skills, and screening questionnaire for a job.
    Uses /middleware/jobdetail/{jobId} to obtain the complete structured job object.
    """
    jid = str(job_id).strip()
    cache_key = f"foundit_jd_{jid}"
    cached = client_cache.get(cache_key) if use_cache else None
    if cached:
        return cached

    url = f"{FOUNDIT_BASE_URL}/middleware/jobdetail/{jid}"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}")

    job_obj = None
    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 200:
                data = resp.json()
                job_obj = data.get("jobDetailResponse")
    except Exception:
        job_obj = None

    # Fallback to canJobApply if jobdetail endpoint fails
    can_apply_res = None
    if not job_obj:
        can_apply_res = can_job_apply(job_id=jid)
        job_obj = can_apply_res.get("job_detail")

    if not job_obj:
        return {
            "status_code": 404,
            "job_id": jid,
            "error": "Job details not found or inaccessible.",
        }

    desc_raw = job_obj.get("description", "")
    plain_desc = _clean_html_text(desc_raw)

    locs = [l.get("city") or l.get("country", "") for l in (job_obj.get("locations") or []) if isinstance(l, dict)]
    skills = [s.get("text") for s in (job_obj.get("skills") or []) if isinstance(s, dict)]
    it_skills = [s.get("text") for s in (job_obj.get("itSkills") or []) if isinstance(s, dict)]

    is_applied = bool(job_obj.get("isApplied"))
    is_saved = bool(job_obj.get("isSaved"))
    quick_apply = bool(job_obj.get("quickApplyJob") or job_obj.get("redirectStage") == 0)

    result = {
        "status_code": 200,
        "job_id": jid,
        "title": job_obj.get("title"),
        "company_name": job_obj.get("companyName") or (job_obj.get("company", {}).get("name") if isinstance(job_obj.get("company"), dict) else ""),
        "locations": locs,
        "minimum_experience": job_obj.get("minimumExperience"),
        "maximum_experience": job_obj.get("maximumExperience"),
        "minimum_salary": job_obj.get("minimumSalary"),
        "maximum_salary": job_obj.get("maximumSalary"),
        "skills": list(dict.fromkeys(skills + it_skills)),
        "employment_types": job_obj.get("employmentTypes", []),
        "job_types": job_obj.get("jobTypes", []),
        "description_text": plain_desc,
        "description_length": len(plain_desc),
        "quick_apply": quick_apply,
        "redirect_stage": job_obj.get("redirectStage"),
        "is_applied": is_applied,
        "is_saved": is_saved,
        "total_applicants": job_obj.get("totalApplicants"),
        "posted_at": job_obj.get("postedAt"),
        "has_questionnaire": bool(job_obj.get("questionnaire")),
        "questionnaire": job_obj.get("questionData", {}).get("questions", []) if isinstance(job_obj.get("questionData"), dict) else [],
        "apply_url": job_obj.get("applyUrl") or f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}",
        "jd_url": f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}",
        "eligibility": {
            "can_apply": not is_applied if is_applied else (can_apply_res.get("can_apply") if can_apply_res else None),
            "status_text": "Already applied" if is_applied else ("Eligible" if quick_apply else "External Apply"),
        },
    }

    client_cache.set(cache_key, result, ttl=300)
    return result


# ===========================================================================
# 3. APPLICATION PIPELINE (CAN APPLY & 1-CLICK APPLY)
# ===========================================================================

def can_job_apply(job_id: Union[int, str]) -> Dict[str, Any]:
    """
    Check application eligibility and retrieve job details from Foundit.
    POST /middleware/canJobApply
    Payload: {"jobId": int(job_id)}
    """
    jid_int = int(job_id) if str(job_id).isdigit() else job_id
    url = f"{FOUNDIT_BASE_URL}/middleware/canJobApply"
    headers = build_headers(
        referer=f"{FOUNDIT_BASE_URL}/srp/results",
        content_type="application/json"
    )
    payload = {"jobId": jid_int}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            data = resp.json()
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "can_apply": False,
            "error": f"Failed to check canJobApply: {str(e)}",
        }

    status_num = data.get("canJobApplyStatus")
    status_text = data.get("canJobApplyStatusText")
    app_res = data.get("canJobApplyResponse", {})

    job_data = None
    next_action = None

    if status_num == 200:
        job_data = app_res.get("job")
        next_action = app_res.get("next")
        return {
            "status_code": 200,
            "can_apply": True,
            "job_id": str(job_id),
            "status_text": status_text,
            "next_action": next_action,
            "job_detail": job_data,
        }
    else:
        # Check payload inside error response
        payload_obj = app_res.get("payload", {})
        result_obj = payload_obj.get("result", {})
        job_data = result_obj.get("job")
        next_action = result_obj.get("next")
        err_msg = app_res.get("errorMessage", "Cannot apply for job")
        err_code = app_res.get("errorCode", "CANNOT_APPLY")

        return {
            "status_code": status_num or 400,
            "can_apply": False,
            "job_id": str(job_id),
            "error_code": err_code,
            "error": err_msg,
            "next_action": next_action,
            "job_detail": job_data,
        }


def apply_to_job(
    job_id: Union[int, str],
    answers: Optional[List[Dict[str, Any]]] = None,
    profile_id: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Submit a 1-click candidate application on Foundit.
    POST /middleware/jobApply
    Payload: {"job": {"jobId": int(job_id)}, "answers": [...]}
    """
    jid_int = int(job_id) if str(job_id).isdigit() else job_id

    # 1. Pre-flight check via canJobApply
    pre_check = can_job_apply(job_id=jid_int)

    if dry_run:
        return {
            "status_code": 200,
            "mode": "dry_run",
            "job_id": str(job_id),
            "can_apply": pre_check.get("can_apply"),
            "pre_flight_response": pre_check,
            "message": "Dry run complete. Eligibility verified.",
        }

    # 2. Check if already applied or cannot apply
    if not pre_check.get("can_apply") and pre_check.get("error_code") == "DUPLICATE_APPLY":
        return {
            "status_code": 409,
            "success": False,
            "job_id": str(job_id),
            "already_applied": True,
            "message": "You have already applied to this job on Foundit.",
        }

    # 3. Build submission payload
    payload: Dict[str, Any] = {
        "job": {"jobId": jid_int}
    }
    if answers:
        payload["answers"] = answers
    if profile_id:
        payload["profileId"] = profile_id

    url = f"{FOUNDIT_BASE_URL}/middleware/jobApply"
    headers = build_headers(
        referer=f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid_int}",
        content_type="application/json"
    )

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            data = resp.json()
    except Exception as e:
        return {
            "status_code": 500,
            "success": False,
            "job_id": str(job_id),
            "error": f"Failed to execute jobApply: {str(e)}",
        }

    job_apply_status = data.get("jobApplyStatus")
    job_apply_res = data.get("jobApplyResponse", {})

    if job_apply_status == 200:
        return {
            "status_code": 200,
            "success": True,
            "job_id": str(job_id),
            "message": "Application submitted successfully to Foundit!",
            "response": job_apply_res,
        }
    else:
        err_code = job_apply_res.get("errorCode", "APPLY_ERROR")
        err_msg = job_apply_res.get("errorMessage", "Failed to apply to job")
        already_applied = err_code == "DUPLICATE_APPLY"

        return {
            "status_code": 409 if already_applied else (job_apply_status or 400),
            "success": False,
            "job_id": str(job_id),
            "error_code": err_code,
            "already_applied": already_applied,
            "error": err_msg,
            "raw_response": job_apply_res,
        }


# ===========================================================================
# 4. BOOKMARKS & APPLICATION HISTORY
# ===========================================================================

def save_job(job_id: Union[int, str]) -> Dict[str, Any]:
    """Bookmark / save a job on Foundit. POST /middleware/jobSave"""
    jid_int = int(job_id) if str(job_id).isdigit() else job_id
    url = f"{FOUNDIT_BASE_URL}/middleware/jobSave"
    headers = build_headers(
        referer=f"{FOUNDIT_BASE_URL}/srp/results",
        content_type="application/json"
    )
    payload = {"jobId": jid_int}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            data = resp.json()
            success = data.get("jobSaveStatus") == 200
            return {
                "status_code": 200 if success else data.get("jobSaveStatus", 400),
                "success": success,
                "job_id": str(job_id),
                "message": "Job saved successfully." if success else "Failed to save job.",
                "response": data.get("jobSaveResponse"),
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def unsave_job(job_id: Union[int, str]) -> Dict[str, Any]:
    """Remove bookmark for a job on Foundit. POST /middleware/jobUnSave"""
    jid_int = int(job_id) if str(job_id).isdigit() else job_id
    url = f"{FOUNDIT_BASE_URL}/middleware/jobUnSave"
    headers = build_headers(
        referer=f"{FOUNDIT_BASE_URL}/srp/results",
        content_type="application/json"
    )
    payload = {"jobId": jid_int}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.post(url, json=payload, headers=headers)
            data = resp.json()
            success = data.get("jobUnSaveStatus") == 200
            return {
                "status_code": 200 if success else data.get("jobUnSaveStatus", 400),
                "success": success,
                "job_id": str(job_id),
                "message": "Job unsaved successfully." if success else "Failed to unsave job.",
                "response": data.get("jobUnSaveResponse"),
            }
    except Exception as e:
        return {"status_code": 500, "success": False, "error": str(e)}


def get_applied_jobs(start: int = 0, limit: int = 20) -> Dict[str, Any]:
    """Retrieve history of applied jobs. GET /middleware/appliedJobs"""
    url = f"{FOUNDIT_BASE_URL}/middleware/appliedJobs?start={start}&limit={limit}"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/applied-jobs")

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.get(url, headers=headers)
            data = resp.json()
            applied_res = data.get("appliedJobsResponse", {})
            return {
                "status_code": 200,
                "applied_jobs_status": data.get("appliedJobsStatus"),
                "applied_jobs": applied_res.get("data", []) if isinstance(applied_res, dict) else [],
                "meta": applied_res.get("meta", {}) if isinstance(applied_res, dict) else {},
            }
    except Exception as e:
        return {"status_code": 500, "error": str(e), "applied_jobs": []}


def get_saved_jobs(start: int = 0, limit: int = 20) -> Dict[str, Any]:
    """Retrieve saved / bookmarked jobs. GET /middleware/savedJobs"""
    url = f"{FOUNDIT_BASE_URL}/middleware/savedJobs?start={start}&limit={limit}"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/saved-jobs")

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.get(url, headers=headers)
            data = resp.json()
            saved_res = data.get("savedJobsResponse", {})
            return {
                "status_code": 200,
                "saved_jobs": saved_res.get("data", []) if isinstance(saved_res, dict) else [],
                "meta": saved_res.get("meta", {}) if isinstance(saved_res, dict) else {},
            }
    except Exception as e:
        return {"status_code": 500, "error": str(e), "saved_jobs": []}


def get_recommended_jobs() -> Dict[str, Any]:
    """Retrieve algorithmic job recommendations. GET /middleware/recommended"""
    url = f"{FOUNDIT_BASE_URL}/middleware/recommended"
    headers = build_headers(referer=f"{FOUNDIT_BASE_URL}/seeker/dashboard")

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT) as http_client:
            resp = http_client.get(url, headers=headers)
            data = resp.json()
            wrapper = data.get("dashBoardNewWrapper", {})
            pref_jobs = wrapper.get("preference", {}).get("data", [])
            early_jobs = wrapper.get("earlyAccess", {}).get("data", [])
            similar_jobs = wrapper.get("similarApplicant", {}).get("data", [])
            all_raw = pref_jobs + early_jobs + similar_jobs

            seen_ids = set()
            formatted_jobs = []
            for j in all_raw:
                if not isinstance(j, dict):
                    continue
                jid = j.get("jobId") or j.get("id")
                if not jid or jid in seen_ids:
                    continue
                seen_ids.add(jid)

                locs = j.get("locations")
                if isinstance(locs, list):
                    loc_str = ", ".join([l.get("city", "") for l in locs if isinstance(l, dict)])
                elif isinstance(locs, str):
                    loc_str = locs
                else:
                    loc_str = ""

                formatted_jobs.append({
                    "job_id": jid,
                    "title": j.get("title"),
                    "company_name": j.get("companyName"),
                    "locations": loc_str,
                    "experience": j.get("exp") or f"{j.get('minimumExperience', {}).get('years', 0)} - {j.get('maximumExperience', {}).get('years', 0)} Yrs",
                    "salary": j.get("salary"),
                    "quick_apply": bool(j.get("quickApplyJob") or j.get("redirectStage") == 0),
                    "is_applied": bool(j.get("isApplied")),
                    "is_saved": bool(j.get("isSaved")),
                    "jd_url": f"{FOUNDIT_BASE_URL}/seeker/job-details?id={jid}",
                })

            return {
                "status_code": 200,
                "total_recommended": len(formatted_jobs),
                "preference_count": len(pref_jobs),
                "early_access_count": len(early_jobs),
                "similar_applicant_count": len(similar_jobs),
                "recommended_jobs": formatted_jobs,
            }
    except Exception as e:
        return {"status_code": 500, "error": str(e), "recommended_jobs": []}
