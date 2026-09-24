import pytest
from sqlalchemy import create_engine, select
from sqlalchemy.orm import Session

from app.db.session import Base
from app.models import Order, PriceBook, Project, ProjectCatalogVersion, ProjectOptionChoice, ProjectOptionGroup, Store, User
from scripts.reconcile_aux_menu import reconcile_store
from app.seed import seed


def test_reconcile_aux_menu_changes_only_live_catalog_and_preserves_history():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        store = Store(store_code="aux-menu-test", name="测试门店", address="测试地址")
        user = User(openid="aux-menu-history")
        db.add_all([store, user])
        db.flush()
        old = [
            ("hxy-caier-30", "采耳", 8900, 5900),
            ("hxy-baguan-1", "拔罐", 5900, 2900),
            ("hxy-guasha-1", "刮痧", 5900, 2900),
            ("hxy-head-30", "头疗", 7900, 4900),
            ("hxy-jubu-30", "局部推拿", 7900, 4900),
            ("hxy-foot-refine-1", "足部精修", 5900, 3900),
        ]
        for code, name, store_price, member_price in old:
            project = Project(store_id=store.id, code=code, name=name, category="small",
                              category_mark="辅", publication_status="published")
            db.add(project)
            db.flush()
            db.add_all([
                PriceBook(project_id=project.id, price_type="store", amount_cents=store_price),
                PriceBook(project_id=project.id, price_type="member", amount_cents=member_price),
            ])
        db.add(Order(order_no="AUX-HISTORY-1", order_type="service", user_id=user.id,
                     store_id=store.id, items=[{"project_code": "hxy-baguan-1", "price_cents": 5900}],
                     total_amount_cents=5900, pay_amount_cents=5900, status="completed"))
        db.commit()
        before_orders = [(row.id, row.items, row.total_amount_cents) for row in db.scalars(select(Order))]
        assert reconcile_store(db, store.id, apply=False)["changes"]
        db.rollback()
        assert db.scalar(select(Project).where(Project.code == "hxy-oil-back-30")) is None
        report = reconcile_store(db, store.id, apply=True)
        db.commit()
        assert len(report["changes"]) > 0
        assert [(row.id, row.items, row.total_amount_cents) for row in db.scalars(select(Order))] == before_orders
        projects = list(db.scalars(select(Project).where(Project.store_id == store.id, Project.category_mark == "辅")))
        visible = sorted(project.name for project in projects if project.independently_visible)
        assert visible == sorted(["头疗", "足部精修", "精油开背", "采耳", "局部推拿", "拔罐/刮痧"])
        assert all(p.publication_status == "published" for p in projects)
        combined = next(p for p in projects if p.code == "hxy-cupping-scraping-1")
        version = db.get(ProjectCatalogVersion, combined.current_published_version_id)
        assert version.status == "published"
        group = db.scalar(select(ProjectOptionGroup).where(ProjectOptionGroup.catalog_version_id == version.id))
        assert group.required and group.selection_mode == "single" and group.min_select == group.max_select == 1
        choices = list(db.scalars(select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == group.id)))
        assert {choice.name for choice in choices} == {"拔罐护理", "刮痧护理"}
        assert all(choice.charge_mode == "free" for choice in choices)
        assert reconcile_store(db, store.id, apply=False)["changes"] == []
        db.add(Project(store_id=store.id, code="unexpected-aux", name="未知项目", category="small",
                       category_mark="辅", publication_status="published"))
        db.commit()
        with pytest.raises(ValueError, match="unexpected_aux_project"):
            reconcile_store(db, store.id, apply=False)
    engine.dispose()


def test_newly_seeded_aux_menu_matches_reconciliation_target():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        assert reconcile_store(db, 1, apply=False)["changes"] == []
    engine.dispose()


def test_reconcile_rejects_combined_project_with_missing_care_choice():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        seed(db)
        choice = db.scalar(select(ProjectOptionChoice).where(ProjectOptionChoice.code == "scraping"))
        db.delete(choice)
        db.commit()
        with pytest.raises(ValueError, match="unexpected_combined_options"):
            reconcile_store(db, 1, apply=False)
    engine.dispose()
