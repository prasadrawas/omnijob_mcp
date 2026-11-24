"""
Granular deletion tools for individual items and subresources in naukri_mcp.
Enables precise deletion of specific projects, employments, skills, educations,
accomplishments, and resumes.

CAUTION: Deletions permanently modify candidate profile data. AI assistants should
exercise extreme caution and confirm user intent before triggering delete operations.
"""
from typing import Dict, Any, Optional

from omnijob_mcp.connectors.naukri.auth import resolve_auth_tokens
from omnijob_mcp.connectors.naukri.client import (
    delete_subresource,
    make_api_request,
    get_headers,
    RESUME_FORM_KEY
)
from omnijob_mcp.connectors.naukri.tools.profile import get_profile


def delete_profile_item(
    item_type: str,
    item_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a specific item/subresource from the candidate profile by its unique ID.
    CAUTION: This permanently removes the record from the live profile.

    :param item_type: One of 'projects', 'employments', 'itskills', 'educations', 'schools',
                      'onlineProfiles', 'workSamples', 'publications', 'presentations',
                      'patents', 'certifications', 'languages'.
    :param item_id: The unique ID string of the item to delete.
    :param nauk_at: Optional bearer token.
    :param nauk_rt: Optional refresh token.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    prof_res = get_profile(section="headline", nauk_at=at, nauk_rt=rt)
    pid = prof_res.get("profile_id", "")
    if not pid:
        return {"status": "error", "message": "Could not retrieve profile ID."}

    # Normalize entity name
    type_map = {
        "project": "projects",
        "projects": "projects",
        "employment": "employments",
        "employments": "employments",
        "work": "employments",
        "itskill": "itskills",
        "itskills": "itskills",
        "skill": "itskills",
        "education": "educations",
        "educations": "educations",
        "school": "schools",
        "schools": "schools",
        "language": "languages",
        "languages": "languages",
        "onlineprofile": "onlineProfiles",
        "onlineprofiles": "onlineProfiles",
        "worksample": "workSamples",
        "worksamples": "workSamples",
        "publication": "publications",
        "publications": "publications",
        "presentation": "presentations",
        "presentations": "presentations",
        "patent": "patents",
        "patents": "patents",
        "certification": "certifications",
        "certifications": "certifications"
    }

    norm_type = type_map.get(item_type.strip().lower(), item_type.strip())
    clean_id = item_id.strip()
    if not clean_id:
        return {"status": "error", "message": "Item ID cannot be empty."}

    success, resp = delete_subresource(pid, norm_type, clean_id, at, rt)
    if success:
        return {
            "status": "success",
            "message": f"Successfully deleted {norm_type} item '{clean_id}'.",
            "item_type": norm_type,
            "item_id": clean_id
        }
    return {
        "status": "error",
        "message": f"Failed to delete {norm_type} item '{clean_id}'.",
        "details": resp
    }


def delete_project(
    project_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a specific project entry from the profile by its projectId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("projects", project_id, nauk_at, nauk_rt)


def delete_employment(
    employment_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a specific employment / work experience entry by its employmentId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("employments", employment_id, nauk_at, nauk_rt)


def delete_it_skill(
    skill_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a specific IT skill entry from the structured skills table by its skillId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("itskills", skill_id, nauk_at, nauk_rt)


def delete_education(
    education_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a specific graduation / post-graduation education entry by its educationId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("educations", education_id, nauk_at, nauk_rt)


def delete_school(
    school_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a 10th or 12th class school entry by its schoolId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("schools", school_id, nauk_at, nauk_rt)


def delete_online_profile(
    profile_item_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete an online profile link (LinkedIn, GitHub, etc.) by its ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("onlineProfiles", profile_item_id, nauk_at, nauk_rt)


def delete_work_sample(
    sample_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a work sample link by its ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("workSamples", sample_id, nauk_at, nauk_rt)


def delete_publication(
    publication_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a research publication or white paper by its ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("publications", publication_id, nauk_at, nauk_rt)


def delete_presentation(
    presentation_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete an online presentation link by its ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("presentations", presentation_id, nauk_at, nauk_rt)


def delete_patent(
    patent_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a patent filing or grant by its ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("patents", patent_id, nauk_at, nauk_rt)


def delete_certification(
    certification_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a certification entry by its certificationId.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("certifications", certification_id, nauk_at, nauk_rt)


def delete_language(
    language_id: str,
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete a language entry by its language ID.
    CAUTION: Permanent deletion.
    """
    return delete_profile_item("languages", language_id, nauk_at, nauk_rt)


def delete_resume(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete the uploaded resume document file from the candidate profile.
    CAUTION: Permanent deletion.
    """
    at, rt = resolve_auth_tokens(nauk_at, nauk_rt)
    headers = get_headers(at, rt, app_id="105", system_id="Naukri")
    url = "https://files.naukri.com/0/deleteFile.php"
    data_payload = {
        "appId": 105,
        "formKey": RESUME_FORM_KEY,
        "fileKey": "textCV"
    }
    import urllib.parse
    encoded = urllib.parse.urlencode(data_payload).encode("utf-8")
    headers["Content-Type"] = "application/x-www-form-urlencoded"

    status, resp = make_api_request(url, method="POST", headers=headers, data=encoded)
    return {
        "status": "success" if status in (200, 204) else "error",
        "http_status": status,
        "message": "Resume deletion request executed.",
        "details": resp
    }


def delete_photo(
    nauk_at: Optional[str] = None,
    nauk_rt: Optional[str] = None
) -> Dict[str, Any]:
    """
    Delete the uploaded candidate display photo from the candidate profile.
    CAUTION: Permanent deletion.
    """
    from omnijob_mcp.connectors.naukri.tools.photo import delete_photo as _del_photo
    return _del_photo(nauk_at=nauk_at, nauk_rt=nauk_rt)

