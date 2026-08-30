import unittest
import mimetypes
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

    def test_serves_technician_entry_and_nested_path_from_admin_bundle(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            customer = release / "diy-web" / "dist"
            admin = release / "admin-react" / "dist"
            customer.mkdir(parents=True)
            admin.mkdir(parents=True)
            (customer / "index.html").write_text("customer app", encoding="utf-8")
            (admin / "index.html").write_text("admin bundle", encoding="utf-8")

            app = FastAPI()
            mount_release_static_files(app, release)
            client = TestClient(app)

            self.assertEqual(client.get("/technician/").text, "admin bundle")
            self.assertEqual(client.get("/technician/today").text, "admin bundle")

    def test_serves_technician_entry_and_history_fallback_from_admin_bundle(self):
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

            self.assertEqual(client.get("/technician/").text, "staff app")
            self.assertEqual(client.get("/technician/today").text, "staff app")

    def test_html_is_not_cached_and_hashed_assets_are_immutable(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            customer = release / "diy-web" / "dist"
            admin = release / "admin-react" / "dist"
            assets = customer / "assets"
            customer.mkdir(parents=True)
            admin.mkdir(parents=True)
            assets.mkdir()
            (customer / "index.html").write_text("customer app", encoding="utf-8")
            (admin / "index.html").write_text("staff app", encoding="utf-8")
            (assets / "index-version.js").write_text("app", encoding="utf-8")

            app = FastAPI()
            mount_release_static_files(app, release)
            client = TestClient(app)

            customer_response = client.get("/")
            admin_response = client.get("/admin/")
            asset_response = client.get("/assets/index-version.js")

            self.assertEqual(
                customer_response.headers["cache-control"],
                "no-store, no-cache, must-revalidate",
            )
            self.assertEqual(
                admin_response.headers["cache-control"],
                "no-store, no-cache, must-revalidate",
            )
            self.assertEqual(
                asset_response.headers["cache-control"],
                "public, max-age=31536000, immutable",
            )

    def test_does_not_mount_when_release_builds_are_missing(self):
        with TemporaryDirectory() as directory:
            app = FastAPI()

            mounted = mount_release_static_files(app, Path(directory))

            self.assertFalse(mounted)

    def test_serves_webp_with_standard_image_content_type_when_os_mime_table_lacks_it(self):
        with TemporaryDirectory() as directory:
            release = Path(directory)
            customer = release / "diy-web" / "dist"
            admin = release / "admin-react" / "dist"
            customer.mkdir(parents=True)
            admin.mkdir(parents=True)
            (customer / "index.html").write_text("customer app", encoding="utf-8")
            (admin / "index.html").write_text("staff app", encoding="utf-8")
            (customer / "project.webp").write_bytes(b"webp-placeholder")

            previous_type = mimetypes.types_map.pop(".webp", None)
            previous_common_type = mimetypes.common_types.pop(".webp", None)
            try:
                app = FastAPI()
                mount_release_static_files(app, release)
                response = TestClient(app).get("/project.webp")
            finally:
                if previous_type is not None:
                    mimetypes.types_map[".webp"] = previous_type
                if previous_common_type is not None:
                    mimetypes.common_types[".webp"] = previous_common_type

            self.assertEqual(response.status_code, 200)
            self.assertEqual(response.headers["content-type"], "image/webp")


if __name__ == "__main__":
    unittest.main()
