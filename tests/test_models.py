"""
Unit tests for OmniJob MCP Normalized Models.
"""
import unittest
from omnijob_mcp.core.models import (
    JobItem,
    JobDetail,
    CandidateProfile,
    ApplicationResult,
    ConnectorHealth,
)


class TestNormalizedModels(unittest.TestCase):
    def test_job_item(self):
        item = JobItem(
            id="12345",
            platform="foundit",
            title="Senior Python Engineer",
            company="Aeologic Technologies",
            location="Pune",
            experience="3-6 Yrs",
            salary="15-20 LPA",
            skills=["Python", "FastAPI", "PostgreSQL"],
        )
        self.assertEqual(item.id, "12345")
        self.assertEqual(item.platform, "foundit")
        self.assertTrue(item.is_easy_apply)
        dump = item.model_dump()
        self.assertEqual(dump["company"], "Aeologic Technologies")

    def test_job_detail(self):
        detail = JobDetail(
            id="gh-101",
            platform="greenhouse",
            title="DevOps Lead",
            company="Cloudflare",
            location="Remote",
            description="We are seeking an experienced engineer...",
            skills=["Terraform", "Kubernetes"],
            can_apply=True,
        )
        self.assertEqual(detail.platform, "greenhouse")
        self.assertTrue(detail.can_apply)

    def test_candidate_profile(self):
        prof = CandidateProfile(
            platform="naukri",
            name="Prasad Rawas",
            email="contactprasadrawas@gmail.com",
            location="Pune",
            skills=["Python", "FastMCP", "Docker"],
        )
        self.assertEqual(prof.name, "Prasad Rawas")
        self.assertEqual(len(prof.skills), 3)

    def test_application_result(self):
        res = ApplicationResult(
            platform="hirist",
            job_id="998877",
            status="applied",
            message="Application submitted successfully",
        )
        self.assertEqual(res.status, "applied")

    def test_connector_health(self):
        health = ConnectorHealth(
            connector="wellfound",
            display_name="Wellfound (AngelList)",
            status="authenticated",
            supported_features=["search", "apply"],
            details={"has_cookie": True},
        )
        self.assertEqual(health.status, "authenticated")


if __name__ == "__main__":
    unittest.main()
