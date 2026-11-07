from __future__ import annotations

import uuid

import pytest
from sqlalchemy import create_engine, func, select
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.domain.catalog_options import publish_catalog_version
from app.models import (
    Addon,
    PageContent,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Room,
    ServicePositionQr,
    Staff,
    Store,
)
from scripts.provision_store import apply_clone_plan, build_clone_plan


@pytest.fixture()
def db():
    engine = create_engine(
        "sqlite://",
        connect_args={"check_same_thread": False},
        poolclass=StaticPool,
    )
    Base.metadata.create_all(engine)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with SessionLocal() as session:
        yield session
    Base.metadata.drop_all(engine)


def _price(db, project_id: int, price_type: str, amount: int) -> None:
    db.add(PriceBook(project_id=project_id, price_type=price_type, amount_cents=amount))


def _seed(db) -> dict:
    source = Store(store_code="source-store", name="源门店", city="安阳", address="源地址", business_hours="10:00-22:00", status="open")
    target = Store(store_code="target-store", name="新门店", city="安阳", address="新地址", business_hours="10:00-22:00", status="preparing")
    admin = Staff(username="hq-admin", password_hash="x", name="总部管理员", role="admin", store_id=None, status="active")
    db.add_all([source, target, admin])
    db.flush()

    project_a = Project(
        store_id=source.id, code="hxy-a", category="bath", name="项目A", duration_min=60,
        summary="A", publication_status="published", content_version="menu-test",
        independently_visible=True, display_order=1, price_label="60分钟",
    )
    project_b = Project(
        store_id=source.id, code="hxy-b", category="small", name="项目B", duration_min=30,
        summary="B", publication_status="published", content_version="menu-test",
        independently_visible=False, display_order=2, price_label="30分钟",
    )
    project_c = Project(
        store_id=source.id, code="hxy-c", category="care", name="项目C", duration_min=60,
        summary="C", publication_status="published", content_version="menu-test",
        independently_visible=True, display_order=3, price_label="60分钟",
    )
    project_d = Project(
        store_id=source.id, code="hxy-d", category="local-strength", name="局部项目D", duration_min=30,
        summary="D", publication_status="published", content_version="menu-test",
        independently_visible=True, display_order=4, price_label="30分钟",
    )
    db.add_all([project_a, project_b, project_c, project_d])
    db.flush()
    _price(db, project_a.id, "store", 10000)
    _price(db, project_a.id, "member", 8000)
    _price(db, project_b.id, "store", 5000)
    _price(db, project_c.id, "store", 7000)
    _price(db, project_d.id, "store", 7900)

    version = ProjectCatalogVersion(project_id=project_a.id, version=1, status="draft")
    db.add(version)
    db.flush()
    group = ProjectOptionGroup(
        catalog_version_id=version.id, code="addons", name="加购",
        selection_mode="multiple", required=False, min_select=0, max_select=1, display_order=1,
    )
    db.add(group)
    db.flush()
    db.add(ProjectOptionChoice(
        option_group_id=group.id, code="b", name="项目B", choice_type="linked_project",
        linked_project_id=project_b.id, charge_mode="inherit_linked_price",
        display_order=0, status="active",
    ))
    db.flush()
    local_group = ProjectOptionGroup(
        catalog_version_id=version.id, code="local-strength", name="局部加强",
        selection_mode="multiple", required=False, min_select=0, max_select=2, display_order=2,
    )
    db.add(local_group)
    db.flush()
    for order, (code, name) in enumerate((("local-shoulder-neck", "肩颈"), ("local-waist-hip", "腰臀"))):
        db.add(ProjectOptionChoice(
            option_group_id=local_group.id, code=code, name=name, choice_type="linked_project",
            linked_project_id=project_d.id, charge_mode="inherit_linked_price",
            qualifies_for_foot_bath_bundle=True, display_order=order, status="active",
        ))
    db.flush()
    publish_catalog_version(db, project_a.id, admin.id)

    db.add(Addon(
        store_id=source.id, code="hxy-addon", name="加购A", parent_project_id=project_a.id,
        display_order=1, chargeable=True, store_price_cents=1900, price_cents=1900,
        publication_status="published",
    ))
    db.add(PageContent(
        store_id=source.id, page_key="diy-home", title="源首页", subtitle="源副标题",
        published=True,
    ))

    container = Room(store_id=source.id, code="room-01", name="1号房间", room_type="room", is_space_container=True, is_service_position=False)
    db.add(container)
    db.flush()
    bed = Room(store_id=source.id, code="bed-01a", name="1号房间A床", room_type="bed", parent_room_id=container.id, is_space_container=False, is_service_position=True)
    sofa = Room(store_id=source.id, code="sofa-01", name="1号沙发", room_type="sofa", is_space_container=False, is_service_position=True)
    db.add_all([bed, sofa])
    db.flush()
    db.add(ServicePositionQr(public_id=str(uuid.uuid4()), store_id=source.id, room_id=sofa.id, status="active"))
    db.commit()
    return {
        "source": source, "target": target, "admin": admin,
        "project_a": project_a, "project_b": project_b, "project_c": project_c, "project_d": project_d,
        "container": container, "bed": bed, "sofa": sofa,
    }


def test_preview_is_read_only_and_reports_expected_counts(db):
    seeded = _seed(db)
    plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")

    assert plan["conflicts"] == []
    assert plan["counts"]["projects"] == 4
    assert plan["counts"]["catalog_versions"] == 1
    assert plan["counts"]["option_groups"] == 2
    assert plan["counts"]["option_choices"] == 3
    assert plan["counts"]["addons"] == 1
    assert plan["counts"]["rooms"] == 3
    assert plan["counts"]["service_positions"] == 2
    assert plan["counts"]["qrs"] == 1
    assert plan["preview_hash"]

    assert db.scalar(select(func.count(Project.id)).where(Project.store_id == seeded["target"].id)) == 0
    assert db.scalar(select(func.count(Room.id)).where(Room.store_id == seeded["target"].id)) == 0


def test_apply_clones_and_remaps_tenant_references(db):
    seeded = _seed(db)
    plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")
    created = apply_clone_plan(db, plan, actor_staff_id=seeded["admin"].id, publish_page=True)
    db.commit()

    assert created["created"]["projects"] == 4
    assert created["created"]["catalog_versions"] == 1
    assert created["created"]["addons"] == 1
    assert created["created"]["pages"] == 1
    assert created["created"]["rooms"] == 3

    target_projects = {
        project.code: project for project in db.scalars(
            select(Project).where(Project.store_id == seeded["target"].id)
        )
    }
    assert set(target_projects) == {"s2-hxy-a", "s2-hxy-b", "s2-hxy-c", "s2-hxy-d"}
    target_a = target_projects["s2-hxy-a"]
    target_b = target_projects["s2-hxy-b"]
    target_d = target_projects["s2-hxy-d"]
    assert target_a.publication_status == "published"
    assert target_a.current_published_version_id is not None
    assert target_b.current_published_version_id is None
    assert target_d.current_published_version_id is None

    version = db.get(ProjectCatalogVersion, target_a.current_published_version_id)
    group = db.scalar(select(ProjectOptionGroup).where(
        ProjectOptionGroup.catalog_version_id == version.id,
        ProjectOptionGroup.code == "addons",
    ))
    choice = db.scalar(select(ProjectOptionChoice).where(ProjectOptionChoice.option_group_id == group.id))
    assert choice.linked_project_id == target_b.id
    assert choice.linked_project_id != seeded["project_b"].id

    local_group = db.scalar(select(ProjectOptionGroup).where(
        ProjectOptionGroup.catalog_version_id == version.id,
        ProjectOptionGroup.code == "local-strength",
    ))
    local_choices = list(db.scalars(select(ProjectOptionChoice).where(
        ProjectOptionChoice.option_group_id == local_group.id,
    ).order_by(ProjectOptionChoice.display_order)))
    assert [choice.name for choice in local_choices] == ["肩颈", "腰臀"]
    assert {choice.linked_project_id for choice in local_choices} == {target_d.id}

    target_addon = db.scalar(select(Addon).where(Addon.store_id == seeded["target"].id))
    assert target_addon.code == "s2-hxy-addon"
    assert target_addon.parent_project_id == target_a.id

    page = db.scalar(select(PageContent).where(PageContent.store_id == seeded["target"].id, PageContent.page_key == "diy-home"))
    assert page.title == "源首页"
    assert page.published is True

    target_rooms = {room.code: room for room in db.scalars(select(Room).where(Room.store_id == seeded["target"].id))}
    assert set(target_rooms) == {"s2-room-01", "s2-bed-01a", "s2-sofa-01"}
    assert target_rooms["s2-bed-01a"].parent_room_id == target_rooms["s2-room-01"].id

    # Source remains the single source of truth.
    assert db.scalar(select(func.count(Project.id)).where(Project.store_id == seeded["source"].id)) == 4
    assert db.scalar(select(func.count(Room.id)).where(Room.store_id == seeded["source"].id)) == 3
    assert seeded["project_a"].current_published_version_id is not None


def test_apply_is_idempotent(db):
    seeded = _seed(db)
    plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")
    apply_clone_plan(db, plan, actor_staff_id=seeded["admin"].id, publish_page=True)
    db.commit()

    second_plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")
    assert second_plan["preview_hash"] == plan["preview_hash"]
    created = apply_clone_plan(db, second_plan, actor_staff_id=seeded["admin"].id, publish_page=True)
    db.commit()
    assert created["created"] == {"projects": 0, "catalog_versions": 0, "addons": 0, "pages": 0, "rooms": 0}
    assert db.scalar(select(func.count(Project.id)).where(Project.store_id == seeded["target"].id)) == 4
    assert db.scalar(select(func.count(Room.id)).where(Room.store_id == seeded["target"].id)) == 3


def test_preview_blocks_cross_store_code_conflict(db):
    seeded = _seed(db)
    other = Store(store_code="other-store", name="其他门店", city="安阳", address="其他地址", status="open")
    db.add(other)
    db.flush()
    db.add(Project(store_id=other.id, code="s2-hxy-a", name="其他店项目", category="bath"))
    db.commit()
    plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")
    assert any(item["kind"] == "project_code_used_by_other_store" for item in plan["conflicts"])


def test_apply_rejects_changed_target_project(db):
    seeded = _seed(db)
    plan = build_clone_plan(db, source_store_id=seeded["source"].id, target_store_id=seeded["target"].id, code_prefix="s2-")
    db.add(Project(store_id=seeded["target"].id, code="s2-hxy-a", name="已改名的项目", category="bath"))
    db.commit()
    with pytest.raises(ValueError, match="名称不同"):
        apply_clone_plan(db, plan, actor_staff_id=seeded["admin"].id)
