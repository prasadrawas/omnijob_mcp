"""
Connector Registry for OmniJob MCP.
Provides lazy-loaded, thread-safe access to all 7 job platform connectors.
"""
from typing import Dict, List, Optional, Type
import logging
from threading import Lock

from omnijob_mcp.core.base import BaseConnector

logger = logging.getLogger("omnijob_mcp.registry")

# Platform slug aliases for resilient user/LLM input resolution
CONNECTOR_ALIASES = {
    "monster": "foundit",
    "monsterindia": "foundit",
    "found_it": "foundit",
    "foundit.in": "foundit",
    "angellist": "wellfound",
    "angel": "wellfound",
    "well_found": "wellfound",
    "wellfound.com": "wellfound",
    "naukri.com": "naukri",
    "naukri_mcp": "naukri",
    "hirist.tech": "hirist",
    "hirist_mcp": "hirist",
    "cut_short": "cutshort",
    "cutshort.io": "cutshort",
    "insta_hyre": "instahyre",
    "instahyre.com": "instahyre",
    "green_house": "greenhouse",
    "greenhouse.io": "greenhouse",
}


class ConnectorRegistry:
    """Singleton registry holding references to available platform connectors."""

    _instance: Optional["ConnectorRegistry"] = None
    _lock: Lock = Lock()

    def __init__(self) -> None:
        self._connector_classes: Dict[str, Type[BaseConnector]] = {}
        self._connector_instances: Dict[str, BaseConnector] = {}
        self._init_lock = Lock()

    @classmethod
    def get_instance(cls) -> "ConnectorRegistry":
        if cls._instance is None:
            with cls._lock:
                if cls._instance is None:
                    cls._instance = cls()
                    cls._instance._register_defaults()
        return cls._instance

    def _register_defaults(self) -> None:
        """Register connector classes using lazy imports."""
        # 1. Naukri
        try:
            from omnijob_mcp.connectors.naukri.connector import NaukriConnector
            self.register_class("naukri", NaukriConnector)
        except Exception as e:
            logger.warning(f"Failed to register Naukri connector: {e}")

        # 2. Hirist
        try:
            from omnijob_mcp.connectors.hirist.connector import HiristConnector
            self.register_class("hirist", HiristConnector)
        except Exception as e:
            logger.warning(f"Failed to register Hirist connector: {e}")

        # 3. Wellfound
        try:
            from omnijob_mcp.connectors.wellfound.connector import WellfoundConnector
            self.register_class("wellfound", WellfoundConnector)
        except Exception as e:
            logger.warning(f"Failed to register Wellfound connector: {e}")

        # 4. Instahyre
        try:
            from omnijob_mcp.connectors.instahyre.connector import InstahyreConnector
            self.register_class("instahyre", InstahyreConnector)
        except Exception as e:
            logger.warning(f"Failed to register Instahyre connector: {e}")

        # 5. Cutshort
        try:
            from omnijob_mcp.connectors.cutshort.connector import CutshortConnector
            self.register_class("cutshort", CutshortConnector)
        except Exception as e:
            logger.warning(f"Failed to register Cutshort connector: {e}")

        # 6. Greenhouse
        try:
            from omnijob_mcp.connectors.greenhouse.connector import GreenhouseConnector
            self.register_class("greenhouse", GreenhouseConnector)
        except Exception as e:
            logger.warning(f"Failed to register Greenhouse connector: {e}")

        # 7. Foundit
        try:
            from omnijob_mcp.connectors.foundit.connector import FounditConnector
            self.register_class("foundit", FounditConnector)
        except Exception as e:
            logger.warning(f"Failed to register Foundit connector: {e}")

    def register_class(self, name: str, cls: Type[BaseConnector]) -> None:
        self._connector_classes[name.lower()] = cls

    def resolve_name(self, name: str) -> str:
        clean = name.strip().lower()
        return CONNECTOR_ALIASES.get(clean, clean)

    def get(self, name: str) -> Optional[BaseConnector]:
        canonical_name = self.resolve_name(name)
        if canonical_name in self._connector_instances:
            return self._connector_instances[canonical_name]

        with self._init_lock:
            if canonical_name in self._connector_instances:
                return self._connector_instances[canonical_name]

            cls = self._connector_classes.get(canonical_name)
            if cls is not None:
                instance = cls()
                self._connector_instances[canonical_name] = instance
                return instance

        return None

    def list_connectors(self) -> List[str]:
        return sorted(list(self._connector_classes.keys()))

    def get_all(self) -> Dict[str, BaseConnector]:
        result = {}
        for name in self.list_connectors():
            conn = self.get(name)
            if conn:
                result[name] = conn
        return result

    def get_authenticated(self) -> Dict[str, BaseConnector]:
        result = {}
        for name, conn in self.get_all().items():
            try:
                if conn.is_authenticated():
                    result[name] = conn
            except Exception:
                pass
        return result

    def get_status_all(self) -> Dict[str, Any]:
        all_conns = self.get_all()
        summary = {}
        for name, conn in all_conns.items():
            try:
                summary[name] = conn.get_health().model_dump()
            except Exception as e:
                summary[name] = {
                    "connector": name,
                    "display_name": getattr(conn, "display_name", name),
                    "status": "error",
                    "details": {"error": str(e)},
                }
        return {
            "total_connectors": len(all_conns),
            "authenticated_count": len([c for c in summary.values() if c.get("status") == "authenticated"]),
            "connectors": summary,
        }
