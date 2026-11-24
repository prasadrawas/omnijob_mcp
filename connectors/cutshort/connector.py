"""
Cutshort Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.cutshort import auth
from omnijob_mcp.connectors.cutshort import client


class CutshortConnector(BaseConnector):
    name: str = "cutshort"
    display_name: str = "Cutshort.io"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "save",
        "profile",
        "update_profile",
        "account",
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
        status_code, raw = client.search_jobs(query=query, location=location or "", min_exp=experience, limit=limit)
        if not isinstance(raw, dict):
            raw = {}
        items = raw.get("jobs") or raw.get("opportunities") or []
        normalized = []
        for j in items:
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "cutshort",
                "title": j.get("title") or j.get("role", ""),
                "company": j.get("company_name") or j.get("company", ""),
                "location": j.get("location") or j.get("city", ""),
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary", "")),
                "skills": j.get("skills", []),
                "posted_date": str(j.get("posted_date", "")),
                "apply_url": f"https://cutshort.io/job/{j.get('id')}",
                "is_easy_apply": True,
                "metadata": {
                    "is_bookmarked": j.get("is_bookmarked"),
                    "status": j.get("status"),
                }
            })
        return {
            "platform": "cutshort",
            "total": raw.get("total", len(normalized)),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_job_details(job_id=job_id)
        if not isinstance(raw, dict):
            return {"platform": "cutshort", "id": job_id, "error": str(raw)}
        return {
            "platform": "cutshort",
            "id": str(raw.get("id", job_id)),
            "title": raw.get("title") or raw.get("role", ""),
            "company": raw.get("company_name") or raw.get("company", ""),
            "location": raw.get("location", ""),
            "description": raw.get("job_description") or raw.get("description", ""),
            "experience": str(raw.get("experience", "")),
            "salary": str(raw.get("salary", "")),
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
                "platform": "cutshort",
                "job_id": job_id,
                "status": "dry_run_success",
                "message": f"Dry-run application check succeeded for Cutshort job {job_id}",
            }
        return client.apply_to_job(job_id=job_id, message=kwargs.get("message", ""))

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        return client.save_job(job_id=job_id)

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_candidate_profile()
        return {
            "platform": "cutshort",
            "name": raw.get("name"),
            "email": raw.get("email"),
            "mobile": raw.get("phone"),
            "headline": raw.get("headline"),
            "summary": raw.get("bio") or raw.get("summary"),
            "location": raw.get("location"),
            "skills": raw.get("skills", []),
            "employment": raw.get("experiences", []),
            "education": raw.get("educations", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            return client.touch_profile_pulse()
        elif action in ["update_basic", "update_summary", "update_skills"]:
            return client.update_candidate_profile(payload)
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recruiter_inbox" or action == "inbox":
            return client.get_conversations()
        elif action == "metrics" or action == "pipeline":
            return client.get_pipeline_metrics()
        elif action == "reply":
            return client.send_reply_to_recruiter(
                conversation_id=kwargs.get("conversation_id", ""),
                message=kwargs.get("message", ""),
            )
        return {"success": False, "error": f"Unsupported account action: {action}"}
