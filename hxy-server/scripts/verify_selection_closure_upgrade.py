"""Verify the additive DIY selection-closure schema after an Alembic upgrade.

Run this only against a copied database or a restored production backup before
releasing. It never changes data.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import create_engine, inspect, text

from app.core.config import settings


REQUIRED_TABLES = {
    "selection_revisions",
    "selection_change_requests",
    "service_lines",
}
REQUIRED_ADDON_COLUMNS = {
    "parent_project_id",
    "store_price_cents",
    "member_price_cents",
    "member_price_enabled",
    "independently_sellable",
    "can_attach_to_parent",
    "summary",
    "image_url",
    "display_order",
    "chargeable",
}


def main() -> None:
    engine = create_engine(settings.database_url)
    inspector = inspect(engine)
    tables = set(inspector.get_table_names())
    missing_tables = REQUIRED_TABLES - tables
    addon_columns = {column["name"] for column in inspector.get_columns("addons")}
    missing_columns = REQUIRED_ADDON_COLUMNS - addon_columns
    if missing_tables or missing_columns:
        raise SystemExit(
            f"schema verification failed: tables={sorted(missing_tables)} "
            f"addon_columns={sorted(missing_columns)}"
        )

    with engine.connect() as connection:
        legacy_sessions = connection.execute(text("SELECT COUNT(*) FROM selection_sessions")).scalar_one()
    print("selection closure schema verified")
    print(f"legacy selection_sessions readable: {legacy_sessions}")


if __name__ == "__main__":
    main()
