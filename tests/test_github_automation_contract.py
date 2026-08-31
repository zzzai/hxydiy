"""Static contracts for the repository-owned PR review and production release gates.

GitHub Actions configuration is executable production infrastructure.  These
tests keep its security and rollback guarantees visible without needing GitHub
credentials or a production server.
"""

from pathlib import Path
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def workflow(name: str) -> str:
    return (REPO_ROOT / ".github" / "workflows" / name).read_text(encoding="utf-8")


class GitHubAutomationContractTests(unittest.TestCase):
    def test_ai_review_is_isolated_from_untrusted_pr_code_and_never_auto_approves(self):
        content = workflow("ai-pr-review.yml")

        self.assertIn("pull_request_target:", content)
        self.assertIn("pull-requests: write", content)
        self.assertIn("OPENAI_API_KEY", content)
        self.assertIn("REQUEST_CHANGES", content)
        self.assertNotIn("actions/checkout", content)
        self.assertNotIn("event: APPROVE", content)

    def test_production_workflow_requires_environment_gate_and_pinned_host_identity(self):
        content = workflow("deploy-production.yml")

        self.assertIn("workflow_run:", content)
        self.assertIn('workflows: ["CI"]', content)
        self.assertIn("environment: production", content)
        self.assertIn("PRODUCTION_SSH_KNOWN_HOSTS", content)
        self.assertIn("deploy-production.sh", content)
        self.assertIn("concurrency:", content)

    def test_ci_fetches_the_pr_base_before_comparing_whitespace(self):
        content = workflow("ci.yml")

        self.assertIn("fetch-depth: 0", content)
        self.assertIn('git diff --check "$BASE_SHA" "$GITHUB_SHA"', content)

    def test_remote_release_script_backs_up_verifies_and_rolls_back(self):
        script = (REPO_ROOT / "deploy" / "diy" / "deploy-production.sh").read_text(encoding="utf-8")

        self.assertIn("pg_dump", script)
        self.assertIn("sha256sum -c", script)
        self.assertIn("activate-release.sh", script)
        self.assertIn("rollback", script)
        self.assertIn("curl -fsS", script)
        self.assertIn("rehearsal", script)


if __name__ == "__main__":
    unittest.main()
