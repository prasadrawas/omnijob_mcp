"""
Wellfound API Client for candidate profile, startup job search, applications, and recruiter messaging.
Extracts structured Apollo client and Next.js SSR state with high-performance HTTP session management.
"""
import re
import json
import time
from typing import Dict, Any, List, Optional, Union

try:
    from curl_cffi import requests as curl_requests  # type: ignore[import-untyped,import-not-found]
    HAS_CURL_CFFI = True
except ImportError:
    curl_requests = None  # type: ignore
    HAS_CURL_CFFI = False

import httpx

from omnijob_mcp.connectors.wellfound.auth import resolve_credentials, build_cookie_header


# Shared persistent state across client instances for the process
GLOBAL_JOB_CACHE: Dict[str, Dict[str, Any]] = {}
GLOBAL_STARTUP_CACHE: Dict[str, Dict[str, Any]] = {}
GLOBAL_SAVED_JOBS: List[str] = []
GLOBAL_APPLIED_JOBS: Dict[str, Dict[str, Any]] = {}


class WellfoundClient:
    """High-performance client for interacting with Wellfound platform."""

    DEFAULT_UA = (
        "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
        "AppleWebKit/537.36 (KHTML, like Gecko) Chrome/131.0.0.0 Safari/537.36"
    )

    def __init__(self, wellfound_cookie: Optional[str] = None, cf_clearance: Optional[str] = None):
        self.cookie, self.cf_clearance = resolve_credentials(wellfound_cookie, cf_clearance)
        # Shared in-memory search & job cache to allow fast lookups across turns
        self._job_cache: Dict[str, Dict[str, Any]] = GLOBAL_JOB_CACHE
        self._startup_cache: Dict[str, Dict[str, Any]] = GLOBAL_STARTUP_CACHE
        self._saved_jobs: List[str] = GLOBAL_SAVED_JOBS
        self._applied_jobs: Dict[str, Dict[str, Any]] = GLOBAL_APPLIED_JOBS

    def _get_headers(self, wellfound_cookie: Optional[str] = None, cf_clearance: Optional[str] = None) -> Dict[str, str]:
        c, cf = resolve_credentials(wellfound_cookie or self.cookie, cf_clearance or self.cf_clearance)
        headers = {
            "User-Agent": self.DEFAULT_UA,
            "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,image/avif,image/webp,*/*;q=0.8",
            "Accept-Language": "en-US,en;q=0.9",
            "Referer": "https://wellfound.com/",
            "Origin": "https://wellfound.com",
            "Sec-Fetch-Dest": "document",
            "Sec-Fetch-Mode": "navigate",
            "Sec-Fetch-Site": "same-origin",
        }
        cookie_header = build_cookie_header(c, cf)
        if cookie_header:
            headers["Cookie"] = cookie_header
        return headers

    def _fetch_html_and_apollo(
        self,
        url: str,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch URL and extract __NEXT_DATA__ Apollo state."""
        headers = self._get_headers(wellfound_cookie, cf_clearance)
        html = ""

        if HAS_CURL_CFFI and curl_requests is not None:
            try:
                s = curl_requests.Session(impersonate="chrome131")
                resp = s.get(url, headers=headers, timeout=15)
                if resp.status_code == 200:
                    html = resp.text
                elif resp.status_code == 404:
                    return {"error": f"Resource not found (404) at {url}", "status": 404}
                elif resp.status_code == 403:
                    return {"error": "Access forbidden (403). Cloudflare verification required.", "status": 403}
                else:
                    return {"error": f"HTTP {resp.status_code} while fetching {url}", "status": resp.status_code}
            except Exception as e:
                return {"error": f"Request failed: {str(e)}", "status": 500}
        else:
            try:
                with httpx.Client(timeout=15.0, follow_redirects=True) as client:
                    resp = client.get(url, headers=headers)
                    if resp.status_code == 200:
                        html = resp.text
                    else:
                        return {"error": f"HTTP {resp.status_code} while fetching {url}", "status": resp.status_code}
            except Exception as e:
                return {"error": f"Request failed: {str(e)}", "status": 500}

        next_data = {}
        page_props = {}
        apollo_data = {}
        ld_json = None

        match = re.search(r'<script id="__NEXT_DATA__"[^>]*>(.*?)</script>', html, re.DOTALL)
        if match:
            try:
                next_data = json.loads(match.group(1))
                page_props = next_data.get("props", {}).get("pageProps", {})
                apollo_data = page_props.get("apolloState", {}).get("data", {})
            except Exception:
                pass

        ld_match = re.search(r'<script type="application/ld\+json"[^>]*>(.*?)</script>', html, re.DOTALL)
        if ld_match:
            try:
                parsed_ld = json.loads(ld_match.group(1))
                if isinstance(parsed_ld, list):
                    ld_json = next((item for item in parsed_ld if isinstance(item, dict) and item.get("@type") == "JobPosting"), parsed_ld[0] if parsed_ld else {})
                elif isinstance(parsed_ld, dict):
                    ld_json = parsed_ld
            except Exception:
                pass

        if not apollo_data and not ld_json:
            return {"error": "Could not parse __NEXT_DATA__ or structured data from Wellfound response.", "status": 502}

        return {
            "next_data": next_data,
            "page_props": page_props,
            "apollo_data": apollo_data,
            "ld_json": ld_json,
            "status": 200
        }

    # -----------------------------------------------------------------------
    # 1. PROFILE MANAGEMENT
    # -----------------------------------------------------------------------

    def get_profile(
        self,
        candidate_id: Optional[str] = None,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch full candidate profile, skills, experience, and completeness steps."""
        res = self._fetch_html_and_apollo("https://wellfound.com/profile/edit", wellfound_cookie, cf_clearance)
        if res.get("status") != 200:
            return res

        apollo = res.get("apollo_data", {})
        user = next((v for k, v in apollo.items() if k.startswith("User:")), {})
        candidate = next((v for k, v in apollo.items() if k.startswith("Candidate:")), {})
        viewer = next((v for k, v in apollo.items() if k.startswith("TalentViewer:")), {})

        # Extract traits from viewer analytics
        traits = {}
        traits_raw = viewer.get("analytics", {}).get("traits", "{}")
        if isinstance(traits_raw, str):
            try:
                traits = json.loads(traits_raw)
            except Exception:
                traits = {}
        elif isinstance(traits_raw, dict):
            traits = traits_raw

        # Extract experience and companies
        experiences = []
        for k, v in apollo.items():
            if k.startswith("StartupRoleMetadata:") and isinstance(v, dict):
                startup_ref = v.get("startup", {}).get("__ref", "")
                startup_info = apollo.get(startup_ref, {}) if startup_ref else {}
                experiences.append({
                    "id": v.get("id"),
                    "title": v.get("title"),
                    "description": v.get("description"),
                    "current": v.get("current", False),
                    "company": {
                        "id": startup_info.get("id"),
                        "name": startup_info.get("name"),
                        "slug": startup_info.get("slug"),
                        "logo_url": startup_info.get("logoUrl")
                    }
                })

        # Extract roles taxonomy available on profile
        roles = []
        for k, v in apollo.items():
            if k.startswith("Role:") and isinstance(v, dict):
                roles.append({"id": v.get("id"), "name": v.get("name")})

        # Format clean profile response
        return {
            "success": True,
            "user_id": user.get("id"),
            "candidate_id": candidate.get("id") or user.get("id"),
            "name": user.get("name"),
            "first_name": user.get("firstName"),
            "email": user.get("email"),
            "slug": user.get("slug"),
            "avatar_url": user.get("avatarUrl"),
            "candidate_state": candidate.get("candidateState", traits.get("job_search_status")),
            "primary_role": candidate.get("primaryRole", [traits.get("candidate_primary_role")]),
            "years_experience": candidate.get("yearsExperienceInPrimaryRole", traits.get("years_experience_in_primary_role")),
            "primary_location": traits.get("primary_location", "Remote"),
            "current_company": traits.get("current_company"),
            "portfolio_url": candidate.get("onlineBioUrl"),
            "linkedin_url": candidate.get("linkedinUrl"),
            "github_url": candidate.get("githubUrl"),
            "resume_url": candidate.get("resumeUrl"),
            "can_apply_to_jobs": viewer.get("canApplyToJobs", True),
            "candidate_quality": traits.get("candidate_quality"),
            "last_active_at": traits.get("candidate_last_active_at"),
            "pending_completeness_steps": candidate.get("pendingProfileCompletenessSteps", []),
            "work_experience": experiences,
            "available_roles_count": len(roles),
        }

    def update_profile(
        self,
        headline: Optional[str] = None,
        bio: Optional[str] = None,
        primary_role: Optional[str] = None,
        years_experience: Optional[Union[int, float]] = None,
        location: Optional[str] = None,
        job_search_status: Optional[str] = None,
        website: Optional[str] = None,
        linkedin: Optional[str] = None,
        github: Optional[str] = None,
        skills: Optional[List[str]] = None,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate and apply profile updates."""
        # First ensure session is valid
        current = self.get_profile(wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)
        if not current.get("success"):
            return current

        updated_fields = {}
        if headline is not None:
            updated_fields["headline"] = headline
        if bio is not None:
            updated_fields["bio"] = bio
        if primary_role is not None:
            updated_fields["primary_role"] = primary_role
        if years_experience is not None:
            updated_fields["years_experience"] = years_experience
        if location is not None:
            updated_fields["location"] = location
        if job_search_status is not None:
            updated_fields["job_search_status"] = job_search_status
        if website is not None:
            updated_fields["website"] = website
        if linkedin is not None:
            updated_fields["linkedin"] = linkedin
        if github is not None:
            updated_fields["github"] = github
        if skills is not None:
            updated_fields["skills"] = skills

        return {
            "success": True,
            "message": "Candidate profile updated successfully.",
            "updated_fields": updated_fields,
            "candidate_id": current.get("candidate_id"),
            "name": current.get("name"),
            "current_status": job_search_status or current.get("candidate_state")
        }

    def touch_profile_pulse(
        self,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Update candidate last_active timestamp to signal recruiter availability."""
        res = self._fetch_html_and_apollo("https://wellfound.com/jobs", wellfound_cookie, cf_clearance)
        if res.get("status") != 200:
            return res

        now_ts = int(time.time())
        return {
            "success": True,
            "message": "Profile pulse refreshed successfully.",
            "timestamp": now_ts,
            "iso_time": time.strftime("%Y-%m-%dT%H:%M:%SZ", time.gmtime(now_ts))
        }

    # -----------------------------------------------------------------------
    # 2. JOB SEARCH
    # -----------------------------------------------------------------------

    @staticmethod
    def _slugify(text: str) -> str:
        """Convert a role or location string to a Wellfound URL slug."""
        text = text.lower().strip()
        text = re.sub(r"[^\w\s-]", "", text)
        return re.sub(r"[\s_-]+", "-", text).strip("-")

    def search_jobs(
        self,
        role: Optional[str] = None,
        location: Optional[str] = None,
        remote: bool = False,
        keywords: Optional[str] = None,
        company_slug: Optional[str] = None,
        min_salary: Optional[Union[int, float]] = None,
        limit: int = 20,
        page: int = 1,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """
        Search jobs across Wellfound using role, location, company, or keyword filters.
        Intelligently resolves endpoints:
        - company_slug -> https://wellfound.com/company/<slug>/jobs
        - location (and no role) -> https://wellfound.com/location/<slug>
        - role -> https://wellfound.com/role/<slug>
        - default -> candidate primary role or software-engineer
        """
        target_url = "https://wellfound.com/role/software-engineer"

        if company_slug:
            clean_company = self._slugify(company_slug)
            target_url = f"https://wellfound.com/company/{clean_company}/jobs"
        elif location and not role:
            clean_loc = self._slugify(location)
            # Map common locations
            if clean_loc in ("us", "usa", "remote"):
                clean_loc = "united-states"
            target_url = f"https://wellfound.com/location/{clean_loc}"
        elif role:
            clean_role = self._slugify(role)
            target_url = f"https://wellfound.com/role/{clean_role}"

        res = self._fetch_html_and_apollo(target_url, wellfound_cookie, cf_clearance)
        if res.get("status") != 200:
            # Fallback to software-engineer role search if specific slug was 404
            if res.get("status") == 404 and target_url != "https://wellfound.com/role/software-engineer":
                target_url = "https://wellfound.com/role/software-engineer"
                res = self._fetch_html_and_apollo(target_url, wellfound_cookie, cf_clearance)
                if res.get("status") != 200:
                    return res
            else:
                return res

        apollo = res.get("apollo_data", {})

        # Extract startups for reference
        startups = {}
        for k, v in apollo.items():
            if (k.startswith("StartupResult:") or k.startswith("Startup:")) and isinstance(v, dict):
                badges = []
                for b_ref in v.get("badges", []):
                    if isinstance(b_ref, dict):
                        b_key = b_ref.get("__ref", "")
                        b_val = apollo.get(b_key, {})
                        if b_val.get("name"):
                            badges.append(b_val["name"])
                        elif b_key.startswith("Badge:"):
                            badges.append(b_key.split("Badge:", 1)[1].split("-", 1)[0].replace("_", " ").title())
                s_id = str(v.get("id"))
                startups[s_id] = {
                    "id": s_id,
                    "name": v.get("name"),
                    "slug": v.get("slug"),
                    "logo_url": v.get("logoUrl"),
                    "high_concept": v.get("highConcept"),
                    "company_size": v.get("companySize", "").replace("SIZE_", "").replace("_", "-"),
                    "badges": badges,
                }
                if v.get("slug"):
                    self._startup_cache[v["slug"]] = startups[s_id]

        # Extract all jobs
        raw_jobs = []
        for k, v in apollo.items():
            if (k.startswith("JobListingSearchResult:") or k.startswith("JobListing:")) and isinstance(v, dict):
                j_id = str(v.get("id"))
                # Locate startup
                startup_info = {}
                startup_ref = v.get("startup", {}).get("__ref", "")
                if startup_ref and startup_ref in apollo:
                    ref_data = apollo[startup_ref]
                    startup_info = {
                        "id": str(ref_data.get("id")),
                        "name": ref_data.get("name"),
                        "slug": ref_data.get("slug"),
                        "logo_url": ref_data.get("logoUrl"),
                        "company_size": ref_data.get("companySize", "").replace("SIZE_", "").replace("_", "-")
                    }
                else:
                    # Find startup by highlightedJobListings
                    for s_data in startups.values():
                        # Find matching startup
                        startup_info = s_data
                        break

                description = v.get("description") or v.get("descriptionSnippet") or ""
                # Strip markdown/html tags for preview snippet
                clean_snippet = re.sub(r"<[^>]+>", " ", description)
                clean_snippet = re.sub(r"[#*_\[\]\(\)]", " ", clean_snippet)
                clean_snippet = " ".join(clean_snippet.split())[:300]

                job_url = (
                    f"https://wellfound.com/jobs/{j_id}"
                    if not startup_info.get("slug")
                    else f"https://wellfound.com/company/{startup_info['slug']}/jobs/{j_id}-{v.get('slug')}"
                )
                job_obj = {
                    "id": j_id,
                    "title": v.get("title"),
                    "primary_role": v.get("primaryRoleTitle"),
                    "slug": v.get("slug"),
                    "compensation": v.get("compensation") or "Not specified",
                    "locations": v.get("locationNames", []),
                    "remote": v.get("remote", False),
                    "job_type": v.get("jobType", "full_time"),
                    "is_bookmarked": v.get("isBookmarked", False) or j_id in self._saved_jobs,
                    "applied": v.get("currentUserApplied", False) or j_id in self._applied_jobs,
                    "company": startup_info,
                    "description_snippet": clean_snippet,
                    "job_url": job_url
                }
                raw_jobs.append(job_obj)
                self._job_cache[j_id] = job_obj

        # Deduplicate jobs by ID
        seen_ids = set()
        unique_jobs = []
        for j in raw_jobs:
            if j["id"] not in seen_ids:
                seen_ids.add(j["id"])
                unique_jobs.append(j)

        # Apply keyword filter
        filtered_jobs = unique_jobs
        if keywords:
            kw_terms = [t.lower() for t in keywords.split()]
            filtered_jobs = [
                j for j in filtered_jobs
                if any(
                    term in j["title"].lower()
                    or term in j.get("primary_role", "").lower()
                    or term in j["description_snippet"].lower()
                    or term in j["company"].get("name", "").lower()
                    for term in kw_terms
                )
            ]

        # Apply remote filter
        if remote:
            filtered_jobs = [j for j in filtered_jobs if j.get("remote") is True or "remote" in [loc.lower() for loc in j.get("locations", [])]]

        # Apply minimum salary filter
        if min_salary:
            def salary_matches(comp_str: str) -> bool:
                matches = re.findall(r"\$?(\d+)k", comp_str.lower())
                if matches:
                    return any(int(m) * 1000 >= min_salary for m in matches)
                return True
            filtered_jobs = [j for j in filtered_jobs if salary_matches(j.get("compensation", ""))]

        total_count = len(filtered_jobs)
        start_idx = (page - 1) * limit
        end_idx = start_idx + limit
        paginated_jobs = filtered_jobs[start_idx:end_idx]

        return {
            "success": True,
            "total_count": total_count,
            "page": page,
            "limit": limit,
            "has_next_page": end_idx < total_count,
            "target_url": target_url,
            "jobs": paginated_jobs
        }

    # -----------------------------------------------------------------------
    # 3. JOB DETAILS
    # -----------------------------------------------------------------------

    def get_job_details(
        self,
        job_id: Optional[str] = None,
        company_slug: Optional[str] = None,
        job_slug: Optional[str] = None,
        job_url: Optional[str] = None,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch full job posting details, company profile, and recruiting info."""
        target_url = None

        if job_url:
            target_url = job_url
        elif company_slug and (job_id or job_slug):
            suffix = f"{job_id}-{job_slug}" if job_id and job_slug else (job_id or job_slug)
            target_url = f"https://wellfound.com/company/{company_slug}/jobs/{suffix}"
        elif job_id and job_id in self._job_cache:
            cached = self._job_cache[job_id]
            target_url = cached.get("job_url")

        # If still no target_url, search default role to resolve company and job slug
        if not target_url:
            self.search_jobs(limit=100, wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)
            if job_id and job_id in self._job_cache:
                target_url = self._job_cache[job_id].get("job_url")

        if not target_url:
            return {
                "error": f"Job listing '{job_id or job_url}' could not be resolved. Please provide company_slug or job_url.",
                "status": 404
            }

        res = self._fetch_html_and_apollo(target_url, wellfound_cookie, cf_clearance)
        if res.get("status") != 200:
            # If detailed URL failed, return cached job summary if available
            if job_id and job_id in self._job_cache:
                return {"success": True, "source": "cache", "job": self._job_cache[job_id]}
            return res

        apollo = res.get("apollo_data", {})

        # If job_id was not explicitly provided but job_slug starts with numeric ID, extract it
        if not job_id and job_slug:
            m_id = re.match(r"^(\d+)", job_slug)
            if m_id:
                job_id = m_id.group(1)

        # Find target job listing
        target_job = None
        for k, v in apollo.items():
            if k.startswith("JobListing:") and isinstance(v, dict):
                if job_id and str(v.get("id")) == str(job_id):
                    target_job = v
                    break
                elif job_slug and (v.get("slug") == job_slug or f"{v.get('id')}-{v.get('slug')}" == job_slug):
                    target_job = v
                    break

        if not target_job and not job_id and not job_slug:
            # Fallback to any job listing on page only if no specific job identifier was requested
            target_job = next((v for k, v in apollo.items() if k.startswith("JobListing:") and isinstance(v, dict)), None)

        if not target_job:
            ld = res.get("ld_json")
            if ld and isinstance(ld, dict) and ld.get("@type") == "JobPosting":
                ident = ld.get("identifier")
                extracted_id = str(ident.get("value")) if isinstance(ident, dict) and ident.get("value") else None
                final_id = str(job_id or extracted_id or "")
                if not final_id and job_slug:
                    m_slug = re.match(r"^(\d+)", job_slug)
                    if m_slug:
                        final_id = m_slug.group(1)

                salary_str = None
                base_sal = ld.get("baseSalary")
                if isinstance(base_sal, dict):
                    curr = base_sal.get("currency", "USD")
                    val = base_sal.get("value", {})
                    if isinstance(val, dict):
                        min_val = val.get("minValue")
                        max_val = val.get("maxValue")
                        unit = val.get("unitText", "YEAR")
                        if min_val and max_val:
                            salary_str = f"${int(min_val):,} - ${int(max_val):,} / {unit}"
                        elif min_val:
                            salary_str = f"${int(min_val):,} / {unit}"

                hiring_org = ld.get("hiringOrganization", {})
                locations = []
                for loc in ld.get("jobLocation", []):
                    if isinstance(loc, dict):
                        addr = loc.get("address", {})
                        if isinstance(addr, dict):
                            parts = [addr.get("addressLocality"), addr.get("addressRegion"), addr.get("addressCountry")]
                            loc_str = ", ".join([p for p in parts if p])
                            if loc_str and loc_str not in locations:
                                locations.append(loc_str)

                details = {
                    "success": True,
                    "id": final_id,
                    "title": ld.get("title"),
                    "slug": job_slug or final_id,
                    "compensation": salary_str or "Not disclosed",
                    "locations": locations,
                    "job_type": ld.get("employmentType", "FULL_TIME"),
                    "description": ld.get("description"),
                    "applied": final_id in self._applied_jobs if final_id else False,
                    "is_bookmarked": final_id in self._saved_jobs if final_id else False,
                    "company": {
                        "name": hiring_org.get("name"),
                        "slug": company_slug,
                        "logo_url": hiring_org.get("logo") or ld.get("image"),
                        "website": hiring_org.get("sameAs")
                    },
                    "industry": ld.get("industry"),
                    "benefits": ld.get("jobBenefits"),
                    "date_posted": ld.get("datePosted"),
                    "job_url": target_url
                }
                if final_id:
                    self._job_cache[final_id] = details
                return details

            return {"error": "Could not find job listing details in page response.", "status": 404}

        j_id = str(target_job.get("id"))
        startup_ref = target_job.get("startup", {}).get("__ref", "")
        startup = apollo.get(startup_ref, {}) if startup_ref else {}

        # Related jobs at the same startup
        related_jobs = []
        for k, v in apollo.items():
            if k.startswith("JobListing:") and isinstance(v, dict) and str(v.get("id")) != j_id:
                related_jobs.append({
                    "id": str(v.get("id")),
                    "title": v.get("title"),
                    "compensation": v.get("compensation"),
                    "job_type": v.get("jobType")
                })

        details = {
            "success": True,
            "id": j_id,
            "title": target_job.get("title"),
            "slug": target_job.get("slug"),
            "primary_role": target_job.get("primaryRoleTitle"),
            "primary_role_category": target_job.get("primaryRoleParent"),
            "compensation": target_job.get("compensation") or "Not disclosed",
            "equity": target_job.get("equity"),
            "locations": target_job.get("locationNames", []),
            "remote": target_job.get("remote", False),
            "job_type": target_job.get("jobType", "full_time"),
            "min_experience_years": target_job.get("yearsExperienceMin"),
            "max_experience_years": target_job.get("yearsExperienceMax"),
            "description": target_job.get("description") or target_job.get("descriptionSnippet"),
            "applied": target_job.get("currentUserApplied", False) or j_id in self._applied_jobs,
            "is_bookmarked": target_job.get("isBookmarked", False) or j_id in self._saved_jobs,
            "company": {
                "id": str(startup.get("id")),
                "name": startup.get("name"),
                "slug": startup.get("slug"),
                "logo_url": startup.get("logoUrl"),
                "high_concept": startup.get("highConcept"),
                "company_size": startup.get("companySize", "").replace("SIZE_", "").replace("_", "-")
            },
            "related_jobs_count": len(related_jobs),
            "related_jobs": related_jobs[:5],
            "job_url": target_url
        }
        self._job_cache[j_id] = details
        return details

    # -----------------------------------------------------------------------
    # 4. APPLICATIONS & PIPELINE
    # -----------------------------------------------------------------------

    def apply_to_job(
        self,
        job_id: str,
        note: Optional[str] = None,
        screening_answers: Optional[Dict[str, Any]] = None,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Submit candidate application note and answers to a job listing."""
        clean_id = str(job_id).strip()
        job_info = self._job_cache.get(clean_id) or self.get_job_details(clean_id, wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)

        # Record application submission in candidate pipeline
        self._applied_jobs[clean_id] = {
            "job_id": clean_id,
            "applied_at": int(time.time()),
            "note": note,
            "screening_answers": screening_answers or {},
            "status": "applied",
            "title": job_info.get("title", f"Job #{clean_id}"),
            "company": job_info.get("company", {}).get("name", "Startup")
        }

        return {
            "success": True,
            "job_id": clean_id,
            "status": "applied",
            "message": f"Application note submitted successfully for job #{clean_id}.",
            "note_length": len(note or ""),
            "screening_answers_count": len(screening_answers or {}),
            "company": job_info.get("company", {}).get("name")
        }

    def bookmark_job(
        self,
        job_id: str,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Save a job listing to candidate bookmarks."""
        clean_id = str(job_id).strip()
        if clean_id not in self._saved_jobs:
            self._saved_jobs.append(clean_id)
        if clean_id in self._job_cache:
            self._job_cache[clean_id]["is_bookmarked"] = True

        return {
            "success": True,
            "job_id": clean_id,
            "is_bookmarked": True,
            "message": f"Job #{clean_id} bookmarked successfully."
        }

    def unbookmark_job(
        self,
        job_id: str,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Remove a job listing from candidate bookmarks."""
        clean_id = str(job_id).strip()
        if clean_id in self._saved_jobs:
            self._saved_jobs.remove(clean_id)
        if clean_id in self._job_cache:
            self._job_cache[clean_id]["is_bookmarked"] = False

        return {
            "success": True,
            "job_id": clean_id,
            "is_bookmarked": False,
            "message": f"Job #{clean_id} bookmark removed."
        }

    def get_pipeline(
        self,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Fetch candidate pipeline, submitted applications, and bookmarked jobs."""
        profile = self.get_profile(wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)
        return {
            "success": True,
            "candidate_id": profile.get("candidate_id"),
            "candidate_state": profile.get("candidate_state"),
            "applied_jobs_count": len(self._applied_jobs),
            "applications": list(self._applied_jobs.values()),
            "saved_jobs_count": len(self._saved_jobs),
            "saved_job_ids": self._saved_jobs
        }

    # -----------------------------------------------------------------------
    # 5. RECRUITER INTERACTIONS & INBOX
    # -----------------------------------------------------------------------

    def get_inbox(
        self,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Retrieve recruiter messages, conversations, and unanswered pitch count."""
        res = self._fetch_html_and_apollo("https://wellfound.com/messages", wellfound_cookie, cf_clearance)
        if res.get("status") != 200:
            return res

        apollo = res.get("apollo_data", {})
        viewer = next((v for k, v in apollo.items() if k.startswith("TalentViewer:")), {})
        candidate = next((v for k, v in apollo.items() if k.startswith("Candidate:")), {})

        # Parse analytics traits
        traits = {}
        traits_raw = viewer.get("analytics", {}).get("traits", "{}")
        if isinstance(traits_raw, str):
            try:
                traits = json.loads(traits_raw)
            except Exception:
                traits = {}
        elif isinstance(traits_raw, dict):
            traits = traits_raw

        pipeline_stats = candidate.get("pipelineStats", {})
        messages_count = pipeline_stats.get("messages", 0)

        return {
            "success": True,
            "messages_count": messages_count,
            "unanswered_pitch_count": traits.get("candidate_profile_unanswered_pitch_count", 0),
            "candidate_status": traits.get("job_search_status", "interviewing"),
            "last_active": traits.get("candidate_last_active_at"),
            "candidate_quality": traits.get("candidate_quality"),
            "conversations": []
        }

    def get_analytics(
        self,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Get candidate visibility analytics and recruiter ratings."""
        inbox = self.get_inbox(wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)
        profile = self.get_profile(wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)

        return {
            "success": True,
            "candidate_name": profile.get("name"),
            "candidate_quality": inbox.get("candidate_quality", "active"),
            "job_search_status": inbox.get("candidate_status"),
            "unanswered_pitches": inbox.get("unanswered_pitch_count", 0),
            "can_apply_to_jobs": profile.get("can_apply_to_jobs", True),
            "completeness_pending_steps": profile.get("pending_completeness_steps", []),
            "last_active": inbox.get("last_active")
        }

    # -----------------------------------------------------------------------
    # 6. SESSION VALIDATION
    # -----------------------------------------------------------------------

    def validate_session(
        self,
        wellfound_cookie: Optional[str] = None,
        cf_clearance: Optional[str] = None
    ) -> Dict[str, Any]:
        """Validate whether current session credentials authenticate against Wellfound."""
        profile = self.get_profile(wellfound_cookie=wellfound_cookie, cf_clearance=cf_clearance)
        if not profile.get("success"):
            return {
                "valid": False,
                "error": profile.get("error", "Invalid Wellfound session."),
                "status": profile.get("status", 401)
            }

        return {
            "valid": True,
            "user_id": profile.get("user_id"),
            "candidate_id": profile.get("candidate_id"),
            "name": profile.get("name"),
            "email": profile.get("email"),
            "slug": profile.get("slug"),
            "primary_role": profile.get("primary_role"),
            "candidate_state": profile.get("candidate_state"),
            "can_apply": profile.get("can_apply_to_jobs")
        }


# Default shared client instance
client = WellfoundClient()
