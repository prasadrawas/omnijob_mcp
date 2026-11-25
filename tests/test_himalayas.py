"""
Unit & Integration Tests for Himalayas Connector in OmniJob MCP.
"""
import unittest
from omnijob_mcp.connectors.himalayas import auth
from omnijob_mcp.connectors.himalayas.connector import HimalayasConnector
from omnijob_mcp.connectors.himalayas.client import HimalayasClient


class TestHimalayasConnector(unittest.TestCase):
    def setUp(self):
        self.connector = HimalayasConnector()
        self.client = HimalayasClient()

    def test_connector_metadata(self):
        self.assertEqual(self.connector.name, "himalayas")
        self.assertEqual(self.connector.display_name, "Himalayas Remote")
        self.assertIn("search", self.connector.supported_features)
        self.assertIn("job_details", self.connector.supported_features)
        self.assertIn("profile", self.connector.supported_features)
        self.assertIn("applied_jobs", self.connector.supported_features)
        self.assertIn("account", self.connector.supported_features)
        self.assertIn("taxonomy", self.connector.supported_features)

    def test_authentication_status(self):
        status = self.connector.get_session_status()
        self.assertIsInstance(status, dict)
        self.assertIn("authenticated", status)
        self.assertTrue(status.get("authenticated"))
        self.assertEqual(status.get("first_name"), "Prasad")
        self.assertEqual(status.get("last_name"), "Rawas")
        self.assertIn("@prasadrawas", status.get("talent_handle", ""))

    def test_taxonomy_lookup(self):
        res = self.connector.lookup_taxonomy(type_name="skills", query="FastAPI")
        self.assertIsInstance(res, dict)
        self.assertEqual(res.get("platform"), "himalayas")
        suggestions = [s["name"] for s in res.get("suggestions", [])]
        self.assertIn("FastAPI", suggestions)

    def test_can_job_apply(self):
        res = self.connector.can_job_apply("canonical:lead-python-software-engineer")
        self.assertEqual(res.get("platform"), "himalayas")
        self.assertIn("can_apply", res)

    def test_live_search(self):
        res = self.connector.search_jobs(query="Python", limit=2)
        self.assertEqual(res.get("platform"), "himalayas")
        self.assertGreater(res.get("total", 0), 0)
        jobs = res.get("jobs", [])
        self.assertGreater(len(jobs), 0)
        first = jobs[0]
        self.assertIn("id", first)
        self.assertIn("title", first)
        self.assertIn("company", first)
        self.assertIn("apply_url", first)

    def test_live_profile(self):
        prof = self.connector.get_profile()
        self.assertEqual(prof.get("platform"), "himalayas")
        self.assertEqual(prof.get("name"), "Prasad Rawas")
        self.assertEqual(prof.get("handle"), "@prasadrawas")
        self.assertIn("Volox Innovations", prof.get("headline", ""))
        self.assertGreater(len(prof.get("employments", [])), 0)


if __name__ == "__main__":
    unittest.main()
