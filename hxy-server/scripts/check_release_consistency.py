"""Read-only consistency check for the DIY selection-closure release.

This script compares source/build markers only. It never starts services,
connects to a database, or writes to either tree.
"""

from dataclasses import dataclass
from pathlib import Path
import argparse


@dataclass(frozen=True)
class ConsistencyReport:
    ok: bool
    missing: tuple[str, ...]


CAPABILITIES = {
    "workspace_backend": (
        ("hxy-server/app/api/selections.py", ("/revisions",)),
        ("hxy-server/app/api/admin_v2.py", ("selection-change-requests",)),
        ("hxy-server/scripts/migrate_catalog_options.py", ("migrate_store_catalog", "--apply")),
    ),
    "workspace_customer_web": (
        ("diy-web/src/api.ts", ("/revisions",)),
    ),
    "workspace_admin_web": (
        ("admin-react/src/api.ts", ("selection-change-requests",)),
    ),
    "production_customer_web": (
        ("diy-web/dist", ("/revisions",)),
    ),
    "production_admin_web": (
        ("admin-react/dist", ("selection-change-requests",)),
    ),
    "production_api": (
        ("hxy-server/app/api/selections.py", ("/revisions",)),
        ("hxy-server/app/api/admin_v2.py", ("selection-change-requests",)),
        ("hxy-server/scripts/migrate_catalog_options.py", ("migrate_store_catalog", "--apply")),
    ),
}


def _matches(root: Path, checks: tuple[tuple[str, tuple[str, ...]], ...]) -> bool:
    for relative, markers in checks:
        path = root / relative
        candidates = path.rglob("*") if path.is_dir() else (path,)
        files = [candidate for candidate in candidates if candidate.is_file()]
        if not files:
            return False
        contents = "\n".join(candidate.read_text(encoding="utf-8", errors="ignore") for candidate in files)
        if any(marker not in contents for marker in markers):
            return False
    return True


def check_release_consistency(workspace: Path, production: Path) -> ConsistencyReport:
    production_root = production / "current" if (production / "current").is_dir() else production
    missing: list[str] = []
    for name in ("workspace_backend", "workspace_customer_web", "workspace_admin_web"):
        if not _matches(workspace, CAPABILITIES[name]):
            missing.append(name)
    for name in ("production_api", "production_customer_web", "production_admin_web"):
        if not _matches(production_root, CAPABILITIES[name]):
            missing.append(name)
    return ConsistencyReport(ok=not missing, missing=tuple(missing))


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--workspace", type=Path, default=Path("/root/hxy-workspace"))
    parser.add_argument("--production", type=Path, default=Path("/root/hxy-diy-20260811"))
    args = parser.parse_args()
    report = check_release_consistency(args.workspace, args.production)
    if report.ok:
        print("release consistency verified")
        return
    print("release consistency failed")
    for item in report.missing:
        print(f"missing: {item}")
    raise SystemExit(1)


if __name__ == "__main__":
    main()
