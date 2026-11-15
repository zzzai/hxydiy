"""Package a clean, exact source revision for a separate read-only workstation runner."""
import argparse
import hashlib
import json
from pathlib import Path
import subprocess
import zipfile

FILES = ["runner.py", "contracts.py", "collector.py", "probe_existing.py", "session.py", "bridge.py",
         "notify.ps1", "check-private-root.ps1", "install-readonly-task.ps1", "requirements.txt", "README.md"]


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--output", type=Path, required=True)
    parser.add_argument("--expected-head", required=True)
    parser.add_argument("--server-runtime", type=Path, required=True)
    args = parser.parse_args()
    root = Path(__file__).resolve().parents[2]
    head = subprocess.check_output(["git", "rev-parse", "HEAD"], cwd=root, text=True).strip()
    if head != args.expected_head or subprocess.check_output(["git", "status", "--porcelain"], cwd=root):
        raise SystemExit("clean_exact_revision_required")
    output = args.output.resolve()
    if output == root or root in output.parents:
        raise SystemExit("output_must_be_outside_repository")
    output.mkdir(parents=True, exist_ok=True, mode=0o700)
    source = Path(__file__).resolve().parent
    files = {name: (source / name).read_bytes() for name in FILES}
    files["server-runtime.json"] = args.server_runtime.read_bytes()
    manifest = (json.dumps({name: hashlib.sha256(content).hexdigest() for name, content in files.items()},
                           sort_keys=True, indent=2) + "\n").encode()
    manifest_sha = hashlib.sha256(manifest).hexdigest()
    archive = output / ("member-sync-readonly-" + head[:12] + ".zip")
    with zipfile.ZipFile(archive, "x", compression=zipfile.ZIP_DEFLATED) as z:
        for name, content in files.items():
            z.writestr("member_sync/" + name, content)
        z.writestr("member_sync/package-manifest.json", manifest)
    receipt = {"source_revision": head, "archive": archive.name, "mode": "controlled_additive",
               "archive_sha256": hashlib.sha256(archive.read_bytes()).hexdigest(),
               "package_manifest_sha256": manifest_sha, "apply_enabled": True,
               "scheduled_task_installed": False}
    (output / "package-receipt.json").write_text(json.dumps(receipt, indent=2) + "\n", encoding="utf-8")
    print(json.dumps(receipt))


if __name__ == "__main__":
    main()
