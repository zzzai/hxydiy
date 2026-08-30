"""Serve both DIY web applications from one immutable release directory."""

import mimetypes
from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles
from starlette.exceptions import HTTPException
from starlette.responses import Response


class ReleaseStaticFiles(StaticFiles):
    async def get_response(self, path: str, scope: dict) -> Response:
        try:
            response = await super().get_response(path, scope)
        except HTTPException as exc:
            # BrowserRouter routes such as /technician/today do not map to a
            # physical file. Return the app shell for HTML navigation while
            # preserving real 404s for assets and API-like paths.
            if exc.status_code != 404 or "/assets/" in str(scope.get("path", "")):
                raise
            response = await super().get_response("index.html", scope)
        content_type = response.headers.get("content-type", "")
        if "text/html" in content_type:
            response.headers["Cache-Control"] = "no-store, no-cache, must-revalidate"
            response.headers["Pragma"] = "no-cache"
            response.headers["Expires"] = "0"
        elif "/assets/" in str(scope.get("path", "")):
            response.headers["Cache-Control"] = "public, max-age=31536000, immutable"
        return response


def mount_release_static_files(app: FastAPI, release_root: Path | None = None) -> bool:
    root = release_root or Path("/app")
    customer = root / "diy-web" / "dist"
    admin = root / "admin-react" / "dist"
    if not (customer / "index.html").is_file() or not (admin / "index.html").is_file():
        return False
    # Minimal Linux images may not ship a WebP MIME entry. Starlette otherwise
    # falls back to application/octet-stream for the customer-facing artwork.
    mimetypes.add_type("image/webp", ".webp")
    app.mount("/technician", ReleaseStaticFiles(directory=admin, html=True), name="diy-technician")
    app.mount("/admin", ReleaseStaticFiles(directory=admin, html=True), name="diy-admin")
    app.mount("/", ReleaseStaticFiles(directory=customer, html=True), name="diy-customer")
    return True
