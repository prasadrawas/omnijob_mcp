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
        answers_list = None
        if isinstance(answers, list):
            answers_list = answers
        elif isinstance(answers, dict):
            answers_list = [{"questionId": str(k), "answer": v} for k, v in answers.items()]
        return client.apply_to_job(job_id=job_id, answers=answers_list, dry_run=dry_run)

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
            full_name = payload.get("full_name") or payload.get("name") or "Prasad Rawas"
            years = int(payload.get("years") or payload.get("total_experience_years") or 5)
            months = int(payload.get("months") or payload.get("total_experience_months") or 0)
            city_text = payload.get("city_text") or payload.get("city") or payload.get("location") or "Pune"
            return client.update_basic_profile(
                full_name=full_name,
                years=years,
                months=months,
                city_text=city_text,
            )
        elif action == "update_skills":
            skills = payload.get("skills") or kwargs.get("skills") or []
            return client.add_skills(skills)
        elif action == "update_employment":
            return client.update_employment(
                employment_id=payload.get("employment_id") or payload.get("id"),
                company_text=payload.get("company_text") or payload.get("company_name") or payload.get("company", "Aeologic Technologies Pvt Ltd"),
                designation_text=payload.get("designation_text") or payload.get("designation", "Software Engineer"),
                start_date=payload.get("start_date", "2021-08-01"),
                current=payload.get("current", payload.get("is_current", True)),
                salary=payload.get("salary") or payload.get("annual_salary", 1200000),
                notice_days=payload.get("notice_days") or 30,
            )
        elif action == "update_education":
            return client.add_education(
                qualification_id=payload.get("qualification_id", "7de0a237-15bc-4ab0-8546-c1a7d8b1d724"),
                qualification_text=payload.get("qualification_text", payload.get("degree_name", "Masters in Technology (M.Tech/M.E)")),
                specialization_id=payload.get("specialization_id", "cbdfaea4-43bd-450f-9688-d5e1f4622552"),
                specialization_text=payload.get("specialization_text", payload.get("specialization", "Computers")),
                college_id=payload.get("college_id", "3f945c5e-0aec-11ec-9a03-0242ac130003"),
                college_text=payload.get("college_text", payload.get("institute_name", "Pune Institute of Computer Technology, Society for Computer Technology and Research")),
                year_of_passing=int(payload.get("year_of_passing") or payload.get("passing_year") or 2022),
            )
        elif action == "touch_pulse":
            prof = client.get_profile()
            cur_sum = prof.get("profile_summary", "")
            return client.update_profile_summary(cur_sum)
        else:
            return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recommendations":
            return client.get_recommended_jobs()
        elif action == "applied_jobs":
            return client.get_applied_jobs(start=kwargs.get("start", 0), limit=kwargs.get("limit", 20))
        elif action == "saved_jobs":
            return client.get_saved_jobs(start=kwargs.get("start", 0), limit=kwargs.get("limit", 20))
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        return client.lookup_taxonomy(type_name=type_name, name=query, limit=kwargs.get("limit", 10))
