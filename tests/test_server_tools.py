"""
Integration & unit tests for OmniJob MCP FastMCP meta-tools.
"""
import unittest
import asyncio
from omnijob_mcp.server import (
    search_jobs,
    get_job_details,
    manage_job_pipeline,
    manage_profile,
    manage_account,
    manage_taxonomy,
    manage_session,
)


class TestServerMetaTools(unittest.TestCase):
    def test_manage_session_status_all(self):
        result = asyncio.run(manage_session(connector="all", action="status"))
        self.assertEqual(result["total_connectors"], 7)
        self.assertIn("connectors", result)
        self.assertGreaterEqual(result["authenticated_count"], 1)

    def test_manage_session_clear_cache(self):
        result = asyncio.run(manage_session(action="clear_cache"))
        self.assertTrue(result["success"])

    def test_search_jobs_single_connector(self):
        # Greenhouse is universally searchable without cookies
        result = asyncio.run(search_jobs(connector="greenhouse", query="Engineer", limit=5))
        self.assertIn("jobs", result)
        self.assertEqual(result.get("platform"), "greenhouse")

    def test_manage_taxonomy_lookup(self):
        result = asyncio.run(manage_taxonomy(connector="foundit", type="skills", query="Python", limit=5))
        self.assertIn(result.get("status_code"), [200, None])
        self.assertTrue("items" in result or "suggestions" in result)

    def test_manage_job_pipeline_dry_run(self):
        # Test dry-run application
        result = asyncio.run(manage_job_pipeline(connector="hirist", action="apply", job_id="12345", dry_run=True))
        self.assertEqual(result.get("status"), "dry_run_success")


if __name__ == "__main__":
    unittest.main()
