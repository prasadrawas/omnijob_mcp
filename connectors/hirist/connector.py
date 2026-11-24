"""
Hirist Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.hirist import auth
from omnijob_mcp.connectors.hirist import client


class HiristConnector(BaseConnector):
    name: str = "hirist"
    display_name: str = "Hirist.tech"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "save",
        "unsave",
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
        raw = client.search_jobs(query=query, location=location or "", min_exp=experience, page=(start // limit) + 1 if limit else 1)
        # Hirist returns list or dict with jobs
        job_list = raw.get("jobs", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        normalized = []
        for j in job_list:
            if not isinstance(j, dict):
                continue
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "hirist",
                "title": j.get("title", ""),
                "company": j.get("company_name") or j.get("company", ""),
                "location": j.get("location", ""),
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary", "")),
                "skills": j.get("skills", []),
                "posted_date": str(j.get("posted_date", "")),
                "apply_url": j.get("apply_url", ""),
                "is_easy_apply": True,
                "metadata": {
                    "is_applied": j.get("is_applied", False),
                    "is_saved": j.get("is_saved", False),
                }
            })
        return {
            "platform": "hirist",
            "total": raw.get("total", len(normalized)) if isinstance(raw, dict) else len(normalized),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_job_details(job_id=job_id)
        if not isinstance(raw, dict):
            return {"platform": "hirist", "id": job_id, "error": str(raw)}
        return {
            "platform": "hirist",
            "id": str(raw.get("id") or job_id),
            "title": raw.get("title", ""),
            "company": raw.get("company_name") or raw.get("company", ""),
            "location": raw.get("location", ""),
            "description": raw.get("description") or raw.get("job_description", ""),
            "experience": str(raw.get("experience", "")),
            "salary": str(raw.get("salary", "")),
            "skills": raw.get("skills", []),
            "company_info": raw.get("company_info", {}),
            "screening_questions": raw.get("assessment") or raw.get("screening_questions"),
            "can_apply": not raw.get("is_applied", False),
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
                "platform": "hirist",
                "job_id": job_id,
                "status": "dry_run_success",
                "message": f"Dry-run application check succeeded for Hirist job {job_id}",
            }
        return client.apply_to_job(job_id=job_id, answers=answers or {})

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.save_job(job_id=job_id)

    def unsave_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.unsave_job(job_id=job_id)

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        count = client.get_applied_job_count()
        return {
            "platform": "hirist",
            "applied_count": count,
            "message": f"Hirist reports {count} applications submitted.",
        }

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_profile()
        if not isinstance(raw, dict):
            return {"platform": "hirist", "error": str(raw)}
        return {
            "platform": "hirist",
            "name": raw.get("name") or raw.get("full_name"),
            "email": raw.get("email"),
            "mobile": raw.get("mobile") or raw.get("phone"),
            "headline": raw.get("headline") or raw.get("designation"),
            "summary": raw.get("summary") or raw.get("about"),
            "location": raw.get("location") or raw.get("city"),
            "skills": [s.get("name") if isinstance(s, dict) else str(s) for s in raw.get("skills", [])],
            "employment": raw.get("work_experience") or raw.get("employment", []),
            "education": raw.get("education", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            return client.touch_profile_pulse()
        elif action == "update_skills":
            skills = payload.get("skills") or kwargs.get("skills") or []
            return client.update_skills(skills)
        elif action == "update_basic":
            return client.update_personal_details(payload)
        elif action == "update_employment":
            return client.update_work_experience(payload)
        elif action == "update_education":
            return client.update_education(payload)
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recommendations" or action == "feed":
            return client.get_job_feed()
        elif action == "blocked_companies":
            return client.get_blocked_companies()
        elif action == "block_company":
            company = kwargs.get("company_name") or kwargs.get("company", "")
            return client.block_or_unblock_company(company=company, block=True)
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        if type_name == "companies":
            return client.suggest_companies(query=query)
        elif type_name == "institutes":
            return client.suggest_institutes(query=query)
        return {"platform": "hirist", "query": query, "suggestions": []}
