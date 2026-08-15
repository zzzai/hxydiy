import unittest
from pathlib import Path


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseLayoutTests(unittest.TestCase):
    def test_api_builds_from_the_current_single_release_directory(self):
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        self.assertIn("context: ../../current", compose)
        self.assertIn("dockerfile: deploy/diy/Dockerfile.release", compose)

    def test_nginx_serves_customer_and_staff_apps_from_one_release(self):
        nginx = (REPO_ROOT / "deploy/diy/nginx-diy.conf").read_text(encoding="utf-8")

        self.assertIn("proxy_pass http://hxy-diy-api:8010;", nginx)
        self.assertNotIn("root /srv/hxy-diy", nginx)
        self.assertNotIn("alias /srv/hxy-diy", nginx)


if __name__ == "__main__":
    unittest.main()
