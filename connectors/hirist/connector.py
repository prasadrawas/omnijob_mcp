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
        res = client.search_jobs(query=query, location=location or "", min_exp=experience, size=limit, page=(start // limit) + 1 if limit else 1)
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            raw = {}
        job_list = raw.get("data") or raw.get("jobs") or []
        normalized = []
        for j in job_list:
            if not isinstance(j, dict):
                continue
            locs = j.get("locations", [])
            loc_str = ", ".join([l.get("name", "") if isinstance(l, dict) else str(l) for l in locs]) if locs else j.get("location", "")
            exp_str = f"{j.get('min', 0)}-{j.get('max', 0)} Yrs" if j.get("min") is not None else str(j.get("experience", ""))
            normalized.append({
                "id": str(j.get("id") or j.get("job_id", "")),
                "platform": "hirist",
                "title": j.get("title") or j.get("jobdesignation", ""),
                "company": j.get("companyName") or j.get("organization") or j.get("company", ""),
                "location": loc_str,
                "experience": exp_str,
                "salary": str(j.get("salary", "")),
                "skills": j.get("skills", []),
                "posted_date": str(j.get("createdAt") or j.get("posted_date", "")),
                "apply_url": j.get("jobDetailUrl") or f"https://www.hirist.tech/j/{j.get('id')}.html",
                "is_easy_apply": True,
                "metadata": {
                    "is_applied": j.get("isApplied", False),
                    "is_saved": j.get("isSaved", False),
                }
            })
        return {
            "platform": "hirist",
            "total": raw.get("totalJobs", raw.get("count", len(normalized))),
            "start": start,
            "limit": limit,
            "jobs": normalized,
            "raw": raw,
        }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_job_details(job_id=job_id)
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            return {"platform": "hirist", "id": job_id, "error": str(raw)}
        data = raw.get("data", raw)
        locs = data.get("locations", [])
        loc_str = ", ".join([l.get("name", "") if isinstance(l, dict) else str(l) for l in locs]) if locs else data.get("location", "")
        return {
            "platform": "hirist",
            "id": str(data.get("id") or job_id),
            "title": data.get("title") or data.get("jobdesignation", ""),
            "company": data.get("companyName") or data.get("organization") or "",
            "location": loc_str,
            "description": data.get("jobDescription") or data.get("introText") or "",
            "experience": f"{data.get('min', 0)}-{data.get('max', 0)} Yrs" if data.get("min") is not None else "",
            "salary": str(data.get("salary", "")),
            "skills": data.get("skills", []),
            "company_info": data.get("company_info", {}),
            "screening_questions": data.get("assessment") or data.get("screening_questions"),
            "can_apply": not data.get("isApplied", False),
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
        coverletter = answers.get("coverletter") if isinstance(answers, dict) else kwargs.get("coverletter")
        res = client.apply_to_job(job_id=job_id, coverletter=coverletter)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"result": raw}

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.save_job(job_id=job_id)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"result": raw}

    def unsave_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        res = client.unsave_job(job_id=job_id)
        raw = res[1] if isinstance(res, tuple) else res
        return raw if isinstance(raw, dict) else {"result": raw}

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        count = client.get_applied_job_count()
        return {
            "platform": "hirist",
            "applied_count": count,
            "message": f"Hirist reports {count} applications submitted.",
        }

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        res = client.get_profile()
        raw = res[1] if isinstance(res, tuple) else res
        if not isinstance(raw, dict):
            return {"platform": "hirist", "error": str(raw)}
        locs = raw.get("locations", [])
        loc_str = ", ".join([l.get("name", "") if isinstance(l, dict) else str(l) for l in locs]) if locs else raw.get("location", "")
        return {
            "platform": "hirist",
            "name": raw.get("name"),
            "email": raw.get("email"),
            "mobile": raw.get("phone"),
            "headline": raw.get("currentDesignation"),
            "summary": raw.get("about"),
            "location": loc_str,
            "skills": [s.get("name") if isinstance(s, dict) else str(s) for s in raw.get("skills", [])],
            "current_company": raw.get("currentOrganization"),
            "experience_years": raw.get("experienceYear"),
            "employment": raw.get("professionalInfo", []),
            "education": raw.get("educationInfo", []),
            "raw": raw,
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        payload = payload or {}
        if action == "touch_pulse":
            res = client.touch_profile_pulse()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action == "update_skills":
            skills = payload.get("skills") or kwargs.get("skills") or []
            res = client.update_skills(skills)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action == "update_basic":
            exp_raw = payload.get("exp_year") or payload.get("experience_years")
            exp_year_val: Optional[int] = None
            if exp_raw is not None:
                try:
                    exp_year_val = int(exp_raw)
                except (ValueError, TypeError):
                    exp_year_val = None

            exp_m_raw = payload.get("exp_month")
            exp_month_val: Optional[int] = None
            if exp_m_raw is not None:
                try:
                    exp_month_val = int(exp_m_raw)
                except (ValueError, TypeError):
                    exp_month_val = None

            res = client.update_personal_details(
                name=str(payload["name"]) if payload.get("name") is not None else None,
                current_designation=str(payload.get("current_designation") or payload.get("designation")) if (payload.get("current_designation") or payload.get("designation")) else None,
                current_organization=str(payload.get("current_organization") or payload.get("company")) if (payload.get("current_organization") or payload.get("company")) else None,
                exp_year=exp_year_val,
                exp_month=exp_month_val,
                current_ctc=str(payload["current_ctc"]) if payload.get("current_ctc") is not None else None,
                expected_ctc=str(payload["expected_ctc"]) if payload.get("expected_ctc") is not None else None,
                notice_period=payload.get("notice_period"),
                phone=payload.get("phone"),
                current_location=str(payload.get("current_location") or payload.get("location")) if (payload.get("current_location") or payload.get("location")) else None,
                linkedin=str(payload["linkedin"]) if payload.get("linkedin") is not None else None,
                career_objective=str(payload.get("career_objective") or payload.get("summary")) if (payload.get("career_objective") or payload.get("summary")) else None,
            )
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action == "update_employment":
            experiences: List[Dict[str, Any]] = [payload] if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
            res = client.update_work_experience(experiences=experiences)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        elif action == "update_education":
            educations: List[Dict[str, Any]] = [payload] if isinstance(payload, dict) else (payload if isinstance(payload, list) else [])
            res = client.update_education(educations=educations)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"result": raw}
        return {"success": False, "error": f"Unknown update action: {action}"}

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        if action == "recommendations" or action == "feed":
            res = client.get_job_feed()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "blocked_companies":
            res = client.get_blocked_companies()
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif action == "block_company":
            company_id = str(kwargs.get("company_id") or kwargs.get("company_name") or kwargs.get("company", ""))
            res = client.block_or_unblock_company(company_id=company_id, block=True)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        return {"success": False, "error": f"Unsupported account action: {action}"}

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        if type_name == "companies":
            res = client.suggest_companies(query=query)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        elif type_name == "institutes":
            res = client.suggest_institutes(query=query)
            raw = res[1] if isinstance(res, tuple) else res
            return raw if isinstance(raw, dict) else {"raw": raw}
        return {"platform": "hirist", "query": query, "suggestions": []}
