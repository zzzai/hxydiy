"""Read-only package checks. Never imports data or enables the feature."""
import argparse
import json
from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))
from app.domain.learning_content import load_package


def main():
    parser = argparse.ArgumentParser()
    parser.add_argument("--production", action="store_true")
    args = parser.parse_args()
    folder = Path(__file__).resolve().parents[1] / "content/staff-learning"
    manifest, courses, approved = load_package(folder / ("production-manifest.json" if args.production else "manifest.json"))
    print(json.dumps({"content_integrity_passed": True, "courses": len(courses),
        "questions": sum(len(c["questions"]) for c in courses), "content_sha256": manifest["content_sha256"],
        "production_content_ready": approved, "database_writes": 0}))
    return 0 if approved or not args.production else 2


if __name__ == "__main__":
    sys.exit(main())
