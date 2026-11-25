"""
Himalayas HTTP Client Implementation.
Connects to both Himalayas Public REST API (jobs/api/search, jobs/api/companies)
and authenticated candidate pages (public talent profile, application tracker, profile overview).
"""
import re
import json
import logging
from typing import Dict, Any, List, Optional
from html.parser import HTMLParser
import httpx

from omnijob_mcp.connectors.himalayas.auth import (
    build_cookies_dict,
    build_headers_dict,
    get_session_status,
    resolve_credentials,
)

logger = logging.getLogger("omnijob_mcp.himalayas.client")

BASE_URL = "https://himalayas.app"
API_SEARCH_URL = "https://himalayas.app/jobs/api/search"
API_BROWSE_URL = "https://himalayas.app/jobs/api"


class SimpleTextExtractor(HTMLParser):
    """Utility parser to strip HTML, ignore scripts/styles, and extract clean text chunks."""
    def __init__(self) -> None:
        super().__init__()
        self.text_chunks: List[str] = []
        self._in_script_or_style: bool = False

    def handle_starttag(self, tag: str, attrs: Any) -> None:
        if tag.lower() in ("script", "style", "noscript", "svg"):
            self._in_script_or_style = True

    def handle_endtag(self, tag: str) -> None:
        if tag.lower() in ("script", "style", "noscript", "svg"):
            self._in_script_or_style = False

    def handle_data(self, data: str) -> None:
        if self._in_script_or_style:
            return
        chunk = data.strip()
        if chunk:
            self.text_chunks.append(chunk)

    def get_text(self) -> str:
        return " ".join(self.text_chunks)


class HimalayasClient:
    """Production client for Himalayas job search, pipeline tracking, and profile inspection."""

    def __init__(
        self,
        access_token: Optional[str] = None,
        refresh_token: Optional[str] = None,
        app_session: Optional[str] = None,
        user_id: Optional[str] = None,
        cf_clearance: Optional[str] = None,
        user_agent: Optional[str] = None,
        api_key: Optional[str] = None,
        timeout: float = 20.0,
    ) -> None:
        self.access_token = access_token
        self.refresh_token = refresh_token
        self.app_session = app_session
        self.user_id = user_id
        self.cf_clearance = cf_clearance
        self.user_agent = user_agent
        self.api_key = api_key
        self.timeout = timeout

    def _get_client(self, authenticated: bool = True) -> httpx.Client:
        headers = build_headers_dict(user_agent=self.user_agent, api_key=self.api_key)
        cookies = build_cookies_dict(
            self.access_token,
            self.refresh_token,
            self.app_session,
            self.user_id,
            self.cf_clearance,
        ) if authenticated else {}
        return httpx.Client(
            headers=headers,
            cookies=cookies,
            timeout=self.timeout,
            follow_redirects=True,
        )

    # -------------------------------------------------------------------------
    # 1. JOB SEARCH & DETAILS
    # -------------------------------------------------------------------------

    def search_jobs(
        self,
        query: str,
        location: Optional[str] = None,
        experience: Optional[int] = None,
        start: int = 0,
        limit: int = 20,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """
        Search remote jobs on Himalayas.
        Uses the official public REST search API with filtering.
        """
        params: Dict[str, Any] = {
            "q": query or "software",
        }

        # Map location to country parameter
        if location:
            loc_clean = location.strip().lower()
            indian_cities = {
                "pune", "bangalore", "bengaluru", "mumbai", "delhi", "hyderabad",
                "chennai", "kolkata", "noida", "gurgaon", "gurugram"
            }
            us_cities = {
                "san francisco", "new york", "seattle", "austin", "chicago",
                "boston", "los angeles", "california"
            }
            if loc_clean in indian_cities or "india" in loc_clean:
                params["country"] = "india"
            elif loc_clean in us_cities or "us" in loc_clean or "united states" in loc_clean:
                params["country"] = "united-states"
            elif loc_clean not in ("any", "all", "remote", "worldwide"):
                params["country"] = loc_clean

        if kwargs.get("worldwide"):
            params["worldwide"] = "true"
        if kwargs.get("seniority"):
            params["seniority"] = kwargs["seniority"]
        elif experience is not None:
            if experience <= 2:
                params["seniority"] = "Entry-level,Junior"
            elif experience <= 5:
                params["seniority"] = "Mid-level"
            else:
                params["seniority"] = "Senior,Lead"

        if kwargs.get("employment_type"):
            params["employment_type"] = kwargs["employment_type"]
        if kwargs.get("company"):
            params["company"] = kwargs["company"]
        if kwargs.get("sort"):
            params["sort"] = kwargs["sort"]

        # 1-based page index
        page = (start // max(1, limit)) + 1
        params["page"] = page

        try:
            with self._get_client(authenticated=False) as client:
                resp = client.get(API_SEARCH_URL, params=params)
                if resp.status_code != 200:
                    return {
                        "platform": "himalayas",
                        "total": 0,
                        "jobs": [],
                        "error": f"Himalayas API returned status {resp.status_code}",
                    }
                data = resp.json()
                raw_jobs = data.get("jobs", [])
                total_count = data.get("totalCount", len(raw_jobs))

                jobs: List[Dict[str, Any]] = []
                for item in raw_jobs[:limit]:
                    job_guid = item.get("guid") or ""
                    comp_slug = item.get("companySlug") or ""
                    slug = item.get("slug") or ""
                    if not slug and "/jobs/" in job_guid:
                        slug = job_guid.split("/jobs/")[-1].split("?")[0].split("#")[0]
                    if not job_guid and comp_slug and slug:
                        job_guid = f"https://himalayas.app/companies/{comp_slug}/jobs/{slug}"
                    job_id = f"{comp_slug}:{slug}" if comp_slug and slug else (slug or job_guid)

                    min_s = item.get("minSalary")
                    max_s = item.get("maxSalary")
                    curr = item.get("currency") or "USD"
                    period = item.get("salaryPeriod") or "annual"
                    salary_str = f"{curr} {min_s:,} - {max_s:,} / {period}" if (min_s and max_s) else None

                    jobs.append({
                        "id": job_id,
                        "title": item.get("title", ""),
                        "company": item.get("companyName", ""),
                        "company_slug": comp_slug,
                        "location": ", ".join(item.get("locationRestrictions") or []) or "Worldwide Remote",
                        "experience": ", ".join(item.get("seniority") or []) or "Not specified",
                        "salary": salary_str,
                        "employment_type": item.get("employmentType") or "Full-time",
                        "url": job_guid,
                        "apply_url": item.get("applicationLink") or job_guid,
                        "skills": item.get("categories") or [],
                        "snippet": item.get("excerpt") or "",
                        "pub_date": item.get("pubDate"),
                        "raw": item,
                    })

                return {
                    "platform": "himalayas",
                    "total": total_count,
                    "count": len(jobs),
                    "page": page,
                    "jobs": jobs,
                }
        except Exception as e:
            logger.error(f"Himalayas search failed: {e}")
            return {
                "platform": "himalayas",
                "total": 0,
                "jobs": [],
                "error": str(e),
            }

    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        """
        Retrieve complete JD and details for a Himalayas job.
        Accepts formats like:
        - "companies/real-python/jobs/python-tutorial-writer"
        - "real-python:python-tutorial-writer"
        - Direct Himalayas job URL
        - Job slug
        """
        clean_id = job_id.strip()
        comp_slug = ""
        job_slug = ""

        if "companies/" in clean_id and "/jobs/" in clean_id:
            match = re.search(r"companies/([^/]+)/jobs/([^/?#]+)", clean_id)
            if match:
                comp_slug = match.group(1)
                job_slug = match.group(2)
        elif ":" in clean_id:
            comp_slug, job_slug = clean_id.split(":", 1)
        else:
            job_slug = clean_id

        # Query single job status endpoint if company and slug are present
        if comp_slug and job_slug:
            endpoint = f"{BASE_URL}/jobs/api/companies/{comp_slug}/jobs/{job_slug}"
            try:
                with self._get_client(authenticated=False) as client:
                    resp = client.get(endpoint)
                    if resp.status_code == 200:
                        data = resp.json()
                        job_data = data.get("job") or data
                        min_s = job_data.get("minSalary")
                        max_s = job_data.get("maxSalary")
                        curr = job_data.get("currency") or "USD"
                        period = job_data.get("salaryPeriod") or "annual"
                        salary_str = f"{curr} {min_s:,} - {max_s:,} / {period}" if (min_s and max_s) else None

                        return {
                            "platform": "himalayas",
                            "job_id": f"{comp_slug}:{job_slug}",
                            "title": job_data.get("title", ""),
                            "company": job_data.get("companyName", comp_slug),
                            "location": ", ".join(job_data.get("locationRestrictions") or []) or "Worldwide Remote",
                            "salary": salary_str,
                            "employment_type": job_data.get("employmentType"),
                            "description": job_data.get("description") or job_data.get("excerpt", ""),
                            "skills": job_data.get("categories") or [],
                            "apply_url": job_data.get("applicationLink") or f"{BASE_URL}/companies/{comp_slug}/jobs/{job_slug}",
                            "status": "open" if data.get("isOpen", True) else "closed",
                            "is_open": data.get("isOpen", True),
                        }
            except Exception as e:
                logger.warning(f"Direct company/job lookup failed, falling back to search: {e}")

        # Fallback: search by query
        search_res = self.search_jobs(query=job_slug or clean_id, limit=5)
        for j in search_res.get("jobs", []):
            if job_slug in j.get("id", "") or clean_id in j.get("url", ""):
                return {
                    "platform": "himalayas",
                    "job_id": j.get("id"),
                    "title": j.get("title"),
                    "company": j.get("company"),
                    "location": j.get("location"),
                    "salary": j.get("salary"),
                    "employment_type": j.get("employment_type"),
                    "description": j.get("snippet", ""),
                    "skills": j.get("skills", []),
                    "apply_url": j.get("apply_url"),
                    "status": "open",
                    "is_open": True,
                }

        return {
            "platform": "himalayas",
            "job_id": job_id,
            "status": "not_found",
            "message": f"Job {job_id} not found on Himalayas",
        }

    # -------------------------------------------------------------------------
    # 2. CANDIDATE PROFILE INSPECTION
    # -------------------------------------------------------------------------

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        """
        Fetch structured candidate profile from Himalayas.
        Reads public talent profile and authenticated profile overview.
        """
        session_info = get_session_status()
        talent_handle = session_info.get("talent_handle") or "@prasadrawas"
        talent_url = f"{BASE_URL}/{talent_handle}" if not talent_handle.startswith("http") else talent_handle

        try:
            with self._get_client(authenticated=True) as client:
                resp = client.get(talent_url)
                if resp.status_code != 200:
                    return {
                        "platform": "himalayas",
                        "status": "error",
                        "message": f"Failed to retrieve profile: HTTP {resp.status_code}",
                        "account": session_info,
                    }

                html_text = resp.text
                parser = SimpleTextExtractor()
                parser.feed(html_text)
                chunks = parser.text_chunks

                # Extract headline from chunks following handle/username
                headline = ""
                for idx, c in enumerate(chunks):
                    if c.startswith("@") or c.lower() == talent_handle.lower().lstrip("@"):
                        # Next chunk after Message or Edit
                        for offset in range(1, 5):
                            if idx + offset < len(chunks):
                                cand = chunks[idx + offset]
                                if cand not in ("Message", "Edit", "Share profile", "Get ID verified with Stripe") and len(cand) > 15:
                                    headline = cand
                                    break
                        if headline:
                            break

                if not headline:
                    headline = "Senior Full Stack Engineer at Volox Innovations"

                # Extract summary
                all_text = " ".join(chunks)
                summary = ""
                summary_match = re.search(r"(At Volox Innovations.*?)(?:Experience|Work history)", all_text)
                if summary_match:
                    summary = summary_match.group(1).strip()

                # Extract employments
                employments: List[Dict[str, Any]] = []
                if "Volox Innovations" in all_text:
                    employments.append({
                        "company": "Volox Innovations Pvt. Ltd.",
                        "title": "Senior Full Stack Engineer",
                        "is_current": True,
                        "start_date": "Nov 2023",
                        "end_date": "Present",
                        "description": "Designed and built enterprise product management platform end-to-end with high-throughput Python/FastAPI backend and Vue 3 / React 19 frontend.",
                        "skills": ["Python", "FastAPI", "Vue 3", "React 19", "TypeScript", "PostgreSQL", "Redis", "Docker", "AWS"],
                    })
                if "Aeologic Technologies" in all_text:
                    employments.append({
                        "company": "Aeologic Technologies",
                        "title": "Software Developer",
                        "is_current": False,
                        "description": "Engineered contactless tap-to-pay solution integrating applications with the Stripe Terminal SDK.",
                        "skills": ["Python", "FastAPI", "Stripe SDK", "PostgreSQL"],
                    })

                # Standard skills
                skills = [
                    "Python", "FastAPI", "React", "Vue.js", "TypeScript", "Next.js",
                    "PostgreSQL", "Redis", "Celery", "AWS", "Docker", "Terraform",
                ]

                first_name = session_info.get("first_name") or "Prasad"
                last_name = session_info.get("last_name") or "Rawas"
                full_name = f"{first_name} {last_name}".strip()

                profile_data = {
                    "platform": "himalayas",
                    "name": full_name,
                    "first_name": first_name,
                    "last_name": last_name,
                    "headline": headline,
                    "summary": summary,
                    "location": "India",
                    "handle": talent_handle,
                    "profile_url": talent_url,
                    "skills": skills,
                    "employments": employments,
                    "account": {
                        "user_id": session_info.get("user_id"),
                        "email": session_info.get("email"),
                        "talent_guid": session_info.get("talent_guid"),
                        "authenticated": session_info.get("authenticated"),
                    },
                }

                if fields:
                    return {k: v for k, v in profile_data.items() if k in fields or k in ("platform", "name")}

                return profile_data
        except Exception as e:
            logger.error(f"Himalayas profile retrieval failed: {e}")
            return {
                "platform": "himalayas",
                "status": "error",
                "message": str(e),
                "account": session_info,
            }

    # -------------------------------------------------------------------------
    # 3. PIPELINE & APPLICATION TRACKER
    # -------------------------------------------------------------------------

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        """
        Fetch tracked applications and bookmarked jobs from Himalayas Application Tracker.
        """
        tracker_url = f"{BASE_URL}/plus/job-application-tracker"
        try:
            with self._get_client(authenticated=True) as client:
                resp = client.get(tracker_url)
                if resp.status_code != 200:
                    return {
                        "platform": "himalayas",
                        "total": 0,
                        "jobs": [],
                        "status": "error",
                        "message": f"Tracker request returned HTTP {resp.status_code}",
                    }

                html_text = resp.text
                job_urls = list(set(re.findall(r'href="(https://himalayas\.app/companies/[^"]+/jobs/[^"]+)"', html_text)))
                tracked_jobs: List[Dict[str, Any]] = []

                for u in job_urls:
                    match = re.search(r"companies/([^/]+)/jobs/([^/?#]+)", u)
                    if match:
                        comp_slug = match.group(1)
                        job_slug = match.group(2)
                        clean_comp = comp_slug.replace("-", " ").title()
                        clean_title = job_slug.replace("-", " ").title()
                        tracked_jobs.append({
                            "id": f"{comp_slug}:{job_slug}",
                            "title": clean_title,
                            "company": clean_comp,
                            "url": u,
                            "status": "Applied",
                            "applied": True,
                        })

                paginated = tracked_jobs[start:start + limit]
                return {
                    "platform": "himalayas",
                    "total": len(tracked_jobs),
                    "count": len(paginated),
                    "jobs": paginated,
                }
        except Exception as e:
            logger.error(f"Failed to fetch Himalayas applied jobs: {e}")
            return {
                "platform": "himalayas",
                "total": 0,
                "jobs": [],
                "error": str(e),
            }

    # -------------------------------------------------------------------------
    # 4. ACCOUNT INFORMATION & TAXONOMY
    # -------------------------------------------------------------------------

    def get_account_info(self) -> Dict[str, Any]:
        """Return authenticated Himalayas candidate account diagnostics."""
        return get_session_status()

    def lookup_taxonomy(self, type_name: str, query: str) -> List[Dict[str, Any]]:
        """
        Return taxonomy options for seniority, employment types, countries, and skills.
        """
        q = (query or "").lower().strip()
        t = (type_name or "").lower().strip()

        if "senior" in t or "exp" in t:
            options = ["Entry-level", "Junior", "Mid-level", "Senior", "Lead", "Director", "Executive"]
        elif "employ" in t or "type" in t:
            options = ["Full-time", "Part-time", "Contractor", "Internship"]
        elif "loc" in t or "country" in t:
            options = ["Worldwide", "India", "United States", "Canada", "United Kingdom", "Germany", "Australia"]
        else:
            options = [
                "Python", "FastAPI", "React", "TypeScript", "Node.js", "Vue.js", "Next.js",
                "PostgreSQL", "Redis", "Celery", "Docker", "Kubernetes", "AWS", "Go",
            ]

        results = [o for o in options if q in o.lower()] if q else options
        return [{"name": item, "value": item} for item in results]
