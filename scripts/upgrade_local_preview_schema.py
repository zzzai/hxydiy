"""补齐无 Alembic 版本标记的本地预览 SQLite；严禁用于生产。"""

from pathlib import Path
import sys

sys.path.insert(0, str(Path(__file__).resolve().parents[1]))

from sqlalchemy import inspect, text

from app.core.config import settings
from app.db.session import Base, engine
import app.models  # noqa: F401


def upgrade() -> None:
    if settings.environment == "production" or not settings.database_url.startswith("sqlite"):
        raise RuntimeError("本脚本只能用于非生产 SQLite 预览数据库")

    Base.metadata.create_all(engine)
    columns = {column["name"] for column in inspect(engine).get_columns("projects")}
    statements = {
        "detail_modules": "ALTER TABLE projects ADD COLUMN detail_modules JSON NOT NULL DEFAULT '[]'",
        "diy_options": "ALTER TABLE projects ADD COLUMN diy_options JSON NOT NULL DEFAULT '[]'",
        "display_order": "ALTER TABLE projects ADD COLUMN display_order INTEGER NOT NULL DEFAULT 0",
    }
    with engine.begin() as connection:
        for name, statement in statements.items():
            if name not in columns:
                connection.execute(text(statement))
    print("LOCAL_SCHEMA_READY")


if __name__ == "__main__":
    upgrade()
