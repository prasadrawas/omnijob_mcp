"""
Naukri Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.naukri import auth
from omnijob_mcp.connectors.naukri.tools import (
    jobs,
    profile,
    resume,
    analytics,
    taxonomy,
    delete,
    duplicates,
)


class NaukriConnector(BaseConnector):
    name: str = "naukri"
    display_name: str = "Naukri.com"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "profile",
        "update_profile",
        "account",
        "taxonomy",
        "resume",
        "duplicates",
    ]

    def is_authenticated(self) -> bool:
        return auth.is_authenticated()

    def get_session_status(self) -> Dict[str, Any]:
        return auth.get_session_status()

    def search_jobs(
        self,
        query: str,
        location: Optional[str] = None,
        experience: Optional[int] = None,
        start: int = 0,
        limit: int = 20,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        raw = jobs.search_jobs(
            keywords=query,
            location=location or "Pune",
            experience=experience if experience is not None else 5,
            limit=limit,
            job_age_days=kwargs.get("job_age_days", 3),
        )
        job_list = raw.get("jobs", [])
        normalized = []
        for j in job_list:
            normalized.append({
                "id": str(j.get("job_id", "")),
                "platform": "naukri",
                "title": j.get("title", ""),
                "company": j.get("company_name", ""),
                "location": str(j.get("location", "")),
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary", "")),
                "skills": j.get("key_skills", []) or j.get("tags", []),
                "posted_date": str(j.get("created_date", "")),
                "apply_url": j.get("static_url") or f"https://www.naukri.com/job-listings-{j.get('job_id')}",
                "is_easy_apply": j.get("apply_type") != "apply_on_company_site",
                "metadata": {
                    "apply_type": j.get("apply_type"),
                    "views": j.get("views"),
                }
            })
        return {
            "platform": "naukri",
            "total": raw.get("total_count", len(normalized)),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = jobs.get_job_details(job_id=job_id)
        if not raw.get("success"):
            return raw
        jd = raw.get("job_details", {})
        return {
            "platform": "naukri",
            "id": str(raw.get("job_id", job_id)),
            "title": jd.get("title", ""),
            "company": jd.get("companyName", ""),
            "location": jd.get("placeholders", [{}])[0].get("label", "") if jd.get("placeholders") else "",
            "description": jd.get("jobDescription", ""),
            "experience": jd.get("experienceText", ""),
            "salary": jd.get("salaryDetail", {}).get("label", ""),
            "skills": [s.get("label") for s in jd.get("keySkills", {}).get("userPreferred", []) if isinstance(s, dict)],
            "company_info": jd.get("companyDetail", {}),
            "screening_questions": raw.get("questionnaire", []),
            "can_apply": True,
            "metadata": raw,
        }

    def apply_to_job(
        self,
        job_id: str,
        answers: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        if dry_run:
            return {
                "platform": "naukri",
                "job_id": job_id,
                "status": "dry_run_success",
                "message": f"Dry-run application check succeeded for Naukri job {job_id}",
            }
        answers_list = []
        if answers:
            if isinstance(answers, list):
                answers_list = answers
            elif isinstance(answers, dict):
                for qid, val in answers.items():
                    answers_list.append({"questionId": str(qid), "answer": val})
        return jobs.apply_to_job(job_id=job_id, answers=answers_list or None)

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = profile.get_profile(section="all")
        data = raw.get("data", {})
        user = data.get("user", {})
        prof_list = data.get("profile", [])
        prof_0 = prof_list[0] if isinstance(prof_list, list) and prof_list else (prof_list if isinstance(prof_list, dict) else {})
        city_info = prof_0.get("city", {})
        loc = city_info.get("value") if isinstance(city_info, dict) else str(prof_0.get("mailCity") or "")
        skills_raw = prof_0.get("keySkills", "")
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if isinstance(skills_raw, str) else []
        return {
            "platform": "naukri",
            "name": prof_0.get("name") or user.get("username"),
            "email": user.get("email"),
            "mobile": user.get("mobile"),
            "headline": prof_0.get("resumeHeadline"),
            "summary": prof_0.get("summary"),
            "location": loc,
            "skills": skills or [s.get("skill") for s in data.get("key_skills", []) if isinstance(s, dict)],
            "employment": data.get("employments", []) or data.get("groupedEmployments", []),
            "education": data.get("educations", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            return profile.touch_profile_pulse()
        elif action == "update_headline":
            return profile.update_headline(headline=payload.get("headline", ""))
        elif action == "update_summary":
            return profile.update_summary(summary=payload.get("summary", ""))
        elif action == "update_skills":
            skills = payload.get("skills") or kwargs.get("skills") or []
            if isinstance(skills, list):
                skills_csv = ", ".join(str(s) for s in skills)
            else:
                skills_csv = str(skills)
            return profile.update_key_skills(skills_csv=skills_csv)
        elif action == "update_notice_period":
            val = payload.get("days") or payload.get("notice_period", 30)
            try:
                days = int(val)
            except (ValueError, TypeError):
                days = 30
            return profile.update_notice_period(days=days)
        elif action == "update_location":
            city_id = int(payload.get("city_id") or 139)
            city_name = str(payload.get("city_name") or "Pune")
            return profile.update_location(city_id=city_id, city_name=city_name)
        elif action == "sync_full":
            resume_source = payload.get("resume_source") or payload
            return profile.sync_full_profile(resume_source=resume_source)
        elif action == "audit_duplicates":
            return duplicates.audit_profile_duplicates()
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recruiter_inbox" or action == "inbox":
            return analytics.get_recruiter_inbox()
        elif action == "analytics":
            return analytics.get_profile_analytics()
        elif action == "salary_components" or action == "salary_labels":
            return analytics.get_salary_labels()
        elif action == "notifications":
            return analytics.get_notification_summary()
        elif action == "blocked_companies":
            return analytics.get_blocked_companies()
        elif action == "block_company":
            company_id = str(kwargs.get("company_id") or "")
            company_name = str(kwargs.get("company_name") or kwargs.get("company") or "")
            return analytics.block_company(company_id=company_id, company_name=company_name)
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        entity_map = {
            "locations": "city",
            "location": "city",
            "cities": "city",
            "city": "city",
            "skills": "certificate",
            "certifications": "certificate",
            "certificate": "certificate",
            "languages": "language",
            "language": "language",
        }
        mapped_type = entity_map.get(type_name.lower(), type_name.lower())
        return taxonomy.search_taxonomy(entity_type=mapped_type, query=query, limit=kwargs.get("limit", 10))

    def refresh_session(self) -> Dict[str, Any]:
        at, rt = auth.resolve_auth_tokens()
        return {"refreshed": bool(at), "nauk_at_valid": bool(at)}
