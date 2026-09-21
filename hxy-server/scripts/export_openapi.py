import json
from pathlib import Path
import sys

OUTPUT_PATH = Path(__file__).resolve().parents[1] / "openapi.json"
sys.path.insert(0, str(OUTPUT_PATH.parent))

from app.main import app  # noqa: E402


def main() -> None:
    content = json.dumps(app.openapi(), ensure_ascii=False, indent=2, sort_keys=True) + "\n"
    OUTPUT_PATH.write_text(content, encoding="utf-8", newline="\n")


if __name__ == "__main__":
    main()
