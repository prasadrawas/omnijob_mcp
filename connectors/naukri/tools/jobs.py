"""
Job search, questionnaire parsing, and stateless job application tools for naukri_mcp.
"""
import json
import urllib.parse
from typing import Dict, Any, List, Optional, Union

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    JOB_SEARCH_URL,
    JOB_APPLY_URL,
    JOB_DETAILS_URL_TMPL,
    get_headers,
    make_api_request
)
from omnijob_mcp.connectors.naukri.serializers import build_application_payload
from omnijob_mcp.connectors.naukri.tools.profile import get_profile


def search_jobs(
    keywords: Union[str, List[str]],
    location: str = "Pune",
    experience: int = 5,
    limit: int = 20,
    job_age_days: int = 3,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Search live jobs on Naukri and categorize by Apply Flow.

    :param keywords: Comma-separated string or list of keyword queries (e.g. 'Python, FastAPI, Full Stack').
    :param location: Target city or location string (default 'Pune').
    :param experience: Minimum years of experience (default 5).
    :param limit: Maximum jobs to return (default 20).
    :param job_age_days: Only include jobs posted within the last N days (default 3).
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="109", system_id="jobsearch", referer="https://www.naukri.com/")

    kw_list: List[str] = []
    if isinstance(keywords, str):
        kw_list = [k.strip() for k in keywords.split(",") if k.strip()]
    elif isinstance(keywords, list):
        kw_list = [k.strip() for k in keywords if isinstance(k, str) and k.strip()]

    results: List[Dict[str, Any]] = []
    seen_ids = set()

    for kw in kw_list:
        params = {
            "noOfResults": min(limit, 50),
            "urlType": "search_by_keyword",
            "searchType": "adv",
            "keyword": kw,
            "location": location,
            "experience": experience,
            "jobAge": job_age_days,
            "sort": "r"
        }
        url = f"{JOB_SEARCH_URL}?{urllib.parse.urlencode(params)}"
        status, data = make_api_request(url, method="GET", headers=headers)

        if status == 406 and isinstance(data, dict) and "recaptcha" in str(data.get("message", "")).lower():
            return {
                "status": "recaptcha_required",
                "message": "Naukri search API requires human verification. Open naukri.com in browser to complete the challenge."
            }

        if status == 200 and isinstance(data, dict):
            for item in data.get("jobDetails", []) or []:
                jid = str(item.get("jobId", ""))
                if not jid or jid in seen_ids:
                    continue
                seen_ids.add(jid)

                # Classify apply category
                apply_url = item.get("applyUrl", "")
                has_quest = item.get("hasQuestionnaire", False)
                if not apply_url or "/apply-services/" in apply_url or "naukri.com" in apply_url:
                    category = "Category 2 (Questionnaire)" if has_quest else "Category 1 (1-Click Direct)"
                else:
                    category = "Category 3 (External Portal)"

                placeholders = item.get("placeholders", [])
                loc_label = location
                exp_label = f"{experience} Yrs"
                if isinstance(placeholders, list) and len(placeholders) > 0:
                    first_p = placeholders[0]
                    if isinstance(first_p, dict) and "label" in first_p:
                        loc_label = first_p["label"]
                    if len(placeholders) > 1:
                        second_p = placeholders[1]
                        if isinstance(second_p, dict) and "label" in second_p:
                            exp_label = second_p["label"]

                tags = []
                for t in item.get("tagsAndSkills", [])[:6]:
                    if isinstance(t, dict):
                        tags.append(t.get("label", ""))
                    else:
                        tags.append(str(t))

                results.append({
                    "job_id": jid,
                    "title": item.get("title", ""),
                    "company": item.get("companyName", ""),
                    "location": loc_label,
                    "experience": exp_label,
                    "apply_category": category,
                    "tags": tags,
                    "static_url": item.get("staticUrl", "")
                })

                if len(results) >= limit:
                    break
        if len(results) >= limit:
            break

    return {
        "status": "success",
        "total_found": len(results),
        "jobs": results
    }


def get_job_details(
    job_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Retrieve complete job description, requirements, and screening questionnaire schema for a job ID.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="109", system_id="jobsearch", referer=f"https://www.naukri.com/job-listings-{job_id}")
    url = JOB_DETAILS_URL_TMPL.format(job_id=job_id)
    status, data = make_api_request(url, method="GET", headers=headers)

    if status == 200 and isinstance(data, dict):
        job_info = data.get("jobDetails", {}) or data
        raw_q = job_info.get("questionnaire", []) or data.get("questions", []) or []

        parsed_questions = []
        for idx, q in enumerate(raw_q):
            qid = q.get("questionId") or q.get("id") or str(idx + 1)
            qtext = q.get("questionText") or q.get("title") or q.get("question") or ""
            opts = [opt.get("value") if isinstance(opt, dict) else str(opt) for opt in q.get("options", [])]
            parsed_questions.append({
                "id": str(qid),
                "text": qtext,
                "type": q.get("type", "text"),
                "options": opts,
                "is_mandatory": q.get("isMandatory", True)
            })

        return {
            "status": "success",
            "job_id": job_id,
            "title": job_info.get("title", ""),
            "company": job_info.get("companyDetail", {}).get("name", "") or job_info.get("companyName", ""),
            "description": job_info.get("description", "") or job_info.get("jobDescription", ""),
            "skills": [t.get("label", "") if isinstance(t, dict) else str(t) for t in job_info.get("tagsAndSkills", [])],
            "has_questionnaire": len(parsed_questions) > 0,
            "questions": parsed_questions
        }

    return {
        "status": "partial_success",
        "job_id": job_id,
        "note": f"Job details API returned HTTP {status}. Returning standard questionnaire template for agent resolution.",
        "has_questionnaire": True,
        "questions": [
            {"id": "notice_period", "text": "What is your official notice period?", "type": "single_choice", "options": ["Immediate", "15 Days", "30 Days", "60 Days", "90 Days"]},
            {"id": "current_ctc", "text": "What is your current annual CTC?", "type": "text"},
            {"id": "expected_ctc", "text": "What is your expected annual CTC?", "type": "text"},
            {"id": "current_location", "text": "Are you currently located in or willing to relocate to this job location?", "type": "single_choice", "options": ["Yes", "No"]}
        ]
    }


def apply_to_job(
    job_id: str,
    answers: Optional[List[Dict[str, Any]]] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Submit an application to a Naukri job (Category 1 Direct Apply or Category 2 Questionnaire).
    Pure stateless: does not modify local disk files.

    :param job_id: Numerical job ID from Naukri.
    :param answers: Optional list of questionnaire answers, each dict with {'questionId': str, 'answer': str}.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve candidate profile ID."}

    headers = get_headers(
        at,
        rt,
        content_type="application/json",
        is_mutation=False,
        app_id="109",
        system_id="jobsearch",
        referer=f"https://www.naukri.com/job-listings-{job_id}"
    )

    payload = build_application_payload(job_id=job_id, profile_id=pid, answers=answers)
    status, resp_data = make_api_request(
        JOB_APPLY_URL,
        method="POST",
        headers=headers,
        data=json.dumps(payload).encode("utf-8")
    )

    resp_str = str(resp_data).lower()
    if status in (200, 201) or "already applied" in resp_str:
        return {
            "status": "applied",
            "job_id": job_id,
            "already_applied": "already applied" in resp_str,
            "http_status": status,
            "message": "Application submitted successfully to Naukri CloudGateway.",
            "response": resp_data
        }

    return {
        "status": "failed",
        "job_id": job_id,
        "http_status": status,
        "message": "Application submission failed.",
        "details": resp_data
    }
