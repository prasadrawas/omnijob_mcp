"""
Abstract Base Connector Interface for OmniJob MCP.
Every platform connector (Naukri, Hirist, Wellfound, Instahyre, Cutshort, Greenhouse, Foundit)
implements this interface to ensure uniform invocation across all 7 meta-tools.
"""
from abc import ABC, abstractmethod
from typing import Any, Dict, List, Optional
from omnijob_mcp.core.models import (
    JobItem,
    JobDetail,
    CandidateProfile,
    ApplicationResult,
    ConnectorHealth,
)


class BaseConnector(ABC):
    """Abstract base class for all job board and ATS connectors."""

    name: str = "base"
    display_name: str = "Base Platform"
    supported_features: List[str] = [
        "search",
        "job_details",
        "apply",
        "profile",
        "save",
        "account",
        "taxonomy",
    ]

    @abstractmethod
    def is_authenticated(self) -> bool:
        """Check if connector has active, valid authentication credentials."""
        pass

    @abstractmethod
    def get_session_status(self) -> Dict[str, Any]:
        """Return authentication status, user identity, expiry, and credential diagnostics."""
        pass

    @abstractmethod
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
        Search jobs on this platform.
        Returns a dict containing 'jobs' (List of normalized JobItem or dicts), 'total', etc.
        """
        pass

    @abstractmethod
    def get_job_details(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Fetch detailed JD, requirements, salary, company overview, and questionnaire."""
        pass

    def can_job_apply(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Check if candidate can apply (or has already applied). Default checks status."""
        return {
            "platform": self.name,
            "job_id": job_id,
            "can_apply": True,
            "message": "Application pre-check supported.",
        }

    @abstractmethod
    def apply_to_job(
        self,
        job_id: str,
        answers: Optional[Dict[str, Any]] = None,
        dry_run: bool = False,
        **kwargs: Any,
    ) -> Dict[str, Any]:
        """Submit application to a job listing."""
        pass

    def save_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Save/bookmark a job for later."""
        return {
            "platform": self.name,
            "job_id": job_id,
            "status": "unsupported",
            "message": f"save_job is not implemented for {self.display_name}",
        }

    def unsave_job(self, job_id: str, **kwargs: Any) -> Dict[str, Any]:
        """Remove a job from saved/bookmarks."""
        return {
            "platform": self.name,
            "job_id": job_id,
            "status": "unsupported",
            "message": f"unsave_job is not implemented for {self.display_name}",
        }

    def get_applied_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve candidate's previously submitted applications."""
        return {
            "platform": self.name,
            "total": 0,
            "jobs": [],
            "message": f"get_applied_jobs not supported or not implemented on {self.display_name}",
        }

    def get_saved_jobs(self, start: int = 0, limit: int = 20, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve candidate's bookmarked/saved jobs."""
        return {
            "platform": self.name,
            "total": 0,
            "jobs": [],
            "message": f"get_saved_jobs not supported or not implemented on {self.display_name}",
        }

    def get_profile(self, fields: Optional[List[str]] = None, **kwargs: Any) -> Dict[str, Any]:
        """Retrieve candidate profile data."""
        return {
            "platform": self.name,
            "message": f"get_profile is not implemented for {self.display_name}",
        }

    def update_profile(self, action: str, payload: Optional[Dict[str, Any]] = None, **kwargs: Any) -> Dict[str, Any]:
        """Update a section of the candidate profile or trigger an activity pulse."""
        return {
            "platform": self.name,
            "action": action,
            "message": f"update_profile is not implemented for {self.display_name}",
        }

    def manage_account(self, action: str, **kwargs: Any) -> Dict[str, Any]:
        """Manage recruiter inbox, alerts, recommendations, company blocking, or analytics."""
        return {
            "platform": self.name,
            "action": action,
            "message": f"manage_account is not implemented for {self.display_name}",
        }

    def lookup_taxonomy(self, type_name: str, query: str, **kwargs: Any) -> Dict[str, Any]:
        """Autocomplete or search platform taxonomy (skills, locations, companies, job titles)."""
        return {
            "platform": self.name,
            "type": type_name,
            "query": query,
            "suggestions": [],
            "message": f"lookup_taxonomy is not implemented for {self.display_name}",
        }

    def refresh_session(self) -> Dict[str, Any]:
        """Attempt token renewal or re-verification."""
        return {
            "platform": self.name,
            "refreshed": False,
            "message": f"Session refresh not required or not supported for {self.display_name}",
        }

    def get_health(self) -> ConnectorHealth:
        """Standardized health check representation."""
        status = self.get_session_status()
        is_auth = self.is_authenticated()
        state = "authenticated" if is_auth else ("configured" if status.get("has_keys") else "unauthenticated")
        return ConnectorHealth(
            connector=self.name,
            display_name=self.display_name,
            status=state,
            supported_features=self.supported_features,
            details=status,
        )
