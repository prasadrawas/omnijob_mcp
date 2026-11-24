"""
Profile inspection and mutation tools for naukri_mcp.
"""
import json
from typing import Dict, Any, List, Optional, Tuple, Union

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    PROFILE_AGGREGATOR_URL,
    PROFILE_MUTATE_URL,
    get_headers,
    make_api_request
)
from omnijob_mcp.connectors.naukri.serializers import (
    build_headline_payload,
    build_summary_payload,
    build_key_skills_payload,
    build_notice_period_payload,
    build_location_payload,
    build_career_profile_payload,
    build_itskills_payload,
    build_project_payload,
    build_projects_payload,
    build_employment_payload,
    build_online_profiles_payload,
    build_work_samples_payload,
    build_publications_payload,
    build_presentations_payload,
    build_patents_payload,
    build_certifications_payload,
    build_educations_payload,
    build_schools_payload,
    build_personal_details_payload,
    build_languages_payload,
    build_job_search_status_payload,
    build_disability_payload,
    build_work_permit_payload,
    build_career_break_payload
)
from omnijob_mcp.connectors.naukri.utils import resolve_json_source


def extract_profile_id(profile_data: Dict[str, Any]) -> str:
    """Extract profile ID safely from aggregator profile data."""
    if not isinstance(profile_data, dict):
        return ""
    profiles = profile_data.get("profile", [])
    if isinstance(profiles, list) and len(profiles) > 0:
        return profiles[0].get("profileId", "")
    return profile_data.get("profileId", "")


def get_profile(
    section: str = "all",
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch live Naukri candidate profile data.

    :param section: Section to inspect ('all', 'headline', 'summary', 'skills', 'notice', 'career', 'itskills', 'projects', 'educations', 'employments', 'languages', 'personal').
    :param nauk_at: Optional bearer access token (falls back to NAUK_AT in .env).
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    status, data = make_api_request(PROFILE_AGGREGATOR_URL, method="GET", headers=headers)

    if status != 200 or not isinstance(data, dict):
        return {"status": "error", "http_status": status, "message": str(data)}

    pid = extract_profile_id(data)
    prof_list = data.get("profile", [{}])
    p0 = prof_list[0] if prof_list else {}

    section_lower = section.lower().strip()
    if section_lower in ("all", "full"):
        return {"status": "success", "profile_id": pid, "data": data}
    elif section_lower == "headline":
        return {"status": "success", "profile_id": pid, "headline": p0.get("resumeHeadline", "")}
    elif section_lower == "summary":
        return {"status": "success", "profile_id": pid, "summary": p0.get("summary", "")}
    elif section_lower in ("skills", "keyskills"):
        return {"status": "success", "profile_id": pid, "key_skills": p0.get("keySkills", "")}
    elif section_lower == "notice":
        return {"status": "success", "profile_id": pid, "notice_period": p0.get("noticePeriod", {})}
    elif section_lower == "career":
        return {
            "status": "success",
            "profile_id": pid,
            "expected_ctc": p0.get("expectedCtc", {}),
            "desired_role": p0.get("desiredRole", []),
            "preferred_locations": p0.get("newLocationPrefId", [])
        }
    elif section_lower == "itskills":
        return {"status": "success", "profile_id": pid, "itskills": data.get("itskills", [])}
    elif section_lower == "projects":
        return {"status": "success", "profile_id": pid, "projects": data.get("projects", [])}
    elif section_lower in ("educations", "education"):
        return {"status": "success", "profile_id": pid, "educations": data.get("educations", []), "schools": data.get("schools", [])}
    elif section_lower in ("employments", "employment"):
        return {"status": "success", "profile_id": pid, "employments": data.get("employments", [])}
    elif section_lower == "languages":
        return {"status": "success", "profile_id": pid, "languages": data.get("languages", [])}
    elif section_lower in ("accomplishments", "accomplishment"):
        return {
            "status": "success",
            "profile_id": pid,
            "online_profiles": data.get("onlineProfile", []),
            "work_samples": data.get("workSample", []),
            "publications": data.get("publication", []),
            "presentations": data.get("presentation", []),
            "patents": data.get("patent", []),
            "certifications": data.get("certifications", [])
        }
    elif section_lower in ("certifications", "certification"):
        return {"status": "success", "profile_id": pid, "certifications": data.get("certifications", [])}
    elif section_lower in ("online_profiles", "onlineprofiles", "onlineprofile"):
        return {"status": "success", "profile_id": pid, "online_profiles": data.get("onlineProfile", [])}
    elif section_lower in ("work_samples", "worksamples", "worksample"):
        return {"status": "success", "profile_id": pid, "work_samples": data.get("workSample", [])}
    elif section_lower in ("publications", "publication"):
        return {"status": "success", "profile_id": pid, "publications": data.get("publication", [])}
    elif section_lower in ("presentations", "presentation"):
        return {"status": "success", "profile_id": pid, "presentations": data.get("presentation", [])}
    elif section_lower in ("patents", "patent"):
        return {"status": "success", "profile_id": pid, "patents": data.get("patent", [])}
    elif section_lower == "personal":
        return {
            "status": "success",
            "profile_id": pid,
            "gender": p0.get("gender"),
            "birth_date": p0.get("birthDate"),
            "marital_status": p0.get("maritalStatus"),
            "address": p0.get("contactAddress")
        }

    return {"status": "success", "profile_id": pid, section: data.get(section, p0.get(section, {}))}


def _calculate_work_experience(work_list: List[Dict[str, Any]]) -> Dict[str, int]:
    """Calculate total candidate experience (years, months) from work experience history."""
    from datetime import datetime
    total_months = 0
    for w in work_list:
        s_str = str(w.get("startDate") or "").strip()
        e_str = str(w.get("endDate") or "").strip()
        if not e_str or w.get("isCurrent"):
            e_str = datetime.now().strftime("%Y-%m-%d")
        try:
            if s_str:
                s_dt = datetime.strptime(s_str[:10], "%Y-%m-%d")
                e_dt = datetime.strptime(e_str[:10], "%Y-%m-%d")
                months = max(0, (e_dt.year - s_dt.year) * 12 + (e_dt.month - s_dt.month))
                total_months += months
        except Exception:
            pass
    return {"year": max(0, total_months // 12), "month": max(0, total_months % 12)}


def execute_mutation(payload: Dict[str, Any], nauk_at: str, nauk_rt: str) -> Tuple[int, Any]:
    """Execute mutation request to CloudGateway fullprofiles."""
    headers = get_headers(nauk_at, nauk_rt, is_mutation=True)
    body_bytes = json.dumps(payload).encode("utf-8")
    return make_api_request(PROFILE_MUTATE_URL, method="POST", headers=headers, data=body_bytes)


def update_headline(
    headline: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """Update candidate resume headline."""
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_headline_payload(headline, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "headline": headline}


def update_summary(
    summary: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """Update candidate profile summary (automatically trimmed to max 1000 chars)."""
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="summary", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_summary_payload(summary, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status}


def update_key_skills(
    skills_csv: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """Update candidate key skills comma-separated list."""
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="skills", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_key_skills_payload(skills_csv, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "skills": skills_csv}


def update_notice_period(
    days: int,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """Update candidate notice period (e.g. 0 for Serving Notice, 15, 30 for 1 Month, 60 for 2 Months)."""
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="notice", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_notice_period_payload(days, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "notice_period_days": days}


def update_location(
    city_id: int,
    city_name: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """Update candidate current city (e.g. city_id: 139, city_name: 'Pune')."""
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="personal", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_location_payload(city_id, city_name, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "city": city_name}


def update_career_profile(
    expected_ctc: int,
    preferred_cities: List[Any],
    target_roles: List[Any],
    desired_job_types: Optional[List[str]] = None,
    desired_employment_types: Optional[List[str]] = None,
    department: Optional[Any] = None,
    role_category: Optional[Any] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update desired career preferences, expected CTC in INR, preferred locations, target roles,
    desired job types (e.g. ['permanent']), and desired employment types (e.g. ['Full Time']).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="career", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    # Resolve fallback role ID from existing profile if available
    existing_roles = prof_res.get("desired_role", [])
    fallback_id = 265
    if isinstance(existing_roles, list) and len(existing_roles) > 0 and isinstance(existing_roles[0], dict):
        fallback_id = int(existing_roles[0].get("id") or 265)

    resolved_roles = []
    for r in target_roles:
        if isinstance(r, dict):
            resolved_roles.append({
                "id": int(r.get("id") or fallback_id),
                "value": str(r.get("value", ""))
            })
        else:
            resolved_roles.append({"id": fallback_id, "value": str(r).strip()})

    payload = build_career_profile_payload(
        expected_ctc=expected_ctc,
        preferred_cities=preferred_cities,
        target_roles=resolved_roles,
        profile_id=pid,
        desired_job_types=desired_job_types,
        desired_employment_types=desired_employment_types,
        department=department,
        role_category=role_category
    )
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "details": resp}


def update_work_experience(
    work_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update employment / work experience history on candidate profile.

    :param work_list: List of work experience dicts, each with keys like:
                     'company', 'position', 'startDate' (YYYY-MM-DD), 'endDate', 'isCurrent' (bool),
                     'highlights' (list of achievements), 'technologies' (list of skills).
    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    # Ensure candidate experience is set dynamically from work_list so employments mutation succeeds
    exp = _calculate_work_experience(work_list)
    if exp["year"] > 0 or exp["month"] > 0:
        execute_mutation({"profile": {"experience": exp}, "profileId": pid}, at, rt)

    payload = build_employment_payload(work_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {
        "status": "success" if status in (200, 201) else "error",
        "http_status": status,
        "employments_count": len(work_list),
        "details": resp
    }


def update_projects(
    projects_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update or create multiple project entries on the candidate profile.

    :param projects_list: List of project dicts, each with keys like:
                         'projectTitle' (or 'title', 'name'), 'clientName' (or 'client'),
                         'projectDetails' (or 'description'), 'role', 'teamSize', 'skills',
                         'startDate', 'endDate', 'employmentType'.
    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_projects_payload(projects_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {
        "status": "success" if status in (200, 201) else "error",
        "http_status": status,
        "projects_count": len(projects_list),
        "details": resp
    }


def add_project(
    project_data: Dict[str, Any],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a single project to the candidate profile.

    :param project_data: Dict with keys: 'projectTitle' (or 'name'), 'clientName' (or 'client'),
                         'projectDetails' (or 'description'), 'role', 'teamSize', 'skills',
                         'startDate', 'endDate'.
    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_project_payload(project_data, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {
        "status": "success" if status in (200, 201) else "error",
        "http_status": status,
        "details": resp
    }


def touch_profile_pulse(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Touch candidate profile headline to activate the 'Profile Updated: Today' badge for recruiters.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    hl = prof_res.get("headline", "")
    pid = prof_res.get("profile_id", "")
    if not pid or not hl:
        return {"status": "error", "message": "Could not retrieve headline or profile ID."}

    payload = build_headline_payload(hl, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {
        "status": "success" if status in (200, 201) else "error",
        "http_status": status,
        "message": "Profile touched successfully. 'Updated Today' recruiter badge refreshed."
    }


def update_online_profiles(
    profiles_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update online professional profiles (e.g. LinkedIn, GitHub, Portfolio).

    :param profiles_list: List of dicts with 'profile' (e.g. 'LinkedIn') and 'url'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (p.get("profile") or "").strip().lower(): p.get("id")
        for p in prof_res.get("data", {}).get("onlineProfile", []) if p.get("id")
    }
    for p in profiles_list:
        name = (p.get("profile") or "").strip().lower()
        if not p.get("id") and name in existing_map:
            p["id"] = existing_map[name]

    payload = build_online_profiles_payload(profiles_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(profiles_list)}


def update_work_samples(
    samples_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update work samples links (e.g. GitHub repos, Behance portfolios).

    :param samples_list: List of dicts with 'title' and 'url'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (ws.get("title") or "").strip().lower(): ws.get("id")
        for ws in prof_res.get("data", {}).get("workSample", []) if ws.get("id")
    }
    for ws in samples_list:
        title = (ws.get("title") or "").strip().lower()
        if not ws.get("id") and title in existing_map:
            ws["id"] = existing_map[title]

    payload = build_work_samples_payload(samples_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(samples_list)}



def update_publications(
    publications_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update white papers, research publications, or journal entries.

    :param publications_list: List of dicts with 'title' and 'url'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (pub.get("title") or "").strip().lower(): pub.get("id")
        for pub in prof_res.get("data", {}).get("publication", []) if pub.get("id")
    }
    for pub in publications_list:
        title = (pub.get("title") or "").strip().lower()
        if not pub.get("id") and title in existing_map:
            pub["id"] = existing_map[title]

    payload = build_publications_payload(publications_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(publications_list)}


def update_presentations(
    presentations_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update presentations links (e.g. SlideShare, SpeakerDeck).

    :param presentations_list: List of dicts with 'title' and 'url'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (pres.get("title") or "").strip().lower(): pres.get("id")
        for pres in prof_res.get("data", {}).get("presentation", []) if pres.get("id")
    }
    for pres in presentations_list:
        title = (pres.get("title") or "").strip().lower()
        if not pres.get("id") and title in existing_map:
            pres["id"] = existing_map[title]

    payload = build_presentations_payload(presentations_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(presentations_list)}


def update_patents(
    patents_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update patent filings or grants.

    :param patents_list: List of dicts with 'title' and 'url'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (pat.get("title") or "").strip().lower(): pat.get("id")
        for pat in prof_res.get("data", {}).get("patent", []) if pat.get("id")
    }
    for pat in patents_list:
        title = (pat.get("title") or "").strip().lower()
        if not pat.get("id") and title in existing_map:
            pat["id"] = existing_map[title]

    payload = build_patents_payload(patents_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(patents_list)}


def update_certifications(
    certifications_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update certifications on candidate profile.

    :param certifications_list: List of dicts with 'course' (or 'name') and 'vendor' (or 'body').
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_map = {
        (c.get("course") or "").strip().lower(): (c.get("certificationId") or c.get("id"))
        for c in prof_res.get("data", {}).get("certifications", []) if (c.get("certificationId") or c.get("id"))
    }
    for c in certifications_list:
        course = (c.get("course") or c.get("name") or "").strip().lower()
        if not c.get("certificationId") and not c.get("id") and course in existing_map:
            c["certificationId"] = existing_map[course]

    payload = build_certifications_payload(certifications_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201, 204, 206) else "error", "http_status": status, "count": len(certifications_list)}



def update_accomplishments(
    accomplishments: Dict[str, Any],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update all accomplishment sections at once: online profiles, work samples, publications, presentations, patents, and certifications.
    """
    results = {}
    if "onlineProfiles" in accomplishments or "online_profiles" in accomplishments:
        items = accomplishments.get("onlineProfiles") or accomplishments.get("online_profiles") or []
        results["online_profiles"] = update_online_profiles(items, nauk_at, nauk_rt)
    if "workSamples" in accomplishments or "work_samples" in accomplishments:
        items = accomplishments.get("workSamples") or accomplishments.get("work_samples") or []
        results["work_samples"] = update_work_samples(items, nauk_at, nauk_rt)
    if "publications" in accomplishments:
        items = accomplishments.get("publications") or []
        results["publications"] = update_publications(items, nauk_at, nauk_rt)
    if "presentations" in accomplishments:
        items = accomplishments.get("presentations") or []
        results["presentations"] = update_presentations(items, nauk_at, nauk_rt)
    if "patents" in accomplishments:
        items = accomplishments.get("patents") or []
        results["patents"] = update_patents(items, nauk_at, nauk_rt)
    if "certifications" in accomplishments:
        items = accomplishments.get("certifications") or []
        results["certifications"] = update_certifications(items, nauk_at, nauk_rt)

    return {"status": "success", "results": results}


def sync_full_profile(
    resume_source: Union[str, Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Synchronize full profile sections from a master resume JSON (accepts a local file path, remote HTTP URL, or dictionary).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    master_data = resolve_json_source(resume_source)
    if not master_data:
        return {"status": "error", "message": "Failed to parse master resume JSON from source."}

    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    basics = master_data.get("basics", {})
    naukri_meta = master_data.get("naukri", {})
    results = {}

    # 1. Headline
    hl = naukri_meta.get("headline") or master_data.get("headlines", {}).get("primary") or basics.get("label", "")
    if hl:
        status, _ = execute_mutation(build_headline_payload(hl, pid), at, rt)
        results["headline"] = "success" if status in (200, 201) else "failed"

    # 2. Summary
    summ = basics.get("summary", "")
    if summ:
        status, _ = execute_mutation(build_summary_payload(summ, pid), at, rt)
        results["summary"] = "success" if status in (200, 201) else "failed"

    # 3. Key Skills
    skills_csv = ", ".join(naukri_meta.get("keySkills", [])) or ", ".join([s.get("name", "") for s in master_data.get("skills", [])])
    if skills_csv:
        status, _ = execute_mutation(build_key_skills_payload(skills_csv, pid), at, rt)
        results["skills"] = "success" if status in (200, 201) else "failed"

    # 4. Notice Period
    notice_days = naukri_meta.get("noticePeriodDays", 30)
    status, _ = execute_mutation(build_notice_period_payload(notice_days, pid), at, rt)
    results["notice"] = "success" if status in (200, 201) else "failed"

    # 5. Location
    loc = naukri_meta.get("currentLocation", {})
    if isinstance(loc, dict) and loc.get("id"):
        status, _ = execute_mutation(build_location_payload(loc["id"], loc.get("value", "Pune"), pid), at, rt)
        results["location"] = "success" if status in (200, 201) else "failed"

    # 6. Personal Details & Address
    pers = basics.get("personal", {})
    loc_b = basics.get("location", {})
    personal_payload = {
        "profile": {
            "mailCity": f"{loc_b.get('city', 'Pune').lower()}, {loc_b.get('region', 'Maharashtra').lower()}",
            "contactAddress": loc_b.get("address", "Pune, Maharashtra"),
            "pincode": loc_b.get("postalCode", "411045"),
            "gender": pers.get("gender", "F"),
            "maritalStatus": {"id": "N", "value": pers.get("maritalStatus", "Single / unmarried")},
            "birthDate": pers.get("birthDate", "1998-06-15")
        },
        "profileId": pid
    }
    status, _ = execute_mutation(personal_payload, at, rt)
    results["personal_details"] = "success" if status in (200, 201) else "failed"

    # 7. Projects
    projects_list = master_data.get("projects", [])
    if projects_list:
        status, _ = execute_mutation(build_projects_payload(projects_list, pid), at, rt)
        results["projects"] = "success" if status in (200, 201) else "failed"

    # 8. Structured IT Skills
    it_skills = master_data.get("itSkills", [])
    if it_skills:
        status, _ = execute_mutation(build_itskills_payload(it_skills, pid), at, rt)
        results["itskills"] = "success" if status in (200, 201) else "failed"

    # 9. Languages
    languages_list = master_data.get("languages", [])
    if languages_list:
        lang_entries = []
        for lang_item in languages_list:
            lang_entries.append({
                "lang": lang_item.get("lang"),
                "proficiency": {"id": lang_item.get("proficiency", 2), "value": "Proficient"},
                "ability": lang_item.get("ability", ["read", "write", "speak"])
            })
        status, _ = execute_mutation({"languages": lang_entries, "profileId": pid}, at, rt)
        results["languages"] = "success" if status in (200, 201) else "failed"

    # 10. Work Experience / Employments
    work_list = master_data.get("work", [])
    if work_list:
        exp = _calculate_work_experience(work_list)
        if exp["year"] > 0 or exp["month"] > 0:
            execute_mutation({"profile": {"experience": exp}, "profileId": pid}, at, rt)
        status, _ = execute_mutation(build_employment_payload(work_list, pid), at, rt)
        results["employments"] = "success" if status in (200, 201) else "failed"

    # 11. Accomplishments
    acc = master_data.get("accomplishments", {})
    if not acc:
        # Fallback to top-level keys if present
        acc = {
            "onlineProfiles": master_data.get("onlineProfiles", master_data.get("profiles", [])),
            "workSamples": master_data.get("workSamples", []),
            "publications": master_data.get("publications", []),
            "presentations": master_data.get("presentations", []),
            "patents": master_data.get("patents", []),
            "certifications": master_data.get("certifications", master_data.get("certificates", []))
        }
    if any(acc.values()):
        acc_res = update_accomplishments(acc, at, rt)
        results["accomplishments"] = acc_res.get("results", {})

    # 12. Educations (Graduation, Masters, PhD)
    edu_list = master_data.get("education", []) or master_data.get("educations", [])
    if edu_list:
        status, _ = execute_mutation(build_educations_payload(edu_list, pid), at, rt)
        results["educations"] = "success" if status in (200, 201) else "failed"

    # 13. Schools (Class X, Class XII)
    school_list = master_data.get("schools", [])
    if school_list:
        status, _ = execute_mutation(build_schools_payload(school_list, pid), at, rt)
        results["schools"] = "success" if status in (200, 201) else "failed"

    return {
        "status": "success",
        "profile_id": pid,
        "synced_sections": results
    }


def update_educations(
    educations_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update higher education entries (Graduation, Masters/Post-Graduation, Doctorate/PhD).

    :param educations_list: List of dicts with course, specialization, entityInstitute, yearOfStart, yearOfCompletion.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="educations", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    # Map existing educationType value ('UG', 'PG', 'PPG') -> educationId
    existing_edus = {
        str(e.get("educationType", {}).get("value", "")).strip().upper(): e.get("educationId")
        for e in prof_res.get("educations", []) if e.get("educationId")
    }
    for edu in educations_list:
        ed_val = str(edu.get("educationType", {}).get("value", "") if isinstance(edu.get("educationType"), dict) else edu.get("educationType", "")).strip().upper()
        if not edu.get("educationId") and ed_val in existing_edus:
            edu["educationId"] = existing_edus[ed_val]

    payload = build_educations_payload(educations_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "count": len(educations_list), "details": resp}


def update_schools(
    schools_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update school education entries (Class X, Class XII).

    :param schools_list: List of dicts with schoolBoard, schoolCompletionYear, schoolMedium, schoolPercentage, schoolLevel.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="educations", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    # Map existing schoolLevel -> schoolId
    existing_schools = {
        int(s.get("schoolLevel") or (2 if "12" in str(s.get("educationType", {}).get("id", "")) else 1)): s.get("schoolId")
        for s in prof_res.get("schools", []) if s.get("schoolId")
    }
    for sch in schools_list:
        lvl = int(sch.get("schoolLevel") or (2 if "12" in str(sch.get("educationType", {}).get("id", "")) else 1))
        if not sch.get("schoolId") and lvl in existing_schools:
            sch["schoolId"] = existing_schools[lvl]

    payload = build_schools_payload(schools_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "count": len(schools_list), "details": resp}


def update_personal_details(
    gender: Optional[str] = None,
    marital_status: Optional[str] = None,
    birth_date: Optional[str] = None,
    category: Optional[str] = None,
    address: Optional[str] = None,
    hometown: Optional[str] = None,
    pincode: Optional[str] = None,
    mail_city: Optional[str] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update candidate personal details (Gender, Marital status, DOB, Category, Address, Hometown, Pincode).

    :param gender: 'Male', 'Female', 'Transgender' (or 'M', 'F', 'T').
    :param marital_status: 'Single / unmarried', 'Married'.
    :param birth_date: Date of birth (YYYY-MM-DD).
    :param category: Caste/Category ('General', 'OBC', 'SC', 'ST').
    :param address: Full street/contact address.
    :param hometown: Hometown city name.
    :param pincode: Postal code (e.g. '411045').
    :param mail_city: Mail city and state (e.g. 'pune, maharashtra').
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_personal_details_payload(
        profile_id=pid,
        gender=gender,
        marital_status=marital_status,
        birth_date=birth_date,
        category=category,
        address=address,
        hometown=hometown,
        pincode=pincode,
        mail_city=mail_city
    )
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "details": resp}


def update_it_skills(
    skills_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update or add structured entries in candidate IT skills table with version, last used year, and experience.

    :param skills_list: List of dicts with 'skill'/'name', 'version', 'last_used_year', 'exp_years', 'exp_months'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="itskills", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_skill_map = {}
    for s in prof_res.get("itskills", []):
        sk_name = (s.get("skill") or s.get("entitySkill") or "").strip().lower()
        sk_id = s.get("skillId") or s.get("sid")
        if sk_name and sk_id:
            existing_skill_map[sk_name] = sk_id

    payload = build_itskills_payload(skills_list, pid, existing_skill_map=existing_skill_map)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "count": len(skills_list), "details": resp}


def add_it_skill(
    skill: str,
    version: str = "Latest",
    last_used_year: int = 2026,
    experience_years: int = 2,
    experience_months: int = 0,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add or update a single IT skill entry in candidate IT skills table.

    :param skill: Name of skill (e.g. 'Python', 'FastAPI', 'Docker').
    :param version: Version label (e.g. '3.12', 'v26', 'Cloud').
    :param last_used_year: Year last used (e.g. 2026).
    :param experience_years: Total years of experience with the skill.
    :param experience_months: Total months of experience with the skill.
    """
    return update_it_skills(
        skills_list=[{
            "skill": skill,
            "version": version,
            "last_used_year": last_used_year,
            "exp_years": experience_years,
            "exp_months": experience_months
        }],
        nauk_at=nauk_at,
        nauk_rt=nauk_rt
    )


def update_languages(
    languages_list: List[Dict[str, Any]],
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update or add candidate languages with proficiency and abilities (read, write, speak).

    :param languages_list: List of dicts with 'lang'/'language', 'proficiency' ('Beginner'/'Proficient'/'Expert'), and 'ability' list or 'read', 'write', 'speak' booleans.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="languages", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    existing_langs = {
        (lang_item.get("lang") or "").strip().lower(): (lang_item.get("languageId") or lang_item.get("id"))
        for lang_item in prof_res.get("languages", []) if (lang_item.get("languageId") or lang_item.get("id"))
    }
    for item in languages_list:
        name = (item.get("lang") or item.get("language") or "").strip().lower()
        if not item.get("languageId") and not item.get("id") and name in existing_langs:
            item["languageId"] = existing_langs[name]

    payload = build_languages_payload(languages_list, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "count": len(languages_list), "details": resp}


def add_language(
    language: str,
    proficiency: str = "Proficient",
    read: bool = True,
    write: bool = True,
    speak: bool = True,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add or update a single language in candidate profile.

    :param language: Language name (e.g. 'English', 'Hindi', 'Marathi', 'German').
    :param proficiency: 'Beginner', 'Proficient', or 'Expert'.
    :param read: Can read.
    :param write: Can write.
    :param speak: Can speak.
    """
    return update_languages(
        languages_list=[{
            "lang": language,
            "proficiency": proficiency,
            "read": read,
            "write": write,
            "speak": speak
        }],
        nauk_at=nauk_at,
        nauk_rt=nauk_rt
    )


def update_job_search_status(
    status_code_or_name: Any,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update job search availability status.

    :param status_code_or_name: 1 / 'Actively searching jobs', 2 / 'Casual job seeker', 3 / 'Not looking for jobs'.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_job_search_status_payload(status_code_or_name, pid)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "status_value": str(status_code_or_name), "details": resp}


def update_disability(
    is_disabled: bool = False,
    disability_type: Optional[str] = None,
    percentage: Optional[int] = None,
    details: Optional[str] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update candidate differently abled / disability profile section.

    :param is_disabled: Boolean indicating if differently abled.
    :param disability_type: Category of disability (e.g. 'Physical', 'Visual', 'Hearing').
    :param percentage: Percentage of disability (e.g. 40).
    :param details: Description or reason.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_disability_payload(is_disabled, pid, disability_type, percentage, details)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "is_disabled": is_disabled, "details": resp}


def delete_disability(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Clear differently abled / disability status from candidate profile.
    CAUTION: Modifies live candidate profile.
    """
    return update_disability(is_disabled=False, nauk_at=nauk_at, nauk_rt=nauk_rt)


def update_work_permit(
    us_work_status: Optional[str] = None,
    countries: Optional[List[str]] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update US work authorization status and international country work permits.

    :param us_work_status: US status (e.g. 'Citizen', 'Green Card', 'Have H1 Visa', 'Need H1 Visa').
    :param countries: List of countries candidate holds work permits for (e.g. ['USA', 'United Kingdom', 'Canada']).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_work_permit_payload(pid, us_work_status=us_work_status, countries=countries)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "details": resp}


def update_career_break(
    has_break: bool = True,
    reason: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Update candidate career break status, reason, and dates.

    :param has_break: True if candidate has a career break, False otherwise.
    :param reason: Reason for career break (e.g. 'Higher studies', 'Medical', 'Caregiving').
    :param start_date: Start date of break (YYYY-MM-DD or YYYY-MM).
    :param end_date: End date of break (YYYY-MM-DD or YYYY-MM).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    payload = build_career_break_payload(pid, has_break=has_break, reason=reason, start_date=start_date, end_date=end_date)
    status, resp = execute_mutation(payload, at, rt)
    return {"status": "success" if status in (200, 201) else "error", "http_status": status, "has_career_break": has_break, "details": resp}


def delete_career_break(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Remove career break from candidate profile.
    CAUTION: Modifies live candidate profile.
    """
    return update_career_break(has_break=False, nauk_at=nauk_at, nauk_rt=nauk_rt)


def resend_email_verification(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Trigger resending of the verification email link to the candidate's registered inbox.
    Helps fulfill the final profile completeness requirement.

    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    url = "https://www.naukri.com/cloudgateway-mynaukri/resman-aggregator-services/v0/users/self/verifyEmail"
    headers = get_headers(at, rt, content_type="application/json", is_mutation=False, app_id="105", system_id="105")
    headers["clientid"] = "d3skt0p"

    payload = {"verifyPrimaryEmail": True, "verifySecondaryEmail": False}
    status, resp = make_api_request(url, method="POST", headers=headers, data=json.dumps(payload).encode("utf-8"))
    if status in (200, 201, 204):
        return {
            "status": "success",
            "message": "Email verification link has been triggered and sent to registered email.",
            "http_status": status,
            "details": resp
        }
    return {
        "status": "error",
        "http_status": status,
        "message": "Failed to trigger email verification link.",
        "details": resp
    }

