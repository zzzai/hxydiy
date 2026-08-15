import unittest

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import PageContent, Project, Room, Store
from scripts.bootstrap_diy_store import bootstrap_diy_store


class DiyBootstrapTests(unittest.TestCase):
    def test_bootstrap_creates_only_store_catalog_and_service_positions_idempotently(self):
        engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        Base.metadata.create_all(engine)
        SessionLocal = sessionmaker(bind=engine, expire_on_commit=False)

        with SessionLocal() as db:
            bootstrap_diy_store(db)
            first_counts = {
                "stores": db.scalar(select(func.count()).select_from(Store)),
                "projects": db.scalar(select(func.count()).select_from(Project)),
                "rooms": db.scalar(select(func.count()).select_from(Room)),
                "content": db.scalar(select(func.count()).select_from(PageContent)),
            }
            bootstrap_diy_store(db)
            second_counts = {
                "stores": db.scalar(select(func.count()).select_from(Store)),
                "projects": db.scalar(select(func.count()).select_from(Project)),
                "rooms": db.scalar(select(func.count()).select_from(Room)),
                "content": db.scalar(select(func.count()).select_from(PageContent)),
            }

        self.assertEqual(first_counts, {"stores": 1, "projects": 11, "rooms": 10, "content": 1})
        self.assertEqual(second_counts, first_counts)
        engine.dispose()


if __name__ == "__main__":
    unittest.main()
