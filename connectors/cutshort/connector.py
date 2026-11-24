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
        res = client.search_jobs(query=query, location=location or "", min_exp=experience, limit=limit)
        raw = res[1] if isinstance(res, tuple) else res
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
        res = client.get_job_details(job_id=job_id)
        raw = res[1] if isinstance(res, tuple) else res
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
        res = client.apply_to_job(job_id=job_id, context=kwargs.get("context") or answers)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"status": "error", "raw": raw}

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.save_job(job_id=job_id)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"status": "error", "raw": raw}

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_candidate_profile()
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            return {"platform": "cutshort", "error": str(raw)}
        return {
            "platform": "cutshort",
            "name": raw.get("name"),
            "email": raw.get("email"),
            "mobile": raw.get("phone"),
            "headline": raw.get("headline"),
            "summary": raw.get("summary") or raw.get("bio"),
            "location": str(raw.get("locations", [""])[0] if isinstance(raw.get("locations"), list) and raw.get("locations") else raw.get("location", "")),
            "skills": raw.get("skills", []),
            "current_company": raw.get("current_company"),
            "experience_years": raw.get("experience_years"),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            res = client.touch_profile_pulse()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action in ["update_basic", "update_summary", "update_headline", "update_skills"]:
            raw_locs = payload.get("locations")
            loc_list: Optional[List[str]] = None
            if payload.get("location"):
                loc_list = [str(payload.get("location"))]
            elif isinstance(raw_locs, list):
                loc_list = [str(x) for x in raw_locs]

            skills_raw = payload.get("skills")
            skills_list: Optional[List[str]] = None
            if isinstance(skills_raw, list):
                skills_list = [str(x) for x in skills_raw]
            elif isinstance(skills_raw, str):
                skills_list = [s.strip() for s in skills_raw.split(",") if s.strip()]

            exp_raw = payload.get("experience_years") or payload.get("experience")
            exp_val: Optional[int] = None
            if exp_raw is not None:
                try:
                    exp_val = int(exp_raw)
                except (ValueError, TypeError):
                    exp_val = None

            sal_raw = payload.get("preferred_salary")
            sal_val: Optional[int] = None
            if sal_raw is not None:
                try:
                    sal_val = int(sal_raw)
                except (ValueError, TypeError):
                    sal_val = None

            res = client.update_candidate_profile(
                headline=str(payload["headline"]) if payload.get("headline") is not None else None,
                summary=str(payload.get("summary") or payload.get("bio")) if (payload.get("summary") or payload.get("bio")) else None,
                experience=exp_val,
                current_company=str(payload["current_company"]) if payload.get("current_company") is not None else None,
                skills=skills_list,
                locations=loc_list,
                preferred_salary=sal_val,
            )
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recruiter_inbox" or action == "inbox":
            res = client.get_conversations()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "metrics" or action == "pipeline":
            res = client.get_pipeline_metrics()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "reply":
            thread_id = str(kwargs.get("thread_id") or kwargs.get("conversation_id", ""))
            res = client.send_reply_to_recruiter(
                thread_id=thread_id,
                message=str(kwargs.get("message", "")),
            )
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        return {"success": False, "error": f"Unsupported account action: {action}"}
