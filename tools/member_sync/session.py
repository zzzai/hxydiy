"""Own one ephemeral Chrome session through a private pipe; accept fixed read-only requests."""
import argparse
import contextlib
from datetime import datetime, timezone
import json
import os
from pathlib import Path
import subprocess
import sys
import time
import uuid

import runner
from contracts import Stop
from collector import Collector, HOST

START_URL = "https://" + HOST + "/shair/components/shair-web/base-system/index.html"


def validate_request(value, package_sha):
    if (not isinstance(value, dict) or set(value) != {"id", "action", "package_sha256"}
            or value.get("action") != "controlled_sync"
            or value.get("package_sha256") != package_sha):
        raise Stop("invalid_local_request")
    try:
        if str(uuid.UUID(value["id"])) != value["id"]:
            raise ValueError()
    except (ValueError, TypeError, KeyError, AttributeError):
        raise Stop("invalid_local_request") from None
    return value["id"]


def request(root, package_sha):
    with runner.single_instance(root, "request.lock") as owned:
        if not owned:
            return {"status": "request_busy", "business_writes": 0}
        path = root / "request.json"
        if path.exists():
            value = json.loads(path.read_text(encoding="utf-8"))
            ident = validate_request(value, package_sha)
        else:
            ident = str(uuid.uuid4())
            runner.save(path, {"id": ident, "action": "controlled_sync", "package_sha256": package_sha})
        return {"status": "requested", "request_id": ident, "business_writes": 0, "model_calls": 0}


def status(root, package_sha, state):
    runner.save(root / "owner-status.json", {"state": state, "pid": os.getpid(),
                "updated_at_utc": runner.utc(), "package_sha256": package_sha,
                "mode": "controlled_membership_and_finance", "apply_enabled": True, "model_calls": 0})


def serve(root, package_sha, page, owner_held=False):
    # This function also accepts the already signed-in, manually verified pilot page.
    # Authentication remains only inside Chrome; no cookies or storage are exported.
    with (contextlib.nullcontext(True) if owner_held else runner.single_instance(root, "owner.lock")) as owned:
        if not owned:
            return {"status": "owner_exists"}
        page.set_default_timeout(15000)
        last_heartbeat = 0
        status(root, package_sha, "ready")
        while not page.is_closed():
            if time.monotonic() - last_heartbeat >= 20:
                status(root, package_sha, "waiting")
                last_heartbeat = time.monotonic()
            stop = root / "owner-stop.json"
            if stop.exists():
                value = json.loads(stop.read_bytes())
                if value == {"package_sha256": package_sha, "action": "handoff"}:
                    stop.unlink()
                    status(root, package_sha, "handoff")
                    return {"status": "handoff", "business_writes": 0}
                raise Stop("invalid_owner_handoff")
            path = root / "request.json"
            if path.exists():
                with runner.single_instance(root, "request.lock") as request_owned:
                    if not request_owned:
                        time.sleep(0.25)
                        continue
                    try:
                        value = json.loads(path.read_text(encoding="utf-8"))
                        ident = validate_request(value, package_sha)
                    except Exception:
                        def invalid():
                            raise Stop("invalid_local_request")
                        runner.run(root, lambda _: None, probe_fn=invalid)
                        status(root, package_sha, "blocked")
                        return {"status": "blocked"}
                    path.unlink()
                status(root, package_sha, "collecting")
                with runner.single_instance(root) as run_owned:
                    if run_owned:
                        check_runtime(root, package_sha)
                        from finance_schedule import scheduled_sync
                        report = scheduled_sync(root, page)
                    else:
                        report = {"status": "already_running", "business_writes": 0}
                runner.save(root / "request-result.json", {"request_id": ident, "report": report})
                status(root, package_sha, "blocked" if report["status"].startswith("blocked") else "ready")
                last_heartbeat = time.monotonic()
            page.wait_for_timeout(500)
        def closed():
            raise Stop("source_browser_closed")
        report = runner.run(root, lambda _: None, probe_fn=closed)
        status(root, package_sha, "closed")
        return report


def check_runtime(root, package_sha):
    if not root.is_dir() or root.is_symlink() or any((p / ".git").exists() for p in [root, *root.parents]):
        raise Stop("private_root_invalid")
    if not runner.package_valid(package_sha):
        raise Stop("package_integrity_failed")
    if os.name == "nt":
        checked = subprocess.run(["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
            str(runner.HERE / "check-private-root.ps1"), "-PrivateRoot", str(root)],
            capture_output=True, timeout=15, creationflags=0x08000000)
        if checked.returncode:
            raise Stop("private_root_permissions")
    elif root.stat().st_mode & 0o077:
        raise Stop("private_root_permissions")


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--serve", action="store_true")
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve()
    check_runtime(root, args.package_sha256)
    if not args.serve:
        result = request(root, args.package_sha256)
        with runner.single_instance(root, "owner.lock") as missing:
            if missing:
                # A fresh browser always needs normal manual sign-in. No existing profile is read.
                subprocess.Popen([sys.executable, "-B", str(Path(__file__).resolve()),
                    "--root", str(root), "--package-sha256", args.package_sha256, "--serve"],
                    stdin=subprocess.DEVNULL, stdout=subprocess.DEVNULL, stderr=subprocess.DEVNULL,
                    creationflags=0x08000000 if os.name == "nt" else 0)
        print(json.dumps(result))
        return 0
    from playwright.sync_api import sync_playwright
    with runner.single_instance(root, "owner.lock") as owned:
        if not owned:
            return 0
        with sync_playwright() as pw:
            browser = None
            try:
                browser = pw.chromium.launch(channel="chrome", headless=False, chromium_sandbox=True, args=["--start-minimized"])
                context = browser.new_context(accept_downloads=False)
                page = context.new_page()
                page.goto(START_URL, wait_until="domcontentloaded", timeout=30000)
                serve(root, args.package_sha256, page, owner_held=True)
            except Exception:
                def failed():
                    raise Stop("browser_owner_failed")
                runner.run(root, lambda _: None, probe_fn=failed)
                status(root, args.package_sha256, "failed")
            finally:
                if browser is not None:
                    browser.close()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
