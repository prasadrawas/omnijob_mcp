"""
Instahyre Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.instahyre import auth
from omnijob_mcp.connectors.instahyre import client


class InstahyreConnector(BaseConnector):
    name: str = "instahyre"
    display_name: str = "Instahyre"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
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
        status_code, raw = client.search_jobs(query=query, location=location or "", limit=limit, offset=start)
        if not isinstance(raw, dict):
            raw = {}
        items = raw.get("opportunities") or raw.get("jobs") or []
        normalized = []
        for j in items:
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "instahyre",
                "title": j.get("title") or j.get("job_title", ""),
                "company": j.get("company_name") or j.get("company", ""),
                "location": j.get("location") or j.get("city", ""),
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary", "")),
                "skills": j.get("skills", []),
                "posted_date": str(j.get("posted_date", "")),
                "apply_url": f"https://www.instahyre.com/candidate/opportunities/?id={j.get('id')}",
                "is_easy_apply": True,
                "metadata": {
                    "is_interested": j.get("is_interested"),
                    "status": j.get("status"),
                }
            })
        return {
            "platform": "instahyre",
            "total": raw.get("count", len(normalized)),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_job_details(opportunity_id=int(job_id) if job_id.isdigit() else job_id)
        if not isinstance(raw, dict):
            return {"platform": "instahyre", "id": job_id, "error": str(raw)}
        opp = raw.get("opportunity", raw)
        return {
            "platform": "instahyre",
            "id": str(opp.get("id", job_id)),
            "title": opp.get("job_title") or opp.get("title", ""),
            "company": opp.get("company_name") or opp.get("company", ""),
            "location": opp.get("location", ""),
            "description": opp.get("job_description") or opp.get("description", ""),
            "experience": str(opp.get("experience", "")),
            "salary": str(opp.get("salary", "")),
            "skills": opp.get("skills", []),
            "company_info": opp.get("company_info", {}),
            "screening_questions": opp.get("questions"),
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
                "platform": "instahyre",
                "job_id": job_id,
                "status": "dry_run_success",
                "message": f"Dry-run application check succeeded for Instahyre job {job_id}",
            }
        opp_id = int(job_id) if job_id.isdigit() else job_id
        return client.apply_to_opportunity(opportunity_id=opp_id, answers=answers)

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        raw = client.get_candidate_profile()
        return {
            "platform": "instahyre",
            "name": raw.get("name"),
            "email": raw.get("email"),
            "mobile": raw.get("phone"),
            "headline": raw.get("current_title") or raw.get("headline"),
            "summary": raw.get("summary"),
            "location": raw.get("location"),
            "skills": raw.get("skills", []),
            "employment": raw.get("experiences", []),
            "education": raw.get("education", []),
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
        if action == "recommendations":
            return client.get_matching_opportunities()
        elif action == "recruiter_inbox" or action == "inbox":
            return client.get_inbox_conversations()
        elif action == "metrics" or action == "pipeline":
            return client.get_pipeline_metrics()
        elif action == "block_company":
            company_id = kwargs.get("company_id")
            return client.block_or_unblock_company(company_id=company_id, block=True)
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        return client.get_taxonomy(category=type_name, query=query)
