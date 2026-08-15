"""Serve both DIY web applications from one immutable release directory."""

from pathlib import Path

from fastapi import FastAPI
from fastapi.staticfiles import StaticFiles


def mount_release_static_files(app: FastAPI, release_root: Path | None = None) -> bool:
    root = release_root or Path("/app")
    customer = root / "diy-web" / "dist"
    admin = root / "admin-react" / "dist"
    if not (customer / "index.html").is_file() or not (admin / "index.html").is_file():
        return False
    app.mount("/admin", StaticFiles(directory=admin, html=True), name="diy-admin")
    app.mount("/", StaticFiles(directory=customer, html=True), name="diy-customer")
    return True
