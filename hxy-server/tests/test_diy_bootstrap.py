import unittest
from inspect import getsource

from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import PageContent, Project, Room, Store
from scripts.bootstrap_diy_store import bootstrap_diy_store
from scripts.setup_preview import setup_preview


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
            sofas = list(db.scalars(select(Room).where(Room.room_type == "sofa")))
            room_containers = list(db.scalars(select(Room).where(Room.is_space_container.is_(True))))
            beds = list(db.scalars(select(Room).where(Room.room_type == "bed")))

            self.assertEqual(first_counts, {"stores": 1, "projects": 13, "rooms": 24, "content": 1})
        self.assertEqual(second_counts, first_counts)
        self.assertEqual(len(sofas), 8)
        self.assertEqual(len(room_containers), 7)
        self.assertEqual(len(beds), 9)
        self.assertTrue(all(room.is_service_position for room in sofas + beds))
        self.assertTrue(all(not room.is_service_position for room in room_containers))
        self.assertTrue(all(bed.parent_room_id is not None for bed in beds))
        self.assertEqual(len({(bed.map_x, bed.map_y) for bed in beds}), len(beds))
        self.assertTrue(all(0 < bed.map_width <= 1 and 0 < bed.map_height <= 1 for bed in beds))
        self.assertTrue(all(bed.map_x + bed.map_width <= 1 and bed.map_y + bed.map_height <= 1 for bed in beds))
        engine.dispose()

    def test_preview_setup_reuses_the_production_space_bootstrap(self):
        self.assertIn("bootstrap_diy_store", getsource(setup_preview))


if __name__ == "__main__":
    unittest.main()
