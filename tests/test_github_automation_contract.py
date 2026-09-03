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
    def test_ai_review_is_an_isolated_required_check_and_never_auto_approves(self):
        content = workflow("ai-pr-review.yml")

        self.assertIn("pull_request_target:", content)
        self.assertIn("pull-requests: write", content)
        self.assertIn("checks: write", content)
        self.assertIn("OPENAI_API_KEY", content)
        self.assertIn("github.rest.checks.create", content)
        self.assertIn("github.rest.checks.update", content)
        self.assertIn("AI PR Review", content)
        self.assertIn("blocking.length ? 'failure' : 'success'", content)
        self.assertNotIn("actions/checkout", content)
        self.assertNotIn("event: APPROVE", content)
        self.assertNotIn("REQUEST_CHANGES", content)

    def test_auto_merge_requires_all_checks_for_the_exact_head_sha(self):
        content = workflow("auto-merge.yml")

        self.assertIn("workflow_run:", content)
        self.assertIn('workflows: ["Trusted PR Gate"]', content)
        self.assertIn("branches: [main]", content)
        self.assertIn("github.event.workflow_run", content)
        self.assertIn("pr.head.sha", content)
        self.assertIn("github.rest.checks.listForRef", content)
        self.assertIn("Trusted PR Gate", content)
        self.assertNotIn("'AI PR Review',", content)
        self.assertIn("pr.head.repo.full_name !== `${owner}/${repo}`", content)
        self.assertIn("github.rest.pulls.merge", content)
        self.assertIn("sha: pr.head.sha", content)
        self.assertIn("merge_method: 'squash'", content)

    def test_trusted_gate_runs_pr_code_without_secrets_and_writes_a_head_check(self):
        content = workflow("trusted-pr-gate.yml")

        self.assertIn("pull_request_target:", content)
        self.assertIn("checks: write", content)
        self.assertIn("permissions:", content)
        self.assertIn("contents: read", content)
        self.assertIn("pull-requests: read", content)
        self.assertIn("persist-credentials: false", content)
        self.assertIn("refs/pull/${{ github.event.pull_request.number }}/merge", content)
        self.assertIn("github.rest.checks.create", content)
        self.assertIn("github.rest.checks.update", content)
        self.assertIn("name: Trusted PR Gate", content)
        self.assertIn("context.payload.pull_request.head.sha", content)
        self.assertIn("core.setFailed", content)
        self.assertIn("needs: [scope, static, admin, customer, backend]", content)
        self.assertIn("permissions:\n      contents: read\n      checks: write", content)
        self.assertIn("permissions:\n      contents: read\n      checks: none", content)

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
        self.assertIn('git diff-tree --no-commit-id --check -r "$GITHUB_SHA"', content)

    def test_remote_release_script_backs_up_verifies_and_rolls_back(self):
        script = (REPO_ROOT / "deploy" / "diy" / "deploy-production.sh").read_text(encoding="utf-8")

        self.assertIn("pg_dump", script)
        self.assertIn("sha256sum -c", script)
        self.assertIn("activate-release.sh", script)
        self.assertIn("rollback", script)
        self.assertIn("curl -fsS", script)
        self.assertIn("rehearsal", script)

    def test_release_boundaries_reject_symbolic_links(self):
        create = (REPO_ROOT / "deploy" / "diy" / "create-release.sh").read_text(encoding="utf-8")
        activate = (REPO_ROOT / "deploy" / "diy" / "activate-release.sh").read_text(encoding="utf-8")

        self.assertIn("find \"$workspace_root/$required\" -type l", create)
        self.assertIn("find \"$target\" -type l", activate)


if __name__ == "__main__":
    unittest.main()
