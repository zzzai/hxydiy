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
        self.assertIn("main-bf0bddf-20260905-1", current)
        self.assertIn("hxy-diy-api:bf0bddf", current)
        self.assertIn("20260904_service_reference_v2", current)

    def test_team_memory_uses_the_versioned_service_reference_contract(self):
        memory = read("docs/TEAM-MEMORY.md")
        self.assertIn("service_reference_v1", memory)
        self.assertNotIn("第一屏填写年龄段、性别、体型、职业场景", memory)


if __name__ == "__main__":
    unittest.main()
