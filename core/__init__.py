"""
OmniJob MCP Core Package.
Provides BaseConnector, Registry, Normalized Models, and Thread-Safe Cache.
"""
from omnijob_mcp.core.base import BaseConnector
from omnijob_mcp.core.models import (
    JobItem,
    JobDetail,
    CandidateProfile,
    ApplicationResult,
    ConnectorHealth,
)
from omnijob_mcp.core.registry import ConnectorRegistry
from omnijob_mcp.core.cache import TTLCache

__all__ = [
    "BaseConnector",
    "JobItem",
    "JobDetail",
    "CandidateProfile",
    "ApplicationResult",
    "ConnectorHealth",
    "ConnectorRegistry",
    "TTLCache",
]
