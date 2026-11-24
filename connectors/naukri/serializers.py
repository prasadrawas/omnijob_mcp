"""
Serializers and payload builders for Naukri CloudGateway mutations.
Completely decoupled from any local paths or candidate data.
"""
import re
from typing import Dict, Any, List, Optional, Union


def normalize_title(t: str) -> str:
    """Normalize project/skill title to lower alphanumeric for robust deduplication."""
    return re.sub(r"[^a-z0-9]", "", t.lower())


def build_headline_payload(headline: str, profile_id: str) -> Dict[str, Any]:
    """Build payload for updating resume headline."""
    return {
        "profile": {
            "resumeHeadline": headline.strip()
        },
        "profileId": profile_id
    }


def build_summary_payload(summary_text: str, profile_id: str) -> Dict[str, Any]:
    """Build payload for updating profile summary (max 1000 chars)."""
    clean_summary = summary_text.strip()
    if len(clean_summary) > 1000:
        clean_summary = clean_summary[:997] + "..."
    return {
        "profile": {
            "summary": clean_summary,
            "profileSummary": clean_summary
        },
        "profileId": profile_id
    }


def build_key_skills_payload(skills_csv: str, profile_id: str) -> Dict[str, Any]:
    """Build payload for updating key skills comma-separated list."""
    return {
        "profile": {
            "keySkills": skills_csv.strip()
        },
        "profileId": profile_id
    }


def build_notice_period_payload(days: int, profile_id: str) -> Dict[str, Any]:
    """Build payload for updating notice period."""
    if days == 0:
        val = "Serving Notice Period"
    elif days <= 15:
        val = "15 Days or less"
    elif days <= 30:
        val = "1 Month"
    elif days <= 60:
        val = "2 Months"
    elif days <= 90:
        val = "3 Months"
    else:
        val = "More than 3 Months"

    return {
        "profile": {
            "noticePeriod": {"id": str(days), "value": val},
            "noticePeriodDays": days
        },
        "profileId": profile_id
    }


def build_location_payload(city_id: int, city_name: str, profile_id: str) -> Dict[str, Any]:
    """Build payload for updating current candidate location."""
    return {
        "profile": {
            "city": {
                "id": city_id,
                "value": city_name,
                "subValue": ""
            }
        },
        "profileId": profile_id
    }


def build_career_profile_payload(
    expected_ctc: int,
    preferred_cities: List[Dict[str, Any]],
    target_roles: List[Dict[str, Any]],
    profile_id: str,
    desired_job_types: Optional[List[str]] = None,
    desired_employment_types: Optional[List[str]] = None,
    department: Optional[Any] = None,
    role_category: Optional[Any] = None
) -> Dict[str, Any]:
    """Build payload for updating career preferences, CTC, job types, and locations."""
    lacs_val = expected_ctc // 100000
    thousands_val = (expected_ctc % 100000) // 1000

    profile_dict: Dict[str, Any] = {
        "absoluteExpectedCtc": str(expected_ctc),
        "expectedCtcCurrency": "INR",
        "expectedCtc": {
            "lacs": {"id": lacs_val, "value": str(lacs_val)},
            "thousands": {"id": thousands_val, "value": str(thousands_val)}
        },
        "shiftPrefTime": {"id": "D", "value": "Day"},
        "desiredJobType": desired_job_types or ["permanent"],
        "desiredEmploymentType": desired_employment_types or ["Full Time"]
    }
    if department:
        if isinstance(department, dict):
            profile_dict["entityDepartment"] = {
                "id": int(department.get("id", 0)),
                "value": str(department.get("value", ""))
            }
        else:
            profile_dict["entityDepartment"] = {"id": 0, "value": str(department).strip()}

    if role_category:
        if isinstance(role_category, dict):
            profile_dict["entityRoleCategory"] = {
                "id": int(role_category.get("id", 0)),
                "value": str(role_category.get("value", ""))
            }
        else:
            profile_dict["entityRoleCategory"] = {"id": 0, "value": str(role_category).strip()}

    if preferred_cities:
        city_id_map = {"pune": 139, "bengaluru": 122, "bangalore": 122, "mumbai": 138, "hyderabad": 125, "delhi": 132, "noida": 133}
        entries = []
        for c in preferred_cities:
            if isinstance(c, dict):
                entries.append({"id": int(c.get("id", 0)), "value": str(c.get("value", ""))})
            else:
                c_str = str(c).strip()
                cid = city_id_map.get(c_str.lower(), 0)
                entries.append({"id": cid, "value": c_str})
        profile_dict["newLocationPrefId"] = entries
    if target_roles:
        first_role = target_roles[0]
        if isinstance(first_role, dict):
            role_id = int(first_role.get("id") or 265)
            role_entry = {
                "id": role_id,
                "value": str(first_role.get("value", ""))
            }
        else:
            role_entry = {
                "id": 265,
                "value": str(first_role).strip()
            }
        profile_dict["entityRole"] = role_entry
        profile_dict["desiredRole"] = [role_entry]
        profile_dict["desiredRoleTypeId"] = [role_entry]

    return {
        "profile": profile_dict,
        "profileId": profile_id
    }


def build_itskills_payload(
    skills_list: List[Dict[str, Any]],
    profile_id: str,
    existing_skill_map: Optional[Dict[str, str]] = None
) -> Dict[str, Any]:
    """Build payload for updating structured IT skills table with verified experienceTime schema."""
    existing_map = existing_skill_map or {}
    entries = []

    for s in skills_list:
        name = s.get("name") or s.get("skill") or ""
        if not name:
            continue
        norm_name = name.strip().lower()

        # Resolve experience duration
        exp_yr = s.get("exp_years")
        if exp_yr is None and isinstance(s.get("experienceTime"), dict):
            exp_yr = s["experienceTime"].get("year")
        exp_yr = int(exp_yr if exp_yr is not None else 2)

        exp_mo = s.get("exp_months")
        if exp_mo is None and isinstance(s.get("experienceTime"), dict):
            exp_mo = s["experienceTime"].get("month")
        exp_mo = int(exp_mo if exp_mo is not None else 0)

        # Resolve last used year
        last_used = s.get("last_used_year")
        if last_used is None and isinstance(s.get("lastUsed"), dict):
            last_used = s["lastUsed"].get("value")
        last_used = int(last_used if last_used is not None else 2026)

        entry: Dict[str, Any] = {
            "skill": name.strip(),
            "version": str(s.get("version", "Latest")),
            "experienceTime": {
                "year": exp_yr,
                "month": exp_mo
            },
            "lastUsed": {
                "id": last_used,
                "value": last_used
            }
        }
        sid = s.get("sid") or s.get("skillId") or existing_map.get(norm_name)
        if sid:
            entry["sid"] = str(sid)

        entries.append(entry)

    return {
        "itskills": entries,
        "profileId": profile_id
    }


def build_project_payload(
    project_data: Dict[str, Any],
    profile_id: str,
    existing_project_id: Optional[str] = None
) -> Dict[str, Any]:
    """Build payload for single project mutation."""
    client_name = project_data.get("client") or project_data.get("clientName") or project_data.get("company", "")
    title = project_data.get("name") or project_data.get("projectTitle") or project_data.get("title", "")
    desc = project_data.get("description") or project_data.get("projectDetails", "")
    if len(desc) > 990:
        desc = desc[:985] + "..."

    ts_raw = project_data.get("teamSize") or project_data.get("team_size") or 5
    ts_val = int(ts_raw.get("id") or ts_raw.get("value") or 5) if isinstance(ts_raw, dict) else int(ts_raw)
    skills = project_data.get("skills") or project_data.get("keywords", [])
    skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)

    entry: Dict[str, Any] = {
        "projectTitle": title,
        "clientName": client_name,
        "projectDetails": desc,
        "role": project_data.get("role", "Developer"),
        "teamSize": {"id": ts_val, "value": ts_val},
        "skills": skills_str,
        "startDate": project_data.get("startDate", ""),
        "endDate": project_data.get("endDate", ""),
        "employmentType": project_data.get("employmentType", "Full Time"),
        "isOnSiteProject": project_data.get("isOnSiteProject", False)
    }
    if existing_project_id or project_data.get("projectId") or project_data.get("id"):
        entry["projectId"] = str(existing_project_id or project_data.get("projectId") or project_data.get("id"))

    return {
        "projects": [entry],
        "profileId": profile_id
    }


def build_projects_payload(
    projects_list: List[Dict[str, Any]],
    profile_id: str
) -> Dict[str, Any]:
    """Build payload for multiple projects mutation."""
    entries = []
    for prj in projects_list:
        client_name = prj.get("client") or prj.get("clientName") or prj.get("company", "")
        title = prj.get("name") or prj.get("projectTitle") or prj.get("title", "")
        desc = prj.get("description") or prj.get("projectDetails", "")
        if len(desc) > 990:
            desc = desc[:985] + "..."

        ts_raw = prj.get("teamSize") or prj.get("team_size") or 5
        ts_val = int(ts_raw.get("id") or ts_raw.get("value") or 5) if isinstance(ts_raw, dict) else int(ts_raw)
        skills = prj.get("skills") or prj.get("keywords", [])
        skills_str = ", ".join(skills) if isinstance(skills, list) else str(skills)

        entry: Dict[str, Any] = {
            "projectTitle": title,
            "clientName": client_name,
            "projectDetails": desc,
            "role": prj.get("role", "Developer"),
            "teamSize": {"id": ts_val, "value": ts_val},
            "skills": skills_str,
            "startDate": prj.get("startDate", ""),
            "endDate": prj.get("endDate", ""),
            "employmentType": prj.get("employmentType", "Full Time"),
            "isOnSiteProject": prj.get("isOnSiteProject", False)
        }
        if prj.get("projectId") or prj.get("id"):
            entry["projectId"] = str(prj.get("projectId") or prj.get("id"))
        entries.append(entry)

    return {
        "projects": entries,
        "profileId": profile_id
    }


def build_employment_payload(
    work_list: List[Dict[str, Any]],
    profile_id: str
) -> Dict[str, Any]:
    """Build payload for updating employment / work experience history."""
    from datetime import datetime
    today_str = datetime.now().strftime("%Y-%m-%d")
    employments = []

    for w in work_list:
        is_current = bool(w.get("isCurrent", False) or w.get("endDate") is None)
        start_date = w.get("startDate", "")
        end_date = "" if is_current else (w.get("endDate") or "")

        summary_pts = w.get("highlights", [])
        if isinstance(summary_pts, list):
            job_desc = " ".join(summary_pts)
        else:
            job_desc = str(summary_pts)
        if len(job_desc) > 950:
            job_desc = job_desc[:945] + "..."

        techs = w.get("technologies") or w.get("skills", [])
        top_skills = ", ".join(techs[:5]) if isinstance(techs, list) else str(techs)

        emp_type = "current" if is_current else "previous"
        emp_entry: Dict[str, Any] = {
            "organization": w.get("company", ""),
            "designation": w.get("position", "") or w.get("role", "Software Engineer"),
            "startDate": start_date,
            "endDate": end_date,
            "employmentType": emp_type,
            "jobDescription": job_desc,
            "keySkills": top_skills
        }
        if w.get("employmentId"):
            emp_entry["employmentId"] = str(w["employmentId"])
        if is_current:
            emp_entry["noticePeriod"] = {"id": "30", "value": "1 Month"}
            if w.get("annualSalary"):
                emp_entry["salary"] = str(w.get("annualSalary"))
        employments.append(emp_entry)

    return {
        "employments": employments,
        "profileId": profile_id
    }


def build_application_payload(
    job_id: str,
    profile_id: str,
    answers: Optional[List[Dict[str, Any]]] = None
) -> Dict[str, Any]:
    """Build payload for submitting job application with questionnaire answers."""
    apply_details: Dict[str, Any] = {
        "jobId": job_id,
        "profileId": profile_id,
        "source": "109"
    }
    if answers:
        formatted_answers = []
        for ans in answers:
            if isinstance(ans, dict):
                formatted_answers.append({
                    "questionId": str(ans.get("questionId") or ans.get("id") or ans.get("question", "")),
                    "answer": str(ans.get("answer") or ans.get("value", ""))
                })
        apply_details["questionnaire"] = formatted_answers

    return {"applyDetails": apply_details}


def build_online_profiles_payload(profiles_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for online profiles (e.g. LinkedIn, GitHub, Portfolio)."""
    entries = []
    for p in profiles_list:
        profile_name = p.get("profile") or p.get("network") or p.get("name") or "LinkedIn"
        url = p.get("url") or ""
        if url:
            entry: Dict[str, Any] = {"profile": str(profile_name)[:150], "url": str(url)[:500]}
            if p.get("id"):
                entry["id"] = str(p["id"])
            entries.append(entry)
    return {"onlineProfiles": entries, "profileId": profile_id}


def build_work_samples_payload(samples_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for work samples (e.g. GitHub repos, Behance)."""
    entries = []
    for s in samples_list:
        title = s.get("title") or s.get("name") or ""
        url = s.get("url") or ""
        if title and url:
            entry: Dict[str, Any] = {"title": str(title)[:150], "url": str(url)[:500]}
            if s.get("id"):
                entry["id"] = str(s["id"])
            entries.append(entry)
    return {"workSamples": entries, "profileId": profile_id}


def build_publications_payload(publications_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for research publications, white papers, or journal entries."""
    entries = []
    for pub in publications_list:
        title = pub.get("title") or pub.get("name") or ""
        url = pub.get("url") or ""
        if title and url:
            entry: Dict[str, Any] = {"title": str(title)[:150], "url": str(url)[:500]}
            if pub.get("id"):
                entry["id"] = str(pub["id"])
            entries.append(entry)
    return {"publications": entries, "profileId": profile_id}


def build_presentations_payload(presentations_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for online presentations (e.g. SlideShare, SpeakerDeck)."""
    entries = []
    for pres in presentations_list:
        title = pres.get("title") or pres.get("name") or ""
        url = pres.get("url") or ""
        if title and url:
            entry: Dict[str, Any] = {"title": str(title)[:150], "url": str(url)[:500]}
            if pres.get("id"):
                entry["id"] = str(pres["id"])
            entries.append(entry)
    return {"presentations": entries, "profileId": profile_id}


def build_patents_payload(patents_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for patents filed or issued."""
    entries = []
    for pat in patents_list:
        title = pat.get("title") or pat.get("name") or ""
        url = pat.get("url") or ""
        if title and url:
            entry: Dict[str, Any] = {"title": str(title)[:150], "url": str(url)[:500]}
            if pat.get("id"):
                entry["id"] = str(pat["id"])
            entries.append(entry)
    return {"patents": entries, "profileId": profile_id}


def build_certifications_payload(certifications_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """Build payload for certifications."""
    entries = []
    for cert in certifications_list:
        course = cert.get("course") or cert.get("name") or cert.get("title") or ""
        vendor = cert.get("vendor") or cert.get("issuer") or cert.get("body") or "Official Provider"
        if course:
            entry: Dict[str, Any] = {
                "course": str(course),
                "vendor": str(vendor)
            }
            yr = cert.get("validTillYear") or cert.get("year")
            if yr is not None:
                entry["validTillYear"] = int(yr)
            mo = cert.get("validTillMonth") or cert.get("month")
            if mo is not None:
                entry["validTillMonth"] = int(mo)
            if cert.get("id") or cert.get("certificationId"):
                entry["certificationId"] = str(cert.get("id") or cert.get("certificationId"))
            entries.append(entry)
    return {"certifications": entries, "profileId": profile_id}


def build_educations_payload(educations_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """
    Build payload for higher educations (Doctorate, Masters, Graduation).
    Matches Naukri CloudGateway schema.
    """
    entries = []
    for edu in educations_list:
        ed_type = edu.get("educationType") or {}
        if isinstance(ed_type, str):
            val = ed_type.upper()
            ed_type_obj = {"id": "1" if "UG" in val or "GRAD" in val else "2" if "PG" in val or "MASTER" in val else "3", "value": val}
        else:
            ed_type_obj = {
                "id": str(ed_type.get("id", "1")),
                "value": str(ed_type.get("value", "UG"))
            }

        course_obj = edu.get("course") or {}
        if isinstance(course_obj, str):
            course_dict = {"id": 0, "value": course_obj, "subValue": ""}
        else:
            course_dict = {
                "id": int(course_obj.get("id") or 0),
                "value": str(course_obj.get("value", "")),
                "subValue": str(course_obj.get("subValue", ""))
            }

        spec_obj = edu.get("specialisation") or edu.get("specialization") or {}
        if isinstance(spec_obj, str):
            spec_dict = {"id": 0, "value": spec_obj, "subValue": ""}
        else:
            spec_dict = {
                "id": int(spec_obj.get("id") or 0),
                "value": str(spec_obj.get("value", "")),
                "subValue": str(spec_obj.get("subValue", ""))
            }

        inst_obj = edu.get("entityInstitute") or edu.get("institute") or {}
        if isinstance(inst_obj, str):
            inst_dict = {"id": "0", "value": inst_obj}
        else:
            inst_dict = {
                "id": str(inst_obj.get("id") or "0"),
                "value": str(inst_obj.get("value", ""))
            }

        course_type_raw = edu.get("courseType", "F")
        if isinstance(course_type_raw, dict):
            course_type_letter = "F" if "full" in str(course_type_raw.get("value", "")).lower() else "P"
        else:
            course_type_letter = "F" if "full" in str(course_type_raw).lower() or str(course_type_raw) == "F" else "P"

        entry: Dict[str, Any] = {
            "educationType": ed_type_obj,
            "course": course_dict,
            "specialisation": spec_dict,
            "entityInstitute": inst_dict,
            "courseType": course_type_letter,
            "yearOfStart": int(edu.get("yearOfStart") or 0),
            "yearOfCompletion": int(edu.get("yearOfCompletion") or edu.get("passingYear") or 0)
        }
        if edu.get("educationId") or edu.get("id"):
            entry["educationId"] = str(edu.get("educationId") or edu.get("id"))
        entries.append(entry)

    return {"educations": entries, "profileId": profile_id}


def build_schools_payload(schools_list: List[Dict[str, Any]], profile_id: str) -> Dict[str, Any]:
    """
    Build payload for school educations (Class X, Class XII).
    """
    entries = []
    for sch in schools_list:
        ed_type = sch.get("educationType") or {}
        if isinstance(ed_type, str):
            val = "Class XII" if "12" in ed_type or "xii" in ed_type.lower() else "Class X"
            lvl = 2 if "12" in ed_type or "xii" in ed_type.lower() else 1
            ed_type_obj = {"id": "12" if lvl == 2 else "10", "value": val}
        else:
            lvl = int(sch.get("schoolLevel") or (2 if "12" in str(ed_type.get("id", "")) else 1))
            ed_type_obj = {
                "id": str(ed_type.get("id", "12" if lvl == 2 else "10")),
                "value": str(ed_type.get("value", "Class XII" if lvl == 2 else "Class X"))
            }

        board = sch.get("schoolBoard") or {}
        if isinstance(board, str):
            board_obj = {"id": 1, "value": board}
        else:
            board_obj = {"id": int(board.get("id", 1)), "value": str(board.get("value", "CBSE"))}

        medium = sch.get("schoolMedium") or {}
        if isinstance(medium, str):
            med_obj = {"id": 3, "value": medium}
        else:
            med_obj = {"id": int(medium.get("id", 3)), "value": str(medium.get("value", "English"))}

        pct = sch.get("schoolPercentage") or {}
        if isinstance(pct, str):
            pct_obj = {"id": 1, "value": pct}
        else:
            pct_obj = {"id": int(pct.get("id", 1)), "value": str(pct.get("value", "80-84.9%"))}

        entry: Dict[str, Any] = {
            "educationType": ed_type_obj,
            "schoolBoard": board_obj,
            "schoolCompletionYear": int(sch.get("schoolCompletionYear") or sch.get("passingYear") or 0),
            "schoolMedium": med_obj,
            "schoolPercentage": pct_obj,
            "schoolLevel": lvl
        }
        if sch.get("schoolId") or sch.get("id"):
            entry["schoolId"] = str(sch.get("schoolId") or sch.get("id"))
        entries.append(entry)

    return {"schools": entries, "profileId": profile_id}


def build_personal_details_payload(
    profile_id: str,
    gender: Optional[str] = None,
    marital_status: Optional[str] = None,
    birth_date: Optional[str] = None,
    category: Optional[str] = None,
    address: Optional[str] = None,
    hometown: Optional[str] = None,
    pincode: Optional[str] = None,
    mail_city: Optional[str] = None
) -> Dict[str, Any]:
    """Build payload for updating personal details (gender, marital status, DOB, address, etc)."""
    prof: Dict[str, Any] = {}
    if gender:
        g = gender.strip().upper()
        prof["gender"] = "M" if g in ("M", "MALE") else ("F" if g in ("F", "FEMALE") else ("T" if g in ("T", "TRANSGENDER") else g))
    if marital_status:
        ms = marital_status.strip().title()
        ms_id = "M" if "Married" in ms and "Unmarried" not in ms else "N"
        ms_val = "Married" if ms_id == "M" else "Single / unmarried"
        prof["maritalStatus"] = {"id": ms_id, "value": ms_val}
    if birth_date:
        prof["birthDate"] = birth_date.strip()
    if category:
        cat = category.strip()
        prof["category"] = {"id": 1, "value": cat}
    if address:
        prof["contactAddress"] = address.strip()
    if hometown:
        prof["hometown"] = hometown.strip()
    if pincode:
        prof["pincode"] = pincode.strip()
    if mail_city:
        prof["mailCity"] = mail_city.strip()

    return {"profile": prof, "profileId": profile_id}


def build_languages_payload(
    languages_list: List[Dict[str, Any]],
    profile_id: str
) -> Dict[str, Any]:
    """Build payload for updating candidate languages with proficiency and abilities."""
    entries = []
    for lang_item in languages_list:
        lang_name = str(lang_item.get("lang") or lang_item.get("language") or "").strip()
        if not lang_name:
            continue
        prof_raw = lang_item.get("proficiency", 2)
        if isinstance(prof_raw, dict):
            prof_obj = prof_raw
        elif isinstance(prof_raw, int):
            prof_val = "Expert" if prof_raw == 3 else ("Proficient" if prof_raw == 2 else "Beginner")
            prof_obj = {"id": prof_raw, "value": prof_val}
        else:
            p_str = str(prof_raw).strip().title()
            p_id = 3 if "Expert" in p_str else (1 if "Beginner" in p_str else 2)
            prof_obj = {"id": p_id, "value": p_str if p_str in ("Beginner", "Proficient", "Expert") else "Proficient"}

        abilities = lang_item.get("ability") or []
        if not abilities:
            abilities = []
            if lang_item.get("read", True):
                abilities.append("read")
            if lang_item.get("write", True):
                abilities.append("write")
            if lang_item.get("speak", True):
                abilities.append("speak")

        entry: Dict[str, Any] = {
            "lang": lang_name,
            "proficiency": prof_obj,
            "ability": abilities
        }
        if lang_item.get("languageId") or lang_item.get("id"):
            entry["languageId"] = str(lang_item.get("languageId") or lang_item.get("id"))
        entries.append(entry)

    return {"languages": entries, "profileId": profile_id}


def build_job_search_status_payload(
    status_code_or_name: Any,
    profile_id: str
) -> Dict[str, Any]:
    """Build payload for updating job search status (Active, Casual, Not looking)."""
    status_str = str(status_code_or_name).strip().lower()
    if status_str in ("1", "actively", "actively searching jobs", "active"):
        s_id, s_val = 1, "Actively searching jobs"
    elif status_str in ("2", "casual", "casual job seeker", "casually exploring"):
        s_id, s_val = 2, "Casual job seeker"
    else:
        s_id, s_val = 3, "Not looking for jobs"

    return {
        "extendedProfile": {
            "jbSearchStatus": {
                "data": [
                    {"id": s_id, "value": s_val}
                ]
            }
        },
        "profileId": profile_id
    }


def build_disability_payload(
    is_disabled: bool,
    profile_id: str,
    disability_type: Optional[str] = None,
    percentage: Optional[int] = None,
    details: Optional[str] = None
) -> Dict[str, Any]:
    """Build payload for updating differently abled / disability profile."""
    disability_flag = "A" if is_disabled else "B"
    payload: Dict[str, Any] = {
        "profile": {
            "disability": {
                "isDisabled": disability_flag
            }
        },
        "profileId": profile_id
    }
    if is_disabled and (disability_type or percentage or details):
        payload["disability"] = [{
            "disabilityType": disability_type or "Physical",
            "disabilityPercent": percentage or 40,
            "disabilityReason": details or ""
        }]
    return payload


def build_work_permit_payload(
    profile_id: str,
    us_work_status: Optional[Any] = None,
    countries: Optional[List[Any]] = None
) -> Dict[str, Any]:
    """Build payload for updating US work authorization and international work permits."""
    prof_update: Dict[str, Any] = {}
    if us_work_status is not None:
        if isinstance(us_work_status, dict):
            prof_update["workStatus"] = us_work_status
        else:
            ws_str = str(us_work_status).strip().lower()
            if "citizen" in ws_str or ws_str == "1":
                prof_update["workStatus"] = {"id": 1, "value": "US Citizen"}
            elif "green" in ws_str or "resident" in ws_str or ws_str == "2":
                prof_update["workStatus"] = {"id": 2, "value": "Permanent Resident/Green Card"}
            elif (("have" in ws_str or "h1" in ws_str) and "need" not in ws_str) or ws_str == "3":
                prof_update["workStatus"] = {"id": 3, "value": "Have H1 Visa"}
            elif "need" in ws_str or ws_str == "4":
                prof_update["workStatus"] = {"id": 4, "value": "Need H1 Visa"}
            else:
                prof_update["workStatus"] = {"id": 1, "value": str(us_work_status)}

    if countries is not None:
        country_entries: List[Union[Dict[str, Any], int, str]] = []
        country_id_map = {
            "australia": 9001,
            "bahrain": 9002,
            "bangladesh": 9003,
            "belgium": 9004,
            "canada": 9005,
            "germany": 9015,
            "singapore": 9037,
            "uae": 9042,
            "united kingdom": 9043,
            "uk": 9043,
            "united states": 9044,
            "usa": 9044
        }
        for c in countries:
            if isinstance(c, dict) and c.get("id"):
                country_entries.append({"id": int(c["id"]), "value": str(c.get("value", ""))})
            elif isinstance(c, int):
                country_entries.append(c)
            elif isinstance(c, str):
                c_clean = c.strip().lower()
                cid = country_id_map.get(c_clean)
                if cid:
                    country_entries.append({"id": cid, "value": c.strip()})
                else:
                    country_entries.append(c.strip())
        prof_update["workStatusOtherId"] = country_entries

    return {
        "profile": prof_update,
        "profileId": profile_id
    }


def build_career_break_payload(
    profile_id: str,
    has_break: bool = True,
    reason: Optional[str] = None,
    start_date: Optional[str] = None,
    end_date: Optional[str] = None
) -> Dict[str, Any]:
    """Build payload for updating career break status and dates."""
    if not has_break:
        return {
            "extendedProfile": {
                "careerBreak": {
                    "data": [{
                        "comingFromBreak": False
                    }]
                }
            },
            "profileId": profile_id
        }

    reason_map = {
        "child care": 1,
        "education": 2,
        "health": 3,
        "layoff": 4,
        "personal": 5
    }
    r_clean = (reason or "personal").strip().lower()
    rid = reason_map.get(r_clean, 5)
    r_val = reason.strip().title() if reason else "Personal"

    s_dt = start_date.strip() if start_date else ""
    if len(s_dt) == 7:
        s_dt += "-01"
    e_dt = end_date.strip() if end_date else ""
    if len(e_dt) == 7:
        e_dt += "-01"

    return {
        "extendedProfile": {
            "careerBreak": {
                "data": [{
                    "comingFromBreak": True,
                    "reasonOfBreak": {"id": rid, "value": r_val},
                    "breakDuration": {"from": s_dt, "to": e_dt}
                }]
            }
        },
        "profileId": profile_id
    }
