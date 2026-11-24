"""
Analytics, recruiter communication, compensation, and privacy tools for naukri_mcp.
"""
import json
from typing import Dict, Any, Optional

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    DASHBOARD_URL,
    INBOX_URL,
    NOTIFY_URL,
    SALARY_LABELS_URL,
    BLOCKED_COMPANIES_URL,
    get_headers,
    make_api_request
)


def get_profile_analytics(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch recruiter search appearances, profile views, profile completeness score,
    and a prioritized list of missing profile sections.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")

    dash_status, dash_data = make_api_request(DASHBOARD_URL, method="GET", headers=headers)
    db = dash_data.get("dashBoard", {}) if isinstance(dash_data, dict) else {}

    raw_incomplete = db.get("incompleteSection", {}) or {}
    incomplete_list = []
    for k, v in raw_incomplete.items():
        if isinstance(v, dict):
            incomplete_list.append({
                "section": v.get("subSectionName", k),
                "weightage": v.get("subSectionWeightage", 0),
                "priority": v.get("subSectionPriority", 99)
            })
    incomplete_list.sort(key=lambda x: (x["priority"], -x["weightage"]))

    return {
        "status": "success" if dash_status == 200 else "error",
        "profile_id": db.get("profileId"),
        "candidate_name": db.get("name"),
        "profile_completeness_percent": db.get("pc", 0),
        "recruiter_search_appearances": db.get("totalSearchAppearancesCount", 0),
        "recruiter_profile_views": db.get("profileViewCount", 0),
        "last_modified_date": db.get("mod_dt"),
        "incomplete_sections": incomplete_list,
        "is_paid_user": db.get("isPaidUser", False),
        "is_premium": db.get("isPremium", False)
    }


def get_recruiter_inbox(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch recruiter messages, interview invitations, and unread count.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    status, data = make_api_request(INBOX_URL, method="GET", headers=headers)

    if status == 200 and isinstance(data, dict):
        return {
            "status": "success",
            "unread_count": data.get("unreadCount", 0),
            "total_count": data.get("totalCount", 0),
            "has_power_nvites": data.get("hasPowerNvites", False),
            "messages": data.get("inbox", [])
        }
    return {"status": "error", "http_status": status, "message": str(data)}


def get_notification_summary(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Fetch active notification counters (recommended jobs count, pending profile actions).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    status, data = make_api_request(NOTIFY_URL, method="GET", headers=headers)

    if status == 200 and isinstance(data, dict):
        st = data.get("status", {})
        return {
            "status": "success",
            "recommended_jobs_count": st.get("recoJobs", {}).get("noti_count", 0),
            "critical_actions_count": st.get("criticalActions", {}).get("noti_count", 0),
            "recruiter_searches_count": st.get("recruiterSearch", {}).get("noti_count", 0)
        }
    return {"status": "error", "http_status": status, "message": str(data)}


def get_salary_labels(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve Naukri compensation breakdown labels (Fixed, Fixed + Variable, Stocks, ESOPs, RSUs).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    status, data = make_api_request(SALARY_LABELS_URL, method="GET", headers=headers)

    if status == 200 and isinstance(data, dict):
        return {"status": "success", "labels": data.get("labelsToShow", []), "stock_types": data.get("stocksEntity", [])}
    return {"status": "error", "http_status": status, "message": str(data)}


def get_blocked_companies(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve list of companies blocked from viewing your profile.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    status, data = make_api_request(BLOCKED_COMPANIES_URL, method="GET", headers=headers)

    if status == 200:
        return {"status": "success", "blocked_companies": data if isinstance(data, list) else []}
    return {"status": "error", "http_status": status, "message": str(data)}


def block_company(
    company_id: str,
    company_name: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Add a company to your blocked list so recruiters from that company cannot see your profile.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, content_type="application/json", app_id="105", system_id="Naukri")
    payload = {"companyId": company_id, "companyName": company_name}
    status, data = make_api_request(BLOCKED_COMPANIES_URL, method="POST", headers=headers, data=json.dumps(payload).encode("utf-8"))

    return {"status": "success" if status in (200, 201, 204) else "error", "http_status": status, "company": company_name}
