import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import PriceBook, Store
from app.seed import seed
from scripts.sync_final_menu import sync_final_menu


def test_legacy_entrypoint_previews_current_menu_and_rejects_unguarded_apply():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        store = db.scalar(select(Store))
        old_prices = [(row.id, row.amount_cents, row.effective_to) for row in db.scalars(select(PriceBook))]
        preview = sync_final_menu(db, store.id)
        assert preview["version"] == "menu-20261001"
        assert len([change for change in preview["changes"] if change["fields"]["publication_status"] == "published"]) == 14
        with pytest.raises(ValueError, match="authenticated"):
            sync_final_menu(db, store.id, apply=True)
        assert [(row.id, row.amount_cents, row.effective_to) for row in db.scalars(select(PriceBook))] == old_prices
    engine.dispose()
