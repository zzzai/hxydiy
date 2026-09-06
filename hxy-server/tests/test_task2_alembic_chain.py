import shutil
import subprocess
import tempfile
import unittest
from pathlib import Path

from alembic.config import Config
from alembic.script import ScriptDirectory


class Task2AlembicChainTests(unittest.TestCase):
    def test_tracked_migrations_form_a_single_history_to_latest_head(self):
        """已跟踪迁移应形成唯一、连续且可发布的升级历史。"""
        root = Path(__file__).resolve().parents[1]
        tracked = subprocess.run(
            ["git", "ls-files", "alembic/versions"], cwd=root,
            check=True, capture_output=True, text=True,
        ).stdout.splitlines()
        with tempfile.TemporaryDirectory() as directory:
            migration_dir = Path(directory) / "alembic" / "versions"
            migration_dir.mkdir(parents=True)
            for relative_path in tracked:
                source = root / relative_path
                shutil.copy2(source, migration_dir / source.name)
            config = Config()
            config.set_main_option("script_location", str(migration_dir.parent))
            scripts = ScriptDirectory.from_config(config)
            self.assertEqual(scripts.get_heads(), ["20260905_tech_history_v3"])
            self.assertIn(
                "20260815_member_grants",
                {revision.revision for revision in scripts.walk_revisions()},
            )


if __name__ == "__main__":
    unittest.main()
