"""
Duplicate detection and cleanup tools for naukri_mcp.
"""
from typing import Dict, Any, List, Optional

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import delete_subresource
from omnijob_mcp.connectors.naukri.serializers import normalize_title
from omnijob_mcp.connectors.naukri.tools.profile import get_profile


def audit_duplicates(
    canonical_skills: Optional[List[str]] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Audit live profile for duplicate projects and duplicate/obsolete IT skills.

    :param canonical_skills: Optional list of valid skills. Any skill not in this list is flagged as stale/obsolete.
    :param nauk_at: Optional access token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="all", nauk_at=at, nauk_rt=rt)
    profile_data = prof_res.get("data", {})
    pid = prof_res.get("profile_id", "")

    # 1. Duplicate projects
    seen_prefixes = {}
    dup_projects = []
    for prj in profile_data.get("projects", []):
        raw_title = prj.get("projectTitle", "").strip()
        pr_id = prj.get("projectId")
        if not raw_title or not pr_id:
            continue
        norm_key = normalize_title(raw_title)[:18]
        if norm_key in seen_prefixes:
            dup_projects.append({"id": str(pr_id), "title": raw_title, "reason": "duplicate project"})
        else:
            seen_prefixes[norm_key] = str(pr_id)

    # 2. Duplicate / Stale IT skills
    canonical_set = {s.strip().lower() for s in canonical_skills} if canonical_skills else set()
    seen_skills = {}
    to_delete_skills = []
    for its in profile_data.get("itskills", []):
        name = its.get("skill", "").strip()
        sid = its.get("skillId")
        if not name or not sid:
            continue
        name_lower = name.lower()

        if name_lower in seen_skills:
            to_delete_skills.append({"id": str(sid), "name": name, "reason": "duplicate skill"})
        elif canonical_set and name_lower not in canonical_set:
            to_delete_skills.append({"id": str(sid), "name": name, "reason": "not in canonical skills"})
        else:
            seen_skills[name_lower] = str(sid)

    return {
        "status": "success",
        "profile_id": pid,
        "duplicate_projects_count": len(dup_projects),
        "duplicate_projects": dup_projects,
        "stale_or_duplicate_skills_count": len(to_delete_skills),
        "stale_or_duplicate_skills": to_delete_skills
    }


def delete_duplicates(
    canonical_skills: Optional[List[str]] = None,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Purge duplicate projects and duplicate/obsolete IT skills from live Naukri profile.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    audit = audit_duplicates(canonical_skills=canonical_skills, nauk_at=at, nauk_rt=rt)
    pid = audit.get("profile_id", "")

    deleted_projects = []
    for prj in audit.get("duplicate_projects", []):
        success, _ = delete_subresource(pid, "projects", prj["id"], at, rt)
        if success:
            deleted_projects.append(prj)

    deleted_skills = []
    for sk in audit.get("stale_or_duplicate_skills", []):
        success, _ = delete_subresource(pid, "itskills", sk["id"], at, rt)
        if success:
            deleted_skills.append(sk)

    return {
        "status": "success",
        "deleted_projects_count": len(deleted_projects),
        "deleted_projects": deleted_projects,
        "deleted_skills_count": len(deleted_skills),
        "deleted_skills": deleted_skills
    }


# Backward compatibility aliases
audit_profile_duplicates = audit_duplicates
delete_profile_duplicates = delete_duplicates

