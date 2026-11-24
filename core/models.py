"""
Data models and schemas for OmniJob MCP.
Provides standardized, normalized representations for jobs, profiles, applications, and connector health.
"""
from typing import Any, Dict, List, Optional
from pydantic import BaseModel, Field


class JobItem(BaseModel):
    """Normalized summary of a job listing across any supported platform."""
    id: str = Field(description="Unique job ID within the platform")
    platform: str = Field(description="Platform identifier (naukri, hirist, wellfound, instahyre, cutshort, greenhouse, foundit)")
    title: str = Field(description="Job designation / role title")
    company: str = Field(description="Hiring company name")
    location: str = Field(default="", description="Location or remote status")
    experience: Optional[str] = Field(default=None, description="Experience requirement string")
    salary: Optional[str] = Field(default=None, description="Salary or compensation package")
    skills: List[str] = Field(default_factory=list, description="Tagged primary skills")
    posted_date: Optional[str] = Field(default=None, description="Posting date or relative age")
    apply_url: Optional[str] = Field(default=None, description="Direct web URL to apply or view")
    is_easy_apply: bool = Field(default=True, description="Whether 1-click in-platform application is supported")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Platform-specific metadata")


class JobDetail(BaseModel):
    """Normalized full job description and requirements."""
    id: str = Field(description="Platform job ID")
    platform: str = Field(description="Platform identifier")
    title: str = Field(description="Job title")
    company: str = Field(description="Company name")
    location: str = Field(default="", description="Location or remote status")
    description: str = Field(default="", description="Clean text or markdown job description")
    experience: Optional[str] = Field(default=None, description="Experience requirement")
    salary: Optional[str] = Field(default=None, description="Salary details")
    skills: List[str] = Field(default_factory=list, description="Required & preferred skills")
    company_info: Dict[str, Any] = Field(default_factory=dict, description="Company overview, website, size")
    screening_questions: Optional[List[Dict[str, Any]]] = Field(default=None, description="Assessment or screening questions")
    can_apply: bool = Field(default=True, description="Whether currently eligible to apply via API")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw platform attributes")


class CandidateProfile(BaseModel):
    """Normalized candidate profile structure."""
    platform: str = Field(description="Platform name")
    name: Optional[str] = Field(default=None, description="Candidate full name")
    email: Optional[str] = Field(default=None, description="Primary email address")
    mobile: Optional[str] = Field(default=None, description="Contact phone number")
    headline: Optional[str] = Field(default=None, description="Professional headline")
    summary: Optional[str] = Field(default=None, description="Executive summary / bio")
    location: Optional[str] = Field(default=None, description="Current city / country")
    experience_years: Optional[float] = Field(default=None, description="Total years of professional experience")
    skills: List[str] = Field(default_factory=list, description="Top skills")
    current_company: Optional[str] = Field(default=None, description="Current employer")
    current_designation: Optional[str] = Field(default=None, description="Current role")
    notice_period: Optional[str] = Field(default=None, description="Notice period (e.g. 30 days)")
    employment: List[Dict[str, Any]] = Field(default_factory=list, description="Employment history")
    education: List[Dict[str, Any]] = Field(default_factory=list, description="Education records")
    metadata: Dict[str, Any] = Field(default_factory=dict, description="Raw profile data")


class ApplicationResult(BaseModel):
    """Standardized response from an application submission."""
    platform: str = Field(description="Platform applied on")
    job_id: str = Field(description="Job ID")
    status: str = Field(description="Result status: 'applied', 'already_applied', 'requires_external_url', 'failed', 'dry_run_success'")
    message: str = Field(description="Human-readable outcome description")
    details: Dict[str, Any] = Field(default_factory=dict, description="Detailed API payload or confirmation tokens")


class ConnectorHealth(BaseModel):
    """Health and authentication status for a platform connector."""
    connector: str = Field(description="Connector slug")
    display_name: str = Field(description="Connector human-friendly name")
    status: str = Field(description="'authenticated', 'configured', 'unauthenticated', or 'error'")
    supported_features: List[str] = Field(default_factory=list, description="List of supported operations")
    details: Dict[str, Any] = Field(default_factory=dict, description="Additional status diagnostics")
