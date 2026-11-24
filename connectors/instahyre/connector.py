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
        res = client.search_jobs(query=query, location=location or "", limit=limit, offset=start)
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            raw = {}
        items = raw.get("objects") or raw.get("opportunities") or raw.get("jobs") or []
        normalized = []
        for j in items:
            comp = j.get("company_name") or j.get("employer_name")
            if not comp and isinstance(j.get("employer"), dict):
                comp = j.get("employer", {}).get("company_name") or j.get("employer", {}).get("name")
            kw = j.get("keywords")
            if isinstance(kw, list):
                skills = kw
            elif isinstance(kw, str) and kw:
                skills = [k.strip() for k in kw.split(",") if k.strip()]
            else:
                skills = j.get("skills") or []
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "instahyre",
                "title": j.get("title") or j.get("job_title", ""),
                "company": comp or "",
                "location": j.get("locations") or j.get("location") or "",
                "experience": str(j.get("experience", "")),
                "salary": str(j.get("salary", "")),
                "skills": skills,
                "posted_date": str(j.get("reviewed_at") or j.get("date_posted", "")),
                "apply_url": j.get("public_url") or f"https://www.instahyre.com/candidate/opportunities/?id={j.get('id')}",
                "is_easy_apply": True,
                "metadata": {
                    "is_interested": j.get("interview_status"),
                    "status": j.get("is_active"),
                }
            })
        meta = raw.get("meta", {})
        total = meta.get("total_count", len(normalized)) if isinstance(meta, dict) else len(normalized)
        return {
            "platform": "instahyre",
            "total": total,
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_job_details(job_id=int(job_id) if job_id.isdigit() else job_id)
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            return {"platform": "instahyre", "id": job_id, "error": str(raw)}
        return {
            "platform": "instahyre",
            "id": str(raw.get("job_id") or raw.get("id", job_id)),
            "title": raw.get("title") or raw.get("job_title", ""),
            "company": raw.get("company_name") or "",
            "location": str(raw.get("locations") or raw.get("location") or ""),
            "description": raw.get("description") or raw.get("job_description", ""),
            "experience": str(raw.get("experience", "")),
            "salary": str(raw.get("salary", "")),
            "skills": raw.get("skills", []),
            "company_info": {"employer_id": raw.get("employer_id")},
            "screening_questions": raw.get("questions"),
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
        res = client.apply_to_opportunity(job_id=int(job_id) if job_id.isdigit() else job_id, is_interested=True)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"result": raw}

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_candidate_profile()
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            return {"platform": "instahyre", "error": str(raw)}
        user = raw.get("user", {})
        skills_raw = raw.get("main_skills", "")
        skills = [s.strip() for s in skills_raw.split(",") if s.strip()] if isinstance(skills_raw, str) else []
        return {
            "platform": "instahyre",
            "name": user.get("full_name") or f"{user.get('first_name', '')} {user.get('last_name', '')}".strip(),
            "email": user.get("email"),
            "mobile": raw.get("phone"),
            "headline": raw.get("current_designation"),
            "summary": None,
            "location": None,
            "skills": skills,
            "current_company": raw.get("current_company"),
            "experience_years": raw.get("total_experience"),
            "employment": raw.get("previous_companies", []),
            "education": raw.get("education", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            res = client.touch_profile_pulse()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action in ["update_basic", "update_summary", "update_skills"]:
            personal = payload.get("personal")
            jsp = payload.get("jsp")
            if not personal and not jsp:
                personal_dict: Dict[str, Any] = {}
                if payload.get("current_company") or payload.get("company"):
                    personal_dict["current_company"] = str(payload.get("current_company") or payload.get("company"))
                if payload.get("current_designation") or payload.get("designation") or payload.get("headline"):
                    personal_dict["current_designation"] = str(payload.get("current_designation") or payload.get("designation") or payload.get("headline"))
                exp_raw = payload.get("experience_years") or payload.get("total_experience")
                if exp_raw is not None:
                    try:
                        personal_dict["total_experience"] = int(exp_raw)
                    except (ValueError, TypeError):
                        pass
                if payload.get("skills"):
                    sk = payload.get("skills")
                    personal_dict["main_skills"] = ",".join(str(s) for s in sk) if isinstance(sk, list) else str(sk)
                personal = personal_dict if personal_dict else None

            res = client.update_candidate_profile(personal=personal, jsp=jsp)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recommendations":
            res = client.get_matching_opportunities()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "recruiter_inbox" or action == "inbox":
            res = client.get_inbox_conversations()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "metrics" or action == "pipeline":
            res = client.get_pipeline_metrics()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "block_company":
            company_name = kwargs.get("company_name") or kwargs.get("company", "")
            res = client.block_or_unblock_company(company_name=company_name, action="block")
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_taxonomy(taxonomy_type=type_name)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"raw": raw}
