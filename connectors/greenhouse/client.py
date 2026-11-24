"""
Greenhouse Job Board API Client.
Provides complete integration with Greenhouse Job Board API endpoints:
- Job discovery & search across single or multiple organizations
- Detailed job descriptions & dynamic questions schema inspection
- Departments & offices hierarchy
- Application validation & multipart/form-data submission with Basic Auth
- Transparent diagnostic reporting for employer API key requirements
"""
import re
import base64
import html
import mimetypes
from pathlib import Path
from typing import Dict, Any, List, Optional, Tuple, Union

import httpx

from omnijob_mcp.core.cache import TTLCache
from omnijob_mcp.connectors.greenhouse.auth import (
    GREENHOUSE_API_BASE,
    GREENHOUSE_HOSTED_BASE,
    GREENHOUSE_MODERN_HOSTED_BASE,
    get_api_key,
    get_tracked_boards,
    record_pipeline_event,
)

# Global TTL cache for jobs and taxonomy (5 min default)
job_cache = TTLCache(default_ttl=300, max_size=1000)

DEFAULT_TIMEOUT = 12.0
USER_AGENT = "GreenhouseMCP/1.0.0 (Unified Model Context Protocol Client; +https://github.com/prasadrawas/greenhouse_mcp)"


def _clean_html_text(html_content: Optional[str]) -> str:
    """Convert HTML string to readable plain text / markdown representation."""
    if not html_content:
        return ""
    text = html_content
    # Decode HTML entities twice in case of double-encoding
    text = html.unescape(text)
    text = html.unescape(text)
    # Convert headings
    text = re.sub(r'<h[1-6][^>]*>(.*?)</h[1-6]>', r'\n\n### \1\n', text, flags=re.I)
    # Convert paragraphs and breaks
    text = re.sub(r'<br\s*/?>', '\n', text, flags=re.I)
    text = re.sub(r'</p>', '\n\n', text, flags=re.I)
    # Convert list items
    text = re.sub(r'<li[^>]*>(.*?)</li>', r'\n* \1', text, flags=re.I)
    # Strip remaining tags
    text = re.sub(r'<[^>]+>', '', text)
    # Normalize excessive newlines and whitespace
    text = re.sub(r'\n{3,}', '\n\n', text)
    return text.strip()


def parse_job_questions(raw_questions: List[Dict[str, Any]]) -> List[Dict[str, Any]]:
    """
    Parse Greenhouse's raw dynamic questions schema into normalized, user-friendly fields.
    Each question defines field name, label, type, required status, and options.
    """
    parsed = []
    for q in raw_questions:
        label = q.get("label", "").strip()
        required = bool(q.get("required", False))
        fields = q.get("fields", [])

        if not fields:
            # Fallback if no subfields
            parsed.append({
                "name": q.get("name", "unknown"),
                "label": label,
                "type": q.get("type", "text"),
                "required": required,
                "options": [],
                "description": q.get("description", ""),
            })
            continue

        for f in fields:
            field_name = f.get("name", "")
            field_type = f.get("type", "input_text")
            raw_values = f.get("values", [])

            # Format options for select / multiselect
            options = []
            if raw_values:
                for v in raw_values:
                    if isinstance(v, dict):
                        options.append({
                            "label": v.get("label", str(v.get("value", ""))),
                            "value": v.get("value"),
                        })
                    else:
                        options.append({"label": str(v), "value": v})

            # Determine simplified type category
            simplified_type = "text"
            if field_type in ("input_file", "file"):
                simplified_type = "file"
            elif field_type in ("textarea",):
                simplified_type = "textarea"
            elif field_type in ("multi_value_single_select", "single_select"):
                simplified_type = "single_select"
            elif field_type in ("multi_value_multi_select", "multi_select"):
                simplified_type = "multi_select"

            is_custom = field_name.startswith("question_")

            parsed.append({
                "field_name": field_name,
                "label": label,
                "required": required,
                "type": simplified_type,
                "raw_type": field_type,
                "is_custom": is_custom,
                "options": options,
            })
    return parsed


# ===========================================================================
# 1. JOB SEARCH & DETAILS
# ===========================================================================

def search_jobs(
    board_token: str,
    query: Optional[str] = None,
    location: Optional[str] = None,
    department: Optional[str] = None,
    office: Optional[str] = None,
    limit: int = 50,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Search active jobs for a specific company board on Greenhouse.
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs?content=true
    """
    token = board_token.strip().lower()
    cache_key = f"jobs_{token}"
    data = job_cache.get(cache_key) if use_cache else None

    if data is None:
        url = f"{GREENHOUSE_API_BASE}/boards/{token}/jobs?content=true"
        headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}
        try:
            with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
                resp = http_client.get(url, headers=headers)
                if resp.status_code == 404:
                    return {
                        "status_code": 404,
                        "board_token": token,
                        "error": f"Board '{token}' not found on Greenhouse.",
                        "jobs": [],
                        "total_found": 0,
                    }
                resp.raise_for_status()
                data = resp.json()
                job_cache.set(cache_key, data, ttl=300)
        except Exception as e:
            return {
                "status_code": getattr(getattr(e, "response", None), "status_code", 500),
                "board_token": token,
                "error": f"Failed to retrieve jobs for '{token}': {str(e)}",
                "jobs": [],
                "total_found": 0,
            }

    raw_jobs = data.get("jobs", []) if isinstance(data, dict) else []
    filtered = []

    q_lower = query.strip().lower() if query else None
    loc_lower = location.strip().lower() if location else None
    dept_lower = department.strip().lower() if department else None
    off_lower = office.strip().lower() if office else None

    for j in raw_jobs:
        title = j.get("title", "")
        loc_obj = j.get("location") or {}
        loc_name = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)

        # Department checking
        depts = j.get("departments") or []
        dept_names = [d.get("name", "") for d in depts if isinstance(d, dict)]
        dept_str = " ".join(dept_names)

        # Offices checking
        offices = j.get("offices") or []
        off_names = [o.get("name", "") for o in offices if isinstance(o, dict)]
        off_str = " ".join(off_names)

        # Query filter
        if q_lower:
            match_title = q_lower in title.lower()
            match_dept = q_lower in dept_str.lower()
            match_loc = q_lower in loc_name.lower()
            if not (match_title or match_dept or match_loc):
                continue

        # Location filter
        if loc_lower:
            if loc_lower not in loc_name.lower() and loc_lower not in off_str.lower():
                continue

        # Department filter
        if dept_lower:
            if not any(dept_lower in d.lower() for d in dept_names):
                continue

        # Office filter
        if off_lower:
            if not any(off_lower in o.lower() for o in off_names):
                continue

        filtered.append({
            "id": j.get("id"),
            "board_token": token,
            "title": title,
            "location": loc_name,
            "departments": dept_names,
            "offices": off_names,
            "updated_at": j.get("updated_at"),
            "absolute_url": j.get("absolute_url") or f"{GREENHOUSE_HOSTED_BASE}/{token}/jobs/{j.get('id')}",
            "job_post_url": f"{GREENHOUSE_MODERN_HOSTED_BASE}/{token}/jobs/{j.get('id')}",
        })

        if len(filtered) >= limit:
            break

    return {
        "status_code": 200,
        "board_token": token,
        "query": query,
        "location": location,
        "department": department,
        "office": office,
        "total_on_board": len(raw_jobs),
        "total_matched": len(filtered),
        "jobs": filtered,
    }


def search_multi_board_jobs(
    board_tokens: Optional[List[str]] = None,
    query: Optional[str] = None,
    location: Optional[str] = None,
    department: Optional[str] = None,
    limit_per_board: int = 15,
) -> Dict[str, Any]:
    """
    Search jobs across multiple company boards simultaneously.
    If board_tokens is omitted, uses the active tracked boards registry.
    """
    targets = board_tokens or get_tracked_boards()
    aggregated_jobs = []
    board_summaries = {}

    for token in targets:
        res = search_jobs(
            board_token=token,
            query=query,
            location=location,
            department=department,
            limit=limit_per_board,
        )
        if res.get("status_code") == 200:
            board_jobs = res.get("jobs", [])
            aggregated_jobs.extend(board_jobs)
            board_summaries[token] = {
                "total_on_board": res.get("total_on_board", 0),
                "matched": len(board_jobs),
                "status": "ok",
            }
        else:
            board_summaries[token] = {
                "status": "error",
                "error": res.get("error", "Unknown error"),
            }

    return {
        "status_code": 200,
        "queried_boards": targets,
        "total_jobs_found": len(aggregated_jobs),
        "board_summaries": board_summaries,
        "jobs": aggregated_jobs,
    }


def get_job_details(
    board_token: str,
    job_id: Union[str, int],
    include_questions: bool = True,
    use_cache: bool = True,
) -> Dict[str, Any]:
    """
    Retrieve comprehensive details for a specific Greenhouse job posting,
    including full job description and dynamic question fields.
    GET https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}?questions=true
    """
    token = board_token.strip().lower()
    jid = str(job_id).strip()
    cache_key = f"job_{token}_{jid}_{include_questions}"
    cached = job_cache.get(cache_key) if use_cache else None

    if cached:
        return cached

    q_param = "?questions=true" if include_questions else ""
    url = f"{GREENHOUSE_API_BASE}/boards/{token}/jobs/{jid}{q_param}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 404:
                return {
                    "status_code": 404,
                    "board_token": token,
                    "job_id": jid,
                    "error": f"Job {jid} on board '{token}' not found.",
                }
            resp.raise_for_status()
            data = resp.json()
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "board_token": token,
            "job_id": jid,
            "error": f"Failed to retrieve job details: {str(e)}",
        }

    raw_content = data.get("content", "")
    plain_content = _clean_html_text(raw_content)

    depts = [d.get("name", "") for d in (data.get("departments") or []) if isinstance(d, dict)]
    offices = [o.get("name", "") for o in (data.get("offices") or []) if isinstance(o, dict)]
    loc_obj = data.get("location") or {}
    loc_name = loc_obj.get("name", "") if isinstance(loc_obj, dict) else str(loc_obj)

    raw_questions = data.get("questions") or []
    parsed_questions = parse_job_questions(raw_questions)

    # Identify required fields
    required_fields = [q["field_name"] for q in parsed_questions if q.get("required")]

    result = {
        "status_code": 200,
        "id": data.get("id"),
        "board_token": token,
        "title": data.get("title"),
        "location": loc_name,
        "departments": depts,
        "offices": offices,
        "updated_at": data.get("updated_at"),
        "absolute_url": data.get("absolute_url") or f"{GREENHOUSE_HOSTED_BASE}/{token}/jobs/{jid}",
        "description_text": plain_content,
        "content_length": len(plain_content),
        "questions_count": len(parsed_questions),
        "required_fields": required_fields,
        "questions_schema": parsed_questions,
    }

    job_cache.set(cache_key, result, ttl=300)
    return result


# ===========================================================================
# 2. BOARD TAXONOMY (DEPARTMENTS, OFFICES, INFO)
# ===========================================================================

def get_board_info(board_token: str) -> Dict[str, Any]:
    """Retrieve board metadata (company name, description) for an organization."""
    token = board_token.strip().lower()
    url = f"{GREENHOUSE_API_BASE}/boards/{token}"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 404:
                return {"status_code": 404, "board_token": token, "error": f"Board '{token}' not found."}
            resp.raise_for_status()
            data = resp.json()
            return {
                "status_code": 200,
                "board_token": token,
                "name": data.get("name"),
                "content": _clean_html_text(data.get("content")),
            }
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "board_token": token,
            "error": str(e),
        }


def get_departments(board_token: str) -> Dict[str, Any]:
    """Retrieve active departments and department-job hierarchy for an organization."""
    token = board_token.strip().lower()
    url = f"{GREENHOUSE_API_BASE}/boards/{token}/departments"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 404:
                return {"status_code": 404, "board_token": token, "error": f"Board '{token}' not found."}
            resp.raise_for_status()
            data = resp.json()
            depts = data.get("departments", [])
            return {
                "status_code": 200,
                "board_token": token,
                "count": len(depts),
                "departments": depts,
            }
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "board_token": token,
            "error": str(e),
        }


def get_offices(board_token: str) -> Dict[str, Any]:
    """Retrieve office locations for an organization."""
    token = board_token.strip().lower()
    url = f"{GREENHOUSE_API_BASE}/boards/{token}/offices"
    headers = {"User-Agent": USER_AGENT, "Accept": "application/json"}

    try:
        with httpx.Client(timeout=DEFAULT_TIMEOUT, follow_redirects=True) as http_client:
            resp = http_client.get(url, headers=headers)
            if resp.status_code == 404:
                return {"status_code": 404, "board_token": token, "error": f"Board '{token}' not found."}
            resp.raise_for_status()
            data = resp.json()
            offices = data.get("offices", [])
            return {
                "status_code": 200,
                "board_token": token,
                "count": len(offices),
                "offices": offices,
            }
    except Exception as e:
        return {
            "status_code": getattr(getattr(e, "response", None), "status_code", 500),
            "board_token": token,
            "error": str(e),
        }


# ===========================================================================
# 3. APPLICATION VALIDATION & SUBMISSION
# ===========================================================================

def validate_application(
    board_token: str,
    job_id: Union[str, int],
    candidate_data: Dict[str, Any],
    answers: Optional[Dict[str, Any]] = None,
    resume_path: Optional[str] = None,
) -> Dict[str, Any]:
    """
    Validate candidate details and answers against the specific job's dynamic question schema.
    Returns completeness status, missing required fields, and auto-mapping report.
    """
    job_info = get_job_details(board_token, job_id, include_questions=True)
    if job_info.get("status_code") != 200:
        return {
            "valid": False,
            "status_code": job_info.get("status_code"),
            "error": job_info.get("error", "Unable to load job for validation"),
        }

    schema = job_info.get("questions_schema", [])
    answers_map = answers or {}
    missing_fields = []
    invalid_fields = []
    mapped_answers = {}

    for q in schema:
        fname = q["field_name"]
        label = q["label"]
        req = q["required"]
        qtype = q["type"]
        options = q.get("options", [])

        # Check standard fields
        val = None
        if fname == "first_name":
            val = candidate_data.get("first_name")
        elif fname == "last_name":
            val = candidate_data.get("last_name")
        elif fname == "email":
            val = candidate_data.get("email")
        elif fname == "phone":
            val = candidate_data.get("phone")
        elif fname in ("resume", "resume_text"):
            # Check if resume provided
            res_target = resume_path or candidate_data.get("resume_path")
            if res_target and Path(res_target).exists():
                val = res_target
            else:
                val = None
        elif fname in ("cover_letter", "cover_letter_text"):
            val = candidate_data.get("cover_letter_path") or answers_map.get(fname)
        else:
            # Custom questions (e.g. question_12345 or question_12345[])
            val = answers_map.get(fname) or answers_map.get(fname.replace("[]", ""))

        # Check missing if required
        if req and (val is None or (isinstance(val, str) and not val.strip())):
            missing_fields.append({
                "field_name": fname,
                "label": label,
                "type": qtype,
                "options": options,
            })
        else:
            if val is not None:
                # Option validation for select fields
                if options and qtype in ("single_select", "multi_select"):
                    valid_vals = [str(opt["value"]) for opt in options]
                    check_vals = [str(val)] if not isinstance(val, list) else [str(v) for v in val]
                    for cv in check_vals:
                        if cv not in valid_vals:
                            invalid_fields.append({
                                "field_name": fname,
                                "label": label,
                                "provided_value": cv,
                                "allowed_options": options,
                            })
                mapped_answers[fname] = val

    is_valid = len(missing_fields) == 0 and len(invalid_fields) == 0

    return {
        "valid": is_valid,
        "board_token": board_token,
        "job_id": str(job_id),
        "job_title": job_info.get("title"),
        "total_questions": len(schema),
        "required_questions_count": len(job_info.get("required_fields", [])),
        "missing_required_fields": missing_fields,
        "invalid_field_values": invalid_fields,
        "mapped_answers": mapped_answers,
    }


def apply_to_job(
    board_token: str,
    job_id: Union[str, int],
    candidate_data: Dict[str, Any],
    resume_path: Optional[str] = None,
    cover_letter_path: Optional[str] = None,
    answers: Optional[Dict[str, Any]] = None,
    api_key: Optional[str] = None,
    dry_run: bool = False,
) -> Dict[str, Any]:
    """
    Submit or validate an application to a Greenhouse job post.
    
    API BEHAVIOR AND AUTHENTICATION:
    1. If a Greenhouse Job Board API Key is provided (via `api_key` param or `GREENHOUSE_API_KEY` env):
       Executes `POST https://boards-api.greenhouse.io/v1/boards/{board_token}/jobs/{job_id}`
       using HTTP Basic Authentication with multipart/form-data.
    2. If NO API key is provided:
       Performs pre-flight validation against dynamic questions schema, checks resume attachment,
       generates pre-filled candidate application payload & direct hosted application link,
       and logs the tracking entry in the pipeline history.
    """
    token = board_token.strip().lower()
    jid = str(job_id).strip()

    # 1. Run pre-flight validation
    val_report = validate_application(
        board_token=token,
        job_id=jid,
        candidate_data=candidate_data,
        answers=answers,
        resume_path=resume_path,
    )

    effective_api_key = api_key or get_api_key()

    # If dry_run is requested, return validation analysis immediately
    if dry_run:
        event = {
            "type": "dry_run_validation",
            "board_token": token,
            "job_id": jid,
            "job_title": val_report.get("job_title"),
            "candidate_email": candidate_data.get("email"),
            "valid": val_report.get("valid"),
            "missing_fields": val_report.get("missing_required_fields"),
            "has_api_key": bool(effective_api_key),
        }
        record_pipeline_event(event)
        return {
            "status_code": 200,
            "mode": "dry_run",
            "validation": val_report,
            "message": "Dry run complete. Application parameters and questions schema validated.",
            "has_api_key": bool(effective_api_key),
        }

    # 2. Case A: Job Board API Key available -> Execute direct API POST
    if effective_api_key:
        post_url = f"{GREENHOUSE_API_BASE}/boards/{token}/jobs/{jid}"
        auth_bytes = f"{effective_api_key}:".encode("ascii")
        auth_header = f"Basic {base64.b64encode(auth_bytes).decode('ascii')}"

        headers = {
            "User-Agent": USER_AGENT,
            "Authorization": auth_header,
        }

        form_data = {
            "first_name": candidate_data.get("first_name", ""),
            "last_name": candidate_data.get("last_name", ""),
            "email": candidate_data.get("email", ""),
            "phone": candidate_data.get("phone", ""),
        }

        # Add custom question answers
        if answers:
            for k, v in answers.items():
                form_data[k] = v

        files = {}
        file_handles = []

        try:
            # Attach resume
            res_file = resume_path or candidate_data.get("resume_path")
            if res_file and Path(res_file).exists():
                rf = open(res_file, "rb")
                file_handles.append(rf)
                mime = mimetypes.guess_type(res_file)[0] or "application/pdf"
                files["resume"] = (Path(res_file).name, rf, mime)

            # Attach cover letter
            if cover_letter_path and Path(cover_letter_path).exists():
                cf = open(cover_letter_path, "rb")
                file_handles.append(cf)
                mime = mimetypes.guess_type(cover_letter_path)[0] or "application/pdf"
                files["cover_letter"] = (Path(cover_letter_path).name, cf, mime)

            with httpx.Client(timeout=DEFAULT_TIMEOUT * 2) as http_client:
                resp = http_client.post(post_url, data=form_data, files=files if files else None, headers=headers)
                status = resp.status_code
                body_text = resp.text

                event = {
                    "type": "api_submission",
                    "board_token": token,
                    "job_id": jid,
                    "job_title": val_report.get("job_title"),
                    "candidate_email": candidate_data.get("email"),
                    "status_code": status,
                    "success": status in (200, 201),
                }
                record_pipeline_event(event)

                if status in (200, 201):
                    return {
                        "status_code": status,
                        "success": True,
                        "board_token": token,
                        "job_id": jid,
                        "job_title": val_report.get("job_title"),
                        "message": "Candidate application successfully submitted via Greenhouse Job Board API.",
                        "response": body_text,
                    }
                else:
                    return {
                        "status_code": status,
                        "success": False,
                        "board_token": token,
                        "job_id": jid,
                        "error": f"Greenhouse Job Board API returned error {status}: {body_text}",
                        "validation_report": val_report,
                    }
        except Exception as e:
            return {
                "status_code": 500,
                "success": False,
                "board_token": token,
                "job_id": jid,
                "error": f"Exception occurred while posting application to Greenhouse: {str(e)}",
            }
        finally:
            for fh in file_handles:
                try:
                    fh.close()
                except Exception:
                    pass

    # 3. Case B: NO API Key -> Informative Diagnostic + Pre-filled Application Bundle
    direct_apply_url = f"{GREENHOUSE_HOSTED_BASE}/{token}/jobs/{jid}"
    modern_apply_url = f"{GREENHOUSE_MODERN_HOSTED_BASE}/{token}/jobs/{jid}"

    event = {
        "type": "candidate_pipeline_prepared",
        "board_token": token,
        "job_id": jid,
        "job_title": val_report.get("job_title"),
        "candidate_email": candidate_data.get("email"),
        "valid": val_report.get("valid"),
        "missing_fields": val_report.get("missing_required_fields"),
        "direct_url": direct_apply_url,
    }
    record_pipeline_event(event)

    return {
        "status_code": 401,
        "success": False,
        "requires_employer_api_key": True,
        "board_token": token,
        "job_id": jid,
        "job_title": val_report.get("job_title"),
        "validation_report": val_report,
        "explanation": (
            "Greenhouse's Job Board API (`POST /v1/boards/{board_token}/jobs/{job_id}`) requires an employer-issued "
            "Job Board API key using HTTP Basic Authentication. Public unauthenticated HTTP POST submissions to "
            "hosted boards are blocked by Signal Sciences WAF and Google reCAPTCHA Enterprise challenges."
        ),
        "resolution_instructions": [
            "1. If you possess an employer or integration Job Board API Key, set GREENHOUSE_API_KEY or call manage_session(action='set_api_key', api_key=...) to apply directly via API.",
            "2. Otherwise, use the validated candidate payload below and navigate to the direct application URL.",
        ],
        "application_urls": {
            "hosted_url": direct_apply_url,
            "modern_url": modern_apply_url,
        },
        "prefilled_candidate_payload": {
            "first_name": candidate_data.get("first_name"),
            "last_name": candidate_data.get("last_name"),
            "email": candidate_data.get("email"),
            "phone": candidate_data.get("phone"),
            "location": candidate_data.get("location"),
            "linkedin": candidate_data.get("linkedin_url"),
            "github": candidate_data.get("github_url"),
            "mapped_answers": val_report.get("mapped_answers", {}),
            "resume_path": resume_path or candidate_data.get("resume_path"),
        },
    }
