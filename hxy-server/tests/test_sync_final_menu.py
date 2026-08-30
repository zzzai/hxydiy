import unittest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.models import PriceBook, Project, Store
from app.seed import PROJECTS
from app.api.catalog import _current_project_prices
from scripts.sync_final_menu import sync_final_menu


class FinalMenuSyncTests(unittest.TestCase):
  def test_sync_final_menu_updates_existing_prices_and_adds_missing_spa_60(self):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db_session:
      store = Store(store_code="final-menu-sync", name="菜单同步门店", address="测试地址")
      db_session.add(store)
      db_session.flush()
      existing = PROJECTS[0]
      project = Project(store_id=store.id, code=existing[0], name=existing[3], category=existing[1], publication_status="published")
      db_session.add(project)
      db_session.flush()
      db_session.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1))
      db_session.commit()

      result = sync_final_menu(db_session, store.id, apply=True)

      assert result["created"] == len(PROJECTS) - 1
      spa = db_session.scalar(select(Project).where(Project.code == "hxy-spa-60"))
      assert spa is not None and spa.duration_min == 60
      ordered_codes = list(db_session.scalars(
        select(Project.code).where(Project.store_id == store.id).order_by(Project.display_order, Project.id)
      ))
      assert ordered_codes == [item[0] for item in PROJECTS]
      prices = {row.price_type: row.amount_cents for row in db_session.scalars(select(PriceBook).where(PriceBook.project_id == project.id))}
      assert prices["store"] == 3990
      assert len(db_session.scalars(select(PriceBook).where(PriceBook.project_id == project.id)).all()) == 4

      second_result = sync_final_menu(db_session, store.id, apply=True)
      assert second_result == {"created": 0, "updated": 0, "prices_added": 0}
      assert len(db_session.scalars(select(PriceBook)).all()) == len([
        amount
        for item in PROJECTS
        for amount in item[6:9]
        if amount is not None
      ]) + 1

  def test_empty_menu_price_disables_previous_current_price_without_deleting_history(self):
    engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
    Base.metadata.create_all(engine)
    with sessionmaker(bind=engine, expire_on_commit=False)() as db_session:
      store = Store(store_code="final-menu-empty-price", name="空价格门店", address="测试地址")
      db_session.add(store)
      db_session.flush()
      project = Project(
        store_id=store.id,
        code="hxy-taoke-60",
        name="功夫调理",
        category="kit",
        publication_status="published",
      )
      db_session.add(project)
      db_session.flush()
      db_session.add_all([
        PriceBook(project_id=project.id, price_type="store", amount_cents=128000, version="legacy"),
        PriceBook(project_id=project.id, price_type="member", amount_cents=98000, version="legacy"),
      ])
      db_session.commit()

      result = sync_final_menu(db_session, store.id, apply=True)

      assert result["prices_added"] >= 1
      history = list(db_session.scalars(select(PriceBook).where(PriceBook.project_id == project.id)))
      assert any(row.amount_cents == 128000 and row.version == "legacy" for row in history)
      latest_store = db_session.scalar(
        select(PriceBook)
        .where(PriceBook.project_id == project.id, PriceBook.price_type == "store", PriceBook.effective_to.is_(None))
        .order_by(PriceBook.published_at.desc(), PriceBook.id.desc())
      )
      assert latest_store is None
      assert all(row.effective_to is not None for row in history if row.price_type == "store")
      assert _current_project_prices(db_session, project.id) == [{"price_type": "member", "amount_cents": 98000}]
