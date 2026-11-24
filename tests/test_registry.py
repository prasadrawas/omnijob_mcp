"""
Unit tests for OmniJob MCP Connector Registry.
"""
import unittest
from omnijob_mcp.core.registry import ConnectorRegistry, CONNECTOR_ALIASES
from omnijob_mcp.core.base import BaseConnector


class TestConnectorRegistry(unittest.TestCase):
    def setUp(self):
        self.registry = ConnectorRegistry.get_instance()

    def test_registered_connectors(self):
        connectors = self.registry.list_connectors()
        expected = ["cutshort", "foundit", "greenhouse", "hirist", "instahyre", "naukri", "wellfound"]
        for exp in expected:
            self.assertIn(exp, connectors)

    def test_alias_resolution(self):
        self.assertEqual(self.registry.resolve_name("monster"), "foundit")
        self.assertEqual(self.registry.resolve_name("MonsterIndia"), "foundit")
        self.assertEqual(self.registry.resolve_name("angellist"), "wellfound")
        self.assertEqual(self.registry.resolve_name("naukri.com"), "naukri")
        self.assertEqual(self.registry.resolve_name("cut_short"), "cutshort")
        self.assertEqual(self.registry.resolve_name("insta_hyre"), "instahyre")
        self.assertEqual(self.registry.resolve_name("green_house"), "greenhouse")

    def test_connector_retrieval(self):
        foundit = self.registry.get("foundit")
        self.assertIsNotNone(foundit)
        assert foundit is not None
        self.assertIsInstance(foundit, BaseConnector)
        self.assertEqual(foundit.name, "foundit")

        # Test via alias
        monster = self.registry.get("monster")
        self.assertEqual(monster, foundit)

    def test_get_status_all(self):
        status = self.registry.get_status_all()
        self.assertEqual(status["total_connectors"], 7)
        self.assertIn("connectors", status)
        for name in ["naukri", "hirist", "wellfound", "instahyre", "cutshort", "greenhouse", "foundit"]:
            self.assertIn(name, status["connectors"])


if __name__ == "__main__":
    unittest.main()
