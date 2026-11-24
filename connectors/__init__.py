"""
OmniJob MCP Platform Connectors.
Exposes connectors for Naukri, Hirist, Wellfound, Instahyre, Cutshort, Greenhouse, and Foundit.
"""
from omnijob_mcp.connectors.naukri.connector import NaukriConnector
from omnijob_mcp.connectors.hirist.connector import HiristConnector
from omnijob_mcp.connectors.wellfound.connector import WellfoundConnector
from omnijob_mcp.connectors.instahyre.connector import InstahyreConnector
from omnijob_mcp.connectors.cutshort.connector import CutshortConnector
from omnijob_mcp.connectors.greenhouse.connector import GreenhouseConnector
from omnijob_mcp.connectors.foundit.connector import FounditConnector

__all__ = [
    "NaukriConnector",
    "HiristConnector",
    "WellfoundConnector",
    "InstahyreConnector",
    "CutshortConnector",
    "GreenhouseConnector",
    "FounditConnector",
]
