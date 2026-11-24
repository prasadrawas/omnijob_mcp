"""
Greenhouse ATS Platform Connector for OmniJob MCP.
"""
from typing import Any, Dict, List, Optional

from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.connectors.greenhouse import auth
from omnijob_mcp.connectors.greenhouse import client


class GreenhouseConnector(BaseConnector):
    name: str = "greenhouse"
    display_name: str = "Greenhouse ATS"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "can_apply",
        "account",
        "boards",
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
        board_token = kwargs.get("board_token")
        if board_token:
            raw = client.search_jobs(board_token=board_token, query=query, location=location)
        else:
            raw = client.search_multi_board_jobs(query=query, location=location, limit_per_board=10)
        items = raw.get("jobs", [])
        normalized = []
        for j in items:
            normalized.append({
                "id": str(j.get("id", "")),
                "platform": "greenhouse",
                "title": j.get("title", ""),
                "company": j.get("board_token") or j.get("company", ""),
                "location": j.get("location", ""),
                "experience": None,
                "salary": None,
                "skills": [],
                "posted_date": j.get("updated_at"),
                "apply_url": j.get("absolute_url") or f"https://job-boards.greenhouse.io/{j.get('board_token')}/jobs/{j.get('id')}",
                "is_easy_apply": False,
                "metadata": {
                    "board_token": j.get("board_token"),
                    "departments": j.get("departments", []),
                    "offices": j.get("offices", []),
                }
            })
        return {
            "platform": "greenhouse",
            "total": raw.get("total_matches", len(normalized)),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        board_token = kwargs.get("board_token")
        if not board_token and ":" in job_id:
            board_token, job_id = job_id.split(":", 1)
        if not board_token:
            board_token = "cloudflare"  # default fallback
        raw = client.get_job_details(board_token=board_token, job_id=job_id)
        if not raw.get("success"):
            return raw
        job = raw.get("job", {})
        return {
            "platform": "greenhouse",
            "id": f"{board_token}:{job_id}",
            "title": job.get("title", ""),
            "company": board_token,
            "location": job.get("location", {}).get("name", "") if isinstance(job.get("location"), dict) else str(job.get("location", "")),
            "description": raw.get("description", ""),
            "experience": None,
            "salary": None,
            "skills": [],
            "company_info": {"board_token": board_token},
            "screening_questions": raw.get("questions_schema", []),
            "can_apply": True,
            "metadata": raw,
        }

    def can_job_apply(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        board_token = kwargs.get("board_token")
        if not board_token and ":" in job_id:
            board_token, job_id = job_id.split(":", 1)
        return client.validate_application(board_token=board_token or "cloudflare", job_id=job_id, candidate_data=kwargs.get("answers", {}))

    def apply_to_job(
        self,
        job_id: str,
        answers: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        board_token = kwargs.get("board_token")
        if not board_token and ":" in job_id:
            board_token, job_id = job_id.split(":", 1)
        candidate_data = answers or {}
        return client.apply_to_job(
            board_token=board_token or "cloudflare",
            job_id=job_id,
            candidate_data=candidate_data,
            resume_file_path=kwargs.get("resume_file_path"),
            dry_run=dry_run,
        )

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        history = auth.get_pipeline_history()
        return {
            "platform": "greenhouse",
            "total": len(history),
            "jobs": history[start:start + limit],
        }

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "pipeline":
            return {"pipeline_history": auth.get_pipeline_history()}
        elif action == "boards":
            return {"tracked_boards": auth.get_tracked_boards()}
        elif action == "add_board":
            b = kwargs.get("board_token") or kwargs.get("board")
            if b:
                auth.add_tracked_board(b)
            return {"tracked_boards": auth.get_tracked_boards()}
        elif action == "remove_board":
            b = kwargs.get("board_token") or kwargs.get("board")
            if b:
                auth.remove_tracked_board(b)
            return {"tracked_boards": auth.get_tracked_boards()}
        return {"success": False, "error": f"Unsupported account action: {action}"}
