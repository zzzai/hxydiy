"""Zero-model scheduled read-only runner. There is intentionally no apply command."""
import argparse
from contextlib import contextmanager
from datetime import datetime, timezone
import hashlib
import json
import os
import re
from pathlib import Path
import subprocess
import sys
import tempfile
import uuid

HERE = Path(__file__).resolve().parent
BUSINESS_WRITES = 0


def utc():
    return datetime.now(timezone.utc).isoformat()


def save(path, value):
    path = Path(path)
    payload = (json.dumps(value, ensure_ascii=False, sort_keys=True, indent=2) + "\n").encode()
    fd, temporary = tempfile.mkstemp(prefix=".pending-", dir=path.parent)
    try:
        with os.fdopen(fd, "wb") as stream:
            stream.write(payload)
            stream.flush()
            os.fsync(stream.fileno())
        os.replace(temporary, path)
    finally:
        if os.path.exists(temporary):
            os.unlink(temporary)


def package_valid(expected):
    manifest = HERE / "package-manifest.json"
    if not manifest.is_file() or hashlib.sha256(manifest.read_bytes()).hexdigest() != expected:
        return False
    try:
        entries = json.loads(manifest.read_text(encoding="utf-8"))
    except (ValueError, OSError):
        return False
    if not isinstance(entries, dict):
        return False
    required = {"runner.py", "contracts.py", "collector.py", "probe_existing.py", "notify.ps1", "check-private-root.ps1"}
    if not required.issubset(entries):
        return False
    for name, sha in entries.items():
        if Path(name).name != name or not (HERE / name).is_file():
            return False
        if hashlib.sha256((HERE / name).read_bytes()).hexdigest() != sha:
            return False
    return True


@contextmanager
def single_instance(root):
    lock = (root / "runner.lock").open("a+b")
    try:
        lock.seek(0)
        if os.name == "nt":
            import msvcrt
            if os.fstat(lock.fileno()).st_size == 0:
                lock.write(b"0")
                lock.flush()
            lock.seek(0)
            msvcrt.locking(lock.fileno(), msvcrt.LK_NBLCK, 1)
        else:
            import fcntl
            fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except OSError:
        lock.close()
        yield False
        return
    try:
        yield True
    finally:
        lock.close()


def probe():
    # Fixed host/container/query; no shell constructed from any source member data.
    result = subprocess.run(
        ["ssh", "-o", "BatchMode=yes", "-o", "ConnectTimeout=10", "hxy",
         "cd /root/hxy-diy-20260811 && docker exec -i --env PYTHONPATH=/app hxy-diy-api python -B -"],
        input=(HERE / "probe_existing.py").read_bytes(), capture_output=True, timeout=35)
    if result.returncode:
        from contracts import Stop
        raise Stop("production_readonly_probe_failed")
    return json.loads(result.stdout)


def notify(root):
    if os.name != "nt":
        return "unsupported_platform"
    try:
        completed = subprocess.run(
            ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
             str(HERE / "notify.ps1"), "-ReportPath", str(root / "report.json")],
            capture_output=True, timeout=20, creationflags=0x08000000)
        return "desktop_notification_requested" if completed.returncode == 0 else "notification_failed"
    except (OSError, subprocess.TimeoutExpired):
        return "notification_failed"


def run(root, collect_fn, probe_fn=probe, notify_fn=notify):
    from contracts import Stop, index_keys, verify
    state_path = root / "state.json"
    state_error = False
    if state_path.exists():
        try:
            state = json.loads(state_path.read_text(encoding="utf-8"))
            if not isinstance(state, dict) or type(state.get("blocked")) is not bool:
                raise ValueError("invalid_state")
            if state["blocked"]:
                # An unresolved exception never auto-resumes or repeatedly notifies.
                return {"status": "blocked_latched", "business_writes": 0}
        except (ValueError, OSError):
            state_error = True
    run_id = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ-") + uuid.uuid4().hex[:8]
    directory = root / "runs" / run_id
    directory.mkdir(parents=True, mode=0o700)
    try:
        if state_error:
            raise Stop("state_unreadable")
        index = probe_fn()
        known = index_keys(index, datetime.now(timezone.utc))
        evidence = collect_fn(known)
        # Only newly observed cards retain full phones; existing-card amounts are not exported.
        outcome = verify(index, evidence)
        reduced = json.loads(json.dumps(evidence))
        from contracts import source_key
        for scan in reduced:
            for page in scan["pages"]:
                page["rows"] = [r if source_key(r["card_number"]) not in known else
                                {"card_number": r["card_number"], "store_name": r["store_name"],
                                 "allow_cross_store_text": r["allow_cross_store_text"],
                                 "state_text": r["state_text"]} for r in page["rows"]]
        # Bind the retained evidence hash, not a discarded larger object.
        from contracts import digest
        outcome["source_evidence_sha256"] = digest(reduced)
        save(directory / "source-private.json", reduced)
        save(directory / "index-private.json", index)
        save(directory / "candidates-private.json", outcome)
        report = {k: v for k, v in outcome.items() if k != "candidates"}
        report.update(run_id=run_id, completed_at_utc=utc(), model_calls=0,
                      next_step="readonly_acceptance_required" if outcome["new_cards"] else "none")
        save(directory / "report.json", report)
        save(root / "report.json", report)
        save(state_path, {"blocked": False, "last_success": run_id, "mode": "readonly",
                          "apply_enabled": False})
        return report
    except Exception as exc:
        code = str(exc) if isinstance(exc, Stop) else "unexpected_runtime_error"
        # Error text from browser/SQL may contain personal data; never persist it.
        report = {"status": "blocked", "code": code, "run_id": run_id,
                  "completed_at_utc": utc(), "business_writes": 0, "apply_enabled": False,
                  "model_calls": 0, "exception_type": type(exc).__name__}
        save(directory / "report.json", report)
        save(root / "report.json", report)
        save(state_path, {"blocked": True, "code": code, "run_id": run_id, "mode": "readonly"})
        try:
            report["notification"] = notify_fn(root)
        except Exception:
            report["notification"] = "notification_failed"
        save(directory / "report.json", report)
        save(root / "report.json", report)
        return report


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--root", type=Path, required=True)
    parser.add_argument("--package-sha256", required=True)
    parser.add_argument("--acknowledge-run")
    args = parser.parse_args()
    os.umask(0o077)
    root = args.root.resolve()
    if not root.is_dir() or args.root.is_symlink():
        parser.error("private_root_must_exist")
    if any((p / ".git").exists() for p in [root, *root.parents]):
        parser.error("private_root_must_be_outside_git")
    if os.name != "nt" and root.stat().st_mode & 0o077:
        parser.error("private_root_permissions")
    if not package_valid(args.package_sha256):
        print(json.dumps({"status": "blocked", "code": "package_integrity_failed", "business_writes": 0}))
        return 2
    with single_instance(root) as owned:
        if not owned:
            print('{"status":"already_running","business_writes":0}')
            return 0
        if args.acknowledge_run:
            if not re.fullmatch(r"[0-9]{8}T[0-9]{6}Z-[a-f0-9]{8}", args.acknowledge_run):
                parser.error("invalid_acknowledgement_id")
            path = root / "state.json"
            state = json.loads(path.read_text(encoding="utf-8"))
            if not state.get("blocked") or state.get("run_id") != args.acknowledge_run:
                parser.error("exact_blocked_run_required")
            save(root / ("ack-" + args.acknowledge_run + ".json"),
                 {"run_id": args.acknowledge_run, "acknowledged_at_utc": utc()})
            # Keep the original exception record, and require a separate run to retry.
            save(path, {"blocked": False, "mode": "readonly", "apply_enabled": False})
            return 0
        if os.name == "nt":
            checked = subprocess.run(
                ["powershell.exe", "-NoProfile", "-NonInteractive", "-File",
                 str(HERE / "check-private-root.ps1"), "-PrivateRoot", str(root)],
                capture_output=True, timeout=15, creationflags=0x08000000)
            if checked.returncode:
                from contracts import Stop
                def fail_private_root():
                    raise Stop("private_root_permissions")
                result = run(root, lambda _: None, probe_fn=fail_private_root)
                print(json.dumps(result))
                return 2
        from collector import collect
        result = run(root, collect)
        print(json.dumps(result, ensure_ascii=False, sort_keys=True))
        return 2 if result["status"] in {"blocked", "blocked_latched"} else 0


if __name__ == "__main__":
    raise SystemExit(main())
