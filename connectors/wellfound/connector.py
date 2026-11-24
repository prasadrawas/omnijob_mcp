"""
Wellfound Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.wellfound import auth
from omnijob_mcp.connectors.wellfound.client import WellfoundClient


class WellfoundConnector(BaseConnector):
    name: str = "wellfound"
    display_name: str = "Wellfound (AngelList)"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "save",
        "unsave",
        "profile",
        "update_profile",
        "account",
    ]

    def __init__(self) -> None:
        self._client = WellfoundClient()

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
        raw = self._client.search_jobs(keywords=query, role=query, location=location or "", page=(start // limit) + 1 if limit else 1, limit=limit)
        items = raw.get("jobs", []) if isinstance(raw, dict) else (raw if isinstance(raw, list) else [])
        normalized = []
        for j in items:
            comp_obj = j.get("company")
            comp_name = j.get("company_name") or (comp_obj.get("name") if isinstance(comp_obj, dict) else comp_obj) or ""
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "wellfound",
                "title": j.get("title") or j.get("role", ""),
                "company": str(comp_name),
                "location": j.get("location") or "",
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary") or j.get("compensation", "")),
                "skills": j.get("skills", []),
                "posted_date": str(j.get("posted_date", "")),
                "apply_url": j.get("apply_url") or f"https://wellfound.com/jobs/{j.get('id')}",
                "is_easy_apply": True,
                "metadata": {
                    "equity": j.get("equity"),
                    "stage": j.get("stage"),
                }
            })
        return {
            "platform": "wellfound",
            "total": raw.get("total", len(normalized)) if isinstance(raw, dict) else len(normalized),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = self._client.get_job_details(job_id=job_id)
        if not isinstance(raw, dict):
            return {"platform": "wellfound", "id": job_id, "error": str(raw)}
        return {
            "platform": "wellfound",
            "id": str(raw.get("id", job_id)),
            "title": raw.get("title", ""),
            "company": raw.get("company_name") or raw.get("company", ""),
            "location": raw.get("location", ""),
            "description": raw.get("description", ""),
            "experience": str(raw.get("experience", "")),
            "salary": str(raw.get("salary") or raw.get("compensation", "")),
            "skills": raw.get("skills", []),
            "company_info": raw.get("company_info", {}),
            "screening_questions": raw.get("screening_questions"),
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
                "platform": "wellfound",
                "job_id": job_id,
                "status": "dry_run_success",
                "message": f"Dry-run application check succeeded for Wellfound job {job_id}",
            }
        return self._client.apply_to_job(job_id=job_id, note=kwargs.get("note", ""))

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self._client.bookmark_job(job_id=job_id)

    def unsave_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return self._client.unbookmark_job(job_id=job_id)

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        return self._client.get_pipeline()

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = self._client.get_profile()
        return {
            "platform": "wellfound",
            "name": raw.get("name"),
            "headline": raw.get("headline"),
            "summary": raw.get("bio"),
            "location": raw.get("location"),
            "skills": raw.get("skills", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            return self._client.touch_profile_pulse()
        elif action in ["update_basic", "update_summary", "update_skills"]:
            skills_raw = payload.get("skills")
            skills_list: Optional[List[str]] = None
            if isinstance(skills_raw, list):
                skills_list = [str(s) for s in skills_raw]
            elif isinstance(skills_raw, str):
                skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]

            exp_raw = payload.get("experience_years") or payload.get("years_experience")
            exp_float: Optional[float] = None
            if exp_raw is not None:
                try:
                    exp_float = float(exp_raw)
                except (ValueError, TypeError):
                    exp_float = None

            return self._client.update_profile(
                headline=str(payload["headline"]) if payload.get("headline") is not None else None,
                bio=str(payload.get("summary") or payload.get("bio")) if (payload.get("summary") or payload.get("bio")) else None,
                primary_role=str(payload.get("role") or payload.get("primary_role")) if (payload.get("role") or payload.get("primary_role")) else None,
                years_experience=exp_float,
                location=str(payload["location"]) if payload.get("location") is not None else None,
                skills=skills_list,
            )
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recruiter_inbox" or action == "inbox":
            return self._client.get_inbox()
        elif action == "analytics":
            return self._client.get_analytics()
        elif action == "pipeline":
            return self._client.get_pipeline()
        return {"success": False, "error": f"Unsupported account action: {action}"}
