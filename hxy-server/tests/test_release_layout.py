import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.release_static import mount_release_static_files


REPO_ROOT = Path(__file__).resolve().parents[2]


class ReleaseLayoutTests(unittest.TestCase):
    def test_api_builds_from_the_current_single_release_directory(self):
        compose = (REPO_ROOT / "deploy/diy/docker-compose.hxy.yml").read_text(encoding="utf-8")

        self.assertIn("context: ${HXY_DIY_CURRENT:-../../current}", compose)
        self.assertIn("dockerfile: deploy/diy/Dockerfile.release", compose)

    def test_api_serves_customer_and_staff_apps_from_one_release(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            customer = release / "diy-web" / "dist"
            admin = release / "admin-react" / "dist"
            customer.mkdir(parents=True)
            admin.mkdir(parents=True)
            (customer / "index.html").write_text("customer-app", encoding="utf-8")
            (admin / "index.html").write_text("admin-app", encoding="utf-8")
            app = FastAPI()

            self.assertTrue(mount_release_static_files(app, release))

            with TestClient(app) as client:
                self.assertEqual(client.get("/").text, "customer-app")
                self.assertEqual(client.get("/admin/").text, "admin-app")
                self.assertEqual(client.get("/technician/").text, "admin-app")


if __name__ == "__main__":
    unittest.main()
