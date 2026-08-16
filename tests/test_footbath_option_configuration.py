import json
import os
from pathlib import Path
import subprocess
from datetime import UTC, datetime

import pytest
from sqlalchemy import create_engine, delete, event, func, select
from sqlalchemy.orm import Session, sessionmaker

from app.db.session import Base
from app.models import (
    OptionChoicePrice,
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)
from scripts.configure_footbath_options import (
    TARGET_CODES,
    configure_footbath_option_drafts,
)


def _add_project(
    db: Session,
    store_id: int,
    code: str,
    category: str,
    *,
    publication_status: str = "published",
    price_cents: int | None = 1_000,
) -> Project:
    project = Project(
        store_id=store_id,
        code=code,
        category=category,
        name=code,
        publication_status=publication_status,
    )
    db.add(project)
    db.flush()
    if price_cents is not None:
        db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=price_cents))
    return project


def _seed_store(db: Session) -> tuple[Store, dict[str, Project]]:
    store = Store(store_code="footbath-config", name="沐足配置门店", address="测试地址")
    db.add(store)
    db.flush()
    projects = {
        code: _add_project(db, store.id, code, "bath")
        for code in TARGET_CODES
    }
    projects["small-a"] = _add_project(db, store.id, "small-a", "small", price_cents=1_200)
    projects["small-b"] = _add_project(db, store.id, "small-b", "small", price_cents=1_500)
    projects["local"] = _add_project(
        db,
        store.id,
        "local-strength-a",
        "local-strength",
        price_cents=2_000,
    )
    db.commit()
    return store, projects


@pytest.fixture
def configuration_db():
    engine = create_engine("sqlite://")
    Base.metadata.create_all(engine)
    session_local = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    with session_local() as db:
        store, projects = _seed_store(db)
        yield db, engine, store.id, projects
    engine.dispose()


def _table_counts(db: Session) -> tuple[int, int, int, int]:
    return (
        int(db.scalar(select(func.count()).select_from(ProjectCatalogVersion)) or 0),
        int(db.scalar(select(func.count()).select_from(ProjectOptionGroup)) or 0),
        int(db.scalar(select(func.count()).select_from(ProjectOptionChoice)) or 0),
        int(db.scalar(select(func.count()).select_from(OptionChoicePrice)) or 0),
    )


def test_configurator_creates_small_and_local_groups_for_three_projects(configuration_db):
    db, _, store_id, projects = configuration_db

    report = configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert report.projects == list(TARGET_CODES)
    assert report.created_groups == 6
    assert report.created_choices == 9
    expected_linked_ids = {projects["small-a"].id, projects["small-b"].id, projects["local"].id}
    for code in report.projects:
        project_id = db.scalar(
            select(Project.id).where(Project.store_id == store_id, Project.code == code)
        )
        version = db.scalar(
            select(ProjectCatalogVersion).where(
                ProjectCatalogVersion.project_id == project_id,
                ProjectCatalogVersion.status == "draft",
            )
        )
        assert version is not None
        groups = list(
            db.scalars(
                select(ProjectOptionGroup).where(
                    ProjectOptionGroup.catalog_version_id == version.id
                )
            )
        )
        assert {group.code for group in groups} == {"small-services", "local-strength"}
        choices = list(
            db.scalars(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(ProjectOptionGroup.catalog_version_id == version.id)
            )
        )
        assert {choice.linked_project_id for choice in choices} == expected_linked_ids
        assert {choice.choice_type for choice in choices} == {"linked_project"}
        assert {choice.charge_mode for choice in choices} == {"inherit_linked_price"}
    assert db.scalar(select(func.count()).select_from(OptionChoicePrice)) == 0


def test_configurator_dry_run_executes_no_database_writes(configuration_db):
    db, engine, store_id, _ = configuration_db
    writes: list[str] = []

    def capture_statement(_conn, _cursor, statement, _parameters, _context, _executemany):
        operation = statement.lstrip().split(None, 1)[0].upper()
        if operation in {"INSERT", "UPDATE", "DELETE"}:
            writes.append(statement)

    event.listen(engine, "before_cursor_execute", capture_statement)
    try:
        before = _table_counts(db)
        report = configure_footbath_option_drafts(db, store_id, dry_run=True)
        after = _table_counts(db)
    finally:
        event.remove(engine, "before_cursor_execute", capture_statement)

    assert report.projects == list(TARGET_CODES)
    assert report.created_groups == 6
    assert report.created_choices == 9
    assert writes == []
    assert after == before
    assert not db.new
    assert not db.dirty
    assert not db.deleted


def test_configurator_is_idempotent(configuration_db):
    db, _, store_id, _ = configuration_db

    first = configure_footbath_option_drafts(db, store_id, dry_run=False)
    after_first = _table_counts(db)
    second = configure_footbath_option_drafts(db, store_id, dry_run=False)
    after_second = _table_counts(db)

    assert first.created_choices > 0
    assert second.created_groups == 0
    assert second.created_choices == 0
    assert after_second == after_first


@pytest.mark.parametrize("mutation", ["unpublish", "delete-store-price"])
def test_configurator_deactivates_managed_choice_after_reference_loses_eligibility(
    configuration_db,
    mutation,
):
    db, _, store_id, projects = configuration_db
    configure_footbath_option_drafts(db, store_id, dry_run=False)
    db.commit()

    if mutation == "unpublish":
        projects["small-a"].publication_status = "draft"
    else:
        db.execute(delete(PriceBook).where(PriceBook.project_id == projects["small-a"].id))
    db.commit()

    configure_footbath_option_drafts(db, store_id, dry_run=False)

    managed = list(
        db.scalars(
            select(ProjectOptionChoice)
            .join(ProjectOptionGroup)
            .join(ProjectCatalogVersion)
            .where(
                ProjectOptionGroup.code == "small-services",
                ProjectOptionChoice.code == "small-a",
                ProjectCatalogVersion.status == "draft",
            )
            .order_by(ProjectCatalogVersion.project_id)
        )
    )
    assert len(managed) == 3
    assert {choice.status for choice in managed} == {"inactive"}
    active_codes = set(
        db.scalars(
            select(ProjectOptionChoice.code)
            .join(ProjectOptionGroup)
            .join(ProjectCatalogVersion)
            .where(
                ProjectOptionGroup.code == "small-services",
                ProjectOptionChoice.status == "active",
                ProjectCatalogVersion.status == "draft",
            )
        )
    )
    assert active_codes == {"small-b"}


def test_configurator_replaces_existing_dedicated_choice_semantics_and_deletes_prices(
    configuration_db,
):
    db, _, store_id, _ = configuration_db
    configure_footbath_option_drafts(db, store_id, dry_run=False)
    choice = db.scalar(
        select(ProjectOptionChoice)
        .join(ProjectOptionGroup)
        .join(ProjectCatalogVersion)
        .join(Project, Project.id == ProjectCatalogVersion.project_id)
        .where(
            Project.code == TARGET_CODES[0],
            ProjectOptionGroup.code == "small-services",
            ProjectOptionChoice.code == "small-a",
        )
    )
    choice.name = "旧收费小项"
    choice.description = "旧收费语义"
    choice.choice_type = "dedicated_charge"
    choice.linked_project_id = None
    choice.charge_mode = "custom_price"
    choice.independently_visible = False
    choice.coupon_eligible = True
    choice.annual_gift_eligible = True
    choice.qualifies_for_foot_bath_bundle = True
    db.add(OptionChoicePrice(
        option_choice_id=choice.id,
        price_type="store",
        amount_cents=888,
        effective_from=datetime(2026, 8, 1, tzinfo=UTC),
    ))
    db.commit()

    configure_footbath_option_drafts(db, store_id, dry_run=False)

    db.refresh(choice)
    assert choice.name == "small-a"
    assert choice.description == ""
    assert choice.choice_type == "linked_project"
    assert choice.linked_project_id is not None
    assert choice.pinned_linked_catalog_version_id is None
    assert choice.charge_mode == "inherit_linked_price"
    assert choice.independently_visible is True
    assert choice.coupon_eligible is False
    assert choice.annual_gift_eligible is False
    assert choice.qualifies_for_foot_bath_bundle is False
    assert choice.status == "active"
    assert db.scalar(
        select(func.count())
        .select_from(OptionChoicePrice)
        .where(OptionChoicePrice.option_choice_id == choice.id)
    ) == 0


def test_configurator_missing_target_fails_before_writing(configuration_db):
    db, _, store_id, projects = configuration_db
    db.delete(projects[TARGET_CODES[-1]])
    db.commit()
    before = _table_counts(db)

    with pytest.raises(ValueError, match=r"missing published target projects: hxy-xiaoqi-90"):
        configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert _table_counts(db) == before


@pytest.mark.parametrize(
    ("key", "message"),
    [
        ("small-a", r"no independently sellable published project in category: small"),
        ("local", r"no independently sellable published project in category: local-strength"),
    ],
)
def test_configurator_missing_reference_category_fails_before_writing(
    configuration_db,
    key,
    message,
):
    db, _, store_id, projects = configuration_db
    if key == "small-a":
        projects["small-a"].publication_status = "draft"
        projects["small-b"].publication_status = "draft"
    else:
        projects[key].publication_status = "draft"
    db.commit()
    before = _table_counts(db)

    with pytest.raises(ValueError, match=message):
        configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert _table_counts(db) == before


def test_configurator_excludes_cross_store_unpublished_and_unpriced_references(configuration_db):
    db, _, store_id, projects = configuration_db
    other_store = Store(store_code="footbath-other", name="其他门店", address="测试地址")
    db.add(other_store)
    db.flush()
    cross_store = _add_project(db, other_store.id, "other-small", "small")
    unpublished = _add_project(
        db,
        store_id,
        "draft-small",
        "small",
        publication_status="draft",
    )
    unpriced = _add_project(db, store_id, "unpriced-small", "small", price_cents=None)
    db.commit()

    configure_footbath_option_drafts(db, store_id, dry_run=False)

    linked_ids = set(
        db.scalars(
            select(ProjectOptionChoice.linked_project_id).where(
                ProjectOptionChoice.linked_project_id.is_not(None)
            )
        )
    )
    assert linked_ids == {projects["small-a"].id, projects["small-b"].id, projects["local"].id}
    assert {cross_store.id, unpublished.id, unpriced.id}.isdisjoint(linked_ids)


def test_cli_defaults_to_read_only(tmp_path):
    database = tmp_path / "footbath-cli.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        store, _ = _seed_store(db)
        store_id = store.id
    engine.dispose()
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "ENVIRONMENT": "test",
    }

    result = subprocess.run(
        [
            os.fspath(Path(os.sys.executable)),
            "scripts/configure_footbath_options.py",
            "--store-id",
            str(store_id),
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["projects"] == list(TARGET_CODES)
    verify_engine = create_engine(f"sqlite:///{database.as_posix()}")
    with Session(verify_engine) as db:
        assert _table_counts(db) == (0, 0, 0, 0)
    verify_engine.dispose()


def test_cli_explicit_apply_authorizes_write_regardless_of_environment_label(tmp_path):
    database = tmp_path / "footbath-cli-apply.db"
    engine = create_engine(f"sqlite:///{database.as_posix()}")
    Base.metadata.create_all(engine)
    with Session(engine) as db:
        store, _ = _seed_store(db)
        store_id = store.id
    engine.dispose()
    environment = {
        **os.environ,
        "DATABASE_URL": f"sqlite:///{database.as_posix()}",
        "ENVIRONMENT": "production",
    }

    result = subprocess.run(
        [
            os.fspath(Path(os.sys.executable)),
            "scripts/configure_footbath_options.py",
            "--store-id",
            str(store_id),
            "--apply",
        ],
        cwd=Path(__file__).resolve().parents[1],
        env=environment,
        capture_output=True,
        text=True,
        check=True,
    )

    report = json.loads(result.stdout)
    assert report["created_groups"] == 6
    verify_engine = create_engine(f"sqlite:///{database.as_posix()}")
    with Session(verify_engine) as db:
        assert _table_counts(db) == (3, 6, 9, 0)
        assert set(db.scalars(select(ProjectCatalogVersion.status))) == {"draft"}
    verify_engine.dispose()
