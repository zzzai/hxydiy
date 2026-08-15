import unittest
from pathlib import Path
from tempfile import TemporaryDirectory

from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.release_static import mount_release_static_files


class ReleaseStaticFilesTests(unittest.TestCase):
    def test_serves_customer_root_and_admin_from_one_release(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            customer = release / "diy-web" / "dist"
            admin = release / "admin-react" / "dist"
            customer.mkdir(parents=True)
            admin.mkdir(parents=True)
            (customer / "index.html").write_text("customer app", encoding="utf-8")
            (admin / "index.html").write_text("staff app", encoding="utf-8")

            app = FastAPI()
            mount_release_static_files(app, release)
            client = TestClient(app)

            self.assertEqual(client.get("/").text, "customer app")
            self.assertEqual(client.get("/admin/").text, "staff app")

    def test_does_not_mount_when_release_builds_are_missing(self):
        with TemporaryDirectory() as directory:
            app = FastAPI()

            mounted = mount_release_static_files(app, Path(directory))

            self.assertFalse(mounted)


if __name__ == "__main__":
    unittest.main()
