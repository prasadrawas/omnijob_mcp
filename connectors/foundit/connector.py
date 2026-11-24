"""
Foundit (Monster India/APAC) Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.foundit import auth
from omnijob_mcp.connectors.foundit import client


class FounditConnector(BaseConnector):
    name: str = "foundit"
    display_name: str = "Foundit (Monster APAC)"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "can_apply",
        "save",
        "unsave",
        "applied_jobs",
        "saved_jobs",
        "profile",
        "update_profile",
        "account",
        "taxonomy",
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
        raw = client.search_jobs(query=query, location=location, experience=experience, start=start, limit=limit)
        jobs = raw.get("jobs", [])
        normalized = []
        for j in jobs:
            normalized.append({
                "id": str(j.get("job_id", "")),
                "platform": "foundit",
                "title": j.get("title", ""),
                "company": j.get("company", ""),
                "location": j.get("location", ""),
                "experience": j.get("experience", ""),
                "salary": j.get("salary", ""),
                "skills": j.get("skills", []),
                "posted_date": j.get("posted_date", ""),
                "apply_url": j.get("apply_url", ""),
                "is_easy_apply": j.get("is_easy_apply", True),
                "metadata": {
                    "views": j.get("views"),
                    "applies": j.get("applies"),
                }
            })
        return {
            "platform": "foundit",
            "total": raw.get("total", len(normalized)),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_job_details(job_id=job_id)
        if not raw.get("success"):
            return raw
        return {
            "platform": "foundit",
            "id": str(raw.get("job_id", job_id)),
            "title": raw.get("title", ""),
            "company": raw.get("company", ""),
            "location": raw.get("location", ""),
            "description": raw.get("description", ""),
            "experience": raw.get("experience", ""),
            "salary": raw.get("salary", ""),
            "skills": raw.get("skills", []),
            "company_info": raw.get("company_info", {}),
            "screening_questions": raw.get("questionnaire", []),
            "can_apply": raw.get("can_apply", True),
            "metadata": raw.get("raw_details", {}),
        }

    def can_job_apply(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.can_job_apply(job_id=job_id)

    def apply_to_job(
        self,
        job_id: str,
        answers: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        return client.apply_to_job(job_id=job_id, questionnaire_answers=answers, dry_run=dry_run)

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.save_job(job_id=job_id)

    def unsave_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.unsave_job(job_id=job_id)

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        return client.get_applied_jobs(start=start, limit=limit)

    def get_saved_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        return client.get_saved_jobs(start=start, limit=limit)

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_profile(fields=fields)
        return {
            "platform": "foundit",
            "name": raw.get("full_name") or raw.get("basic_details", {}).get("full_name"),
            "email": raw.get("primary_email") or raw.get("basic_details", {}).get("email"),
            "mobile": raw.get("primary_mobile") or raw.get("basic_details", {}).get("mobile"),
            "location": raw.get("city") or raw.get("basic_details", {}).get("current_location"),
            "experience_years": raw.get("total_experience"),
            "summary": raw.get("profile_summary"),
            "skills": [s.get("name") if isinstance(s, dict) else str(s) for s in (raw.get("it_skills") or raw.get("skills") or [])],
            "employment": raw.get("employments") or raw.get("employment_history", []),
            "education": raw.get("educations") or raw.get("education_history", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "update_summary":
            summary = payload.get("summary") or payload.get("profile_summary") or kwargs.get("summary") or ""
            return client.update_profile_summary(summary)
        elif action == "update_basic":
            return client.update_basic_profile(
                first_name=payload.get("first_name"),
                last_name=payload.get("last_name"),
                mobile=payload.get("mobile"),
                current_location=payload.get("current_location"),
                total_experience_years=payload.get("total_experience_years"),
                total_experience_months=payload.get("total_experience_months"),
                notice_period=payload.get("notice_period"),
            )
        elif action == "update_skills":
            skills = payload.get("skills") or kwargs.get("skills") or []
            return client.add_skills(skills)
        elif action == "update_employment":
            return client.update_employment(
                designation=payload.get("designation", ""),
                company_name=payload.get("company_name", ""),
                start_date=payload.get("start_date", ""),
                end_date=payload.get("end_date"),
                is_current=payload.get("is_current", True),
                notice_period=payload.get("notice_period", "30 days"),
                annual_salary=payload.get("annual_salary"),
                job_description=payload.get("job_description", ""),
            )
        elif action == "update_education":
            return client.add_education(
                degree_type=payload.get("degree_type", ""),
                degree_name=payload.get("degree_name", ""),
                specialization=payload.get("specialization", ""),
                institute_name=payload.get("institute_name", ""),
                passing_year=payload.get("passing_year", 2022),
                grading_system=payload.get("grading_system", "Percentage"),
                marks=payload.get("marks", 85.0),
            )
        elif action == "update_preferences":
            return client.update_job_preferences(
                preferred_locations=payload.get("preferred_locations"),
                preferred_job_types=payload.get("preferred_job_types"),
                expected_salary=payload.get("expected_salary"),
            )
        elif action == "touch_pulse":
            # For foundit, updating summary with same value pulses profile
            prof = client.get_profile()
            cur_sum = prof.get("profile_summary", "")
            return client.update_profile_summary(cur_sum)
        else:
            return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recommendations":
            return client.get_recommended_jobs(start=kwargs.get("start", 0), limit=kwargs.get("limit", 20))
        elif action == "applied_jobs":
            return client.get_applied_jobs(start=kwargs.get("start", 0), limit=kwargs.get("limit", 20))
        elif action == "saved_jobs":
            return client.get_saved_jobs(start=kwargs.get("start", 0), limit=kwargs.get("limit", 20))
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        return client.lookup_taxonomy(type_name=type_name, name=query, limit=kwargs.get("limit", 10))
