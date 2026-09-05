"""Static contracts for the repository-owned three-window project memory."""

from pathlib import Path
import subprocess
import unittest


REPO_ROOT = Path(__file__).resolve().parents[1]


def read(relative: str) -> str:
    return (REPO_ROOT / relative).read_text(encoding="utf-8")


class ProjectMemoryContractTests(unittest.TestCase):
    def test_core_memory_files_are_tracked_and_define_authority(self):
        paths = (
            "docs/CONTEXT-MANIFEST.md",
            "docs/CURRENT-STATE.md",
            "docs/TEAM-MEMORY.md",
        )
        tracked = set(
            subprocess.check_output(
                ["git", "ls-files"], cwd=REPO_ROOT, text=True, encoding="utf-8"
            ).splitlines()
        )
        for relative in paths:
            self.assertTrue((REPO_ROOT / relative).is_file(), relative)
            self.assertIn(relative, tracked)

        manifest = read("docs/CONTEXT-MANIFEST.md")
        self.assertIn("origin/main", manifest)
        self.assertIn("生产服务器", manifest)

    def test_current_state_matches_verified_production(self):
        current = read("docs/CURRENT-STATE.md")
        self.assertIn("manual-2c3793ea3b95-20260905-1", current)
        self.assertIn("hxy-diy-api:2c3793e", current)
        self.assertIn("2ad2123696c2e5166e837c524b2a8635053793e9097a9fae1865933f7be44c7f", current)
        self.assertIn("20260904_service_reference_v2", current)

    def test_team_memory_uses_the_versioned_service_reference_contract(self):
        memory = read("docs/TEAM-MEMORY.md")
        contract = read("docs/contracts/service-reference-v1.md")
        self.assertIn("service_reference_v1", memory)
        self.assertNotIn("第一屏填写年龄段、性别、体型、职业场景", memory)
        for code in ("neck_shoulder", "gentle", "higher", "adjust_next_time", "repeat_current"):
            self.assertIn(code, contract)
        self.assertIn("不得自动转换为普通运营标签", contract)

    def test_each_window_has_a_bounded_workstream_and_prompt(self):
        prompts = read("docs/AI-WINDOW-PROMPTS.md")
        for name in ("customer", "admin", "technician"):
            self.assertTrue((REPO_ROOT / f"docs/workstreams/{name}.md").is_file())
        for heading in ("顾客端窗口", "管理端窗口", "技师端窗口"):
            self.assertIn(heading, prompts)
        self.assertIn("git fetch origin", prompts)
        self.assertIn("docs/CURRENT-STATE.md", prompts)

    def test_root_instructions_require_shared_memory_updates(self):
        instructions = read("AGENTS.md")
        self.assertIn("docs/CONTEXT-MANIFEST.md", instructions)
        self.assertIn("跨端契约", instructions)
        self.assertIn("同一个 PR", instructions)


if __name__ == "__main__":
    unittest.main()
