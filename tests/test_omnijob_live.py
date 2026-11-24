"""
Live smoke verification test across active OmniJob MCP platform connectors.
"""
import unittest
import asyncio
from omnijob_mcp.server import search_jobs, manage_profile, manage_session


class TestOmniJobLive(unittest.TestCase):
    def test_multi_platform_search_fanout(self):
        result = asyncio.run(search_jobs(connector="all", query="Python Engineer", location="Pune", limit=5))
        self.assertTrue(result.get("success"))
        self.assertEqual(result.get("mode"), "multi_platform_search")
        self.assertIn("platform_breakdown", result)
        self.assertGreater(result.get("total_aggregated", 0), 0)
        print("\nMulti-platform fan-out breakdown:", result.get("platform_breakdown"))

    def test_foundit_live_profile(self):
        result = asyncio.run(manage_profile(connector="foundit", action="get"))
        self.assertEqual(result.get("platform"), "foundit")
        self.assertIsNotNone(result.get("name"))
        print("\nFoundit Live Profile Name:", result.get("name"))

    def test_naukri_live_profile(self):
        result = asyncio.run(manage_profile(connector="naukri", action="get"))
        self.assertEqual(result.get("platform"), "naukri")
        self.assertIsNotNone(result.get("name"))
        print("Naukri Live Profile Name:", result.get("name"))

    def test_session_dashboard(self):
        result = asyncio.run(manage_session(connector="all", action="status"))
        self.assertEqual(result.get("total_connectors"), 7)
        self.assertGreaterEqual(result.get("authenticated_count"), 5)
        print("OmniJob Authenticated Connectors:", f"{result.get('authenticated_count')}/7")


if __name__ == "__main__":
    unittest.main()
