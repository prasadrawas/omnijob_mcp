"""
Unit tests verifying BaseConnector compliance across all 7 platform connectors.
"""
import unittest
from omnijob_mcp.core.registry import ConnectorRegistry
from omnijob_mcp.core.base import BaseConnector


class TestConnectorsUnit(unittest.TestCase):
    def setUp(self):
        self.registry = ConnectorRegistry.get_instance()

    def test_all_connectors_implement_base(self):
        names = ["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"]
        for name in names:
            with self.subTest(connector=name):
                conn = self.registry.get(name)
                self.assertIsNotNone(conn, f"Connector {name} could not be loaded")
                self.assertIsInstance(conn, BaseConnector)
                self.assertEqual(conn.name, name)
                self.assertTrue(len(conn.display_name) > 0)
                self.assertTrue(len(conn.supported_features) > 0)

    def test_session_status_and_health(self):
        names = ["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"]
        for name in names:
            with self.subTest(connector=name):
                conn = self.registry.get(name)
                status = conn.get_session_status()
                self.assertIsInstance(status, dict)
                health = conn.get_health()
                self.assertEqual(health.connector, name)
                self.assertIn(health.status, ["authenticated", "configured", "unauthenticated", "error"])


if __name__ == "__main__":
    unittest.main()
