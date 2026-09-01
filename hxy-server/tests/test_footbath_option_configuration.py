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
    SMALL_OPTION_CODES,
    TARGET_CODES,
    configure_footbath_option_drafts,
)


EXPECTED_TARGET_CODES = (
    "hxy-qiqing-30",
    "hxy-xiangxiang-60",
    "hxy-xiaoqi-90",
    "hxy-tuina-70",
    "hxy-spa-90",
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
    category_by_code = {
        "hxy-qiqing-30": "bath",
        "hxy-xiangxiang-60": "bath",
        "hxy-xiaoqi-90": "bath",
        "hxy-tuina-70": "balance",
        "hxy-spa-90": "care",
    }
    projects = {
        code: _add_project(db, store.id, code, category_by_code[code])
        for code in EXPECTED_TARGET_CODES
    }
    projects["small-a"] = _add_project(db, store.id, SMALL_OPTION_CODES[0], "small", price_cents=1_200)
    projects["small-b"] = _add_project(db, store.id, SMALL_OPTION_CODES[1], "small", price_cents=1_500)
    projects["small-c"] = _add_project(db, store.id, SMALL_OPTION_CODES[2], "small", price_cents=1_600)
    projects["small-d"] = _add_project(db, store.id, SMALL_OPTION_CODES[3], "small", price_cents=1_700)
    projects["extra-small"] = _add_project(db, store.id, "small-not-for-footbath", "small", price_cents=1_800)
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


def test_configurator_creates_five_service_catalogs_with_required_preferences(configuration_db):
    db, _, store_id, projects = configuration_db

    report = configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert TARGET_CODES == EXPECTED_TARGET_CODES
    assert report.projects == list(EXPECTED_TARGET_CODES)
    assert report.created_groups == 17
    assert report.created_choices == 68
    expected_small_ids = {
        projects["small-a"].id,
        projects["small-b"].id,
        projects["small-c"].id,
        projects["small-d"].id,
    }
    expected_linked_ids = {*expected_small_ids, projects["local"].id}
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
        group_by_code = {group.code: group for group in groups}
        if code in {"hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90"}:
            expected_group_codes = {
                "footbath-liquid",
                "pressure",
                "small-services",
                "local-strength",
            }
        elif code == "hxy-tuina-70":
            expected_group_codes = {"pressure", "small-services"}
        else:
            expected_group_codes = {"spa-oil", "pressure", "small-services"}
        assert set(group_by_code) == expected_group_codes
        choices = list(
            db.scalars(
                select(ProjectOptionChoice)
                .join(ProjectOptionGroup)
                .where(ProjectOptionGroup.catalog_version_id == version.id)
            )
        )
        linked_choices = [choice for choice in choices if choice.choice_type == "linked_project"]
        expected_project_ids = expected_small_ids
        if code in {"hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90"}:
            expected_project_ids = expected_linked_ids
        assert {choice.linked_project_id for choice in linked_choices} == expected_project_ids
        assert {choice.charge_mode for choice in linked_choices} == {"inherit_linked_price"}
        small_choices = [
            choice for choice in linked_choices
            if choice.option_group_id == group_by_code["small-services"].id
        ]
        assert [choice.code for choice in sorted(small_choices, key=lambda item: item.display_order)] == list(SMALL_OPTION_CODES)
        local_choices = [choice for choice in choices if choice.linked_project_id == projects["local"].id]
        if "local-strength" in expected_group_codes:
            assert [(choice.code, choice.name) for choice in sorted(local_choices, key=lambda item: item.display_order)] == [
                ("local-shoulder-neck", "肩颈"),
                ("local-waist-hip", "腰臀"),
                ("local-leg", "腿部"),
                ("local-abdomen", "腹部"),
                ("local-foot", "足部"),
            ]
            assert all(choice.qualifies_for_foot_bath_bundle for choice in local_choices)
        else:
            assert local_choices == []
        assert all(
            not choice.qualifies_for_foot_bath_bundle
            for choice in choices
            if choice.linked_project_id != projects["local"].id
        )
        expected_preferences = {}
        if code in {"hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90"}:
            expected_preferences["footbath-liquid"] = ["老姜", "艾草", "玫瑰", "薰衣草", "老醋"]
        if code in {"hxy-qiqing-30", "hxy-xiangxiang-60", "hxy-xiaoqi-90", "hxy-tuina-70", "hxy-spa-90"}:
            expected_preferences["pressure"] = ["轻柔", "适中", "强力"]
        if code == "hxy-spa-90":
            expected_preferences["spa-oil"] = ["薰衣草精油", "玫瑰精油", "甜橙精油"]
        for group_code, expected_names in expected_preferences.items():
                group = group_by_code[group_code]
                assert group.selection_mode == "single"
                assert group.required is True
                assert group.min_select == 1
                assert group.max_select == 1
                preference_choices = sorted(
                    [choice for choice in choices if choice.option_group_id == group.id],
                    key=lambda item: item.display_order,
                )
                assert [choice.name for choice in preference_choices] == expected_names
                assert {choice.choice_type for choice in preference_choices} == {"preference"}
                assert {choice.charge_mode for choice in preference_choices} == {"free"}
                assert {choice.linked_project_id for choice in preference_choices} == {None}
    assert db.scalar(select(func.count()).select_from(OptionChoicePrice)) == 0


def test_configurator_includes_optional_spa_60_during_locked_apply(configuration_db):
    db, _, store_id, projects = configuration_db
    projects["spa-60"] = _add_project(db, store_id, "hxy-spa-60", "care")
    db.commit()

    report = configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert "hxy-spa-60" in report.projects
    version = db.scalar(
        select(ProjectCatalogVersion).where(
            ProjectCatalogVersion.project_id == projects["spa-60"].id,
            ProjectCatalogVersion.status == "draft",
        )
    )
    assert version is not None
    groups = list(db.scalars(
        select(ProjectOptionGroup).where(ProjectOptionGroup.catalog_version_id == version.id)
    ))
    assert {group.code for group in groups} == {"spa-oil", "pressure", "small-services"}


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

    assert report.projects == list(EXPECTED_TARGET_CODES)
    assert report.created_groups == 17
    assert report.created_choices == 68
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
def test_configurator_rejects_missing_required_small_reference_before_writing(
    configuration_db,
    mutation,
):
    db, _, store_id, projects = configuration_db
    configure_footbath_option_drafts(db, store_id, dry_run=False)
    db.commit()
    before = _table_counts(db)

    if mutation == "unpublish":
        projects["small-a"].publication_status = "draft"
    else:
        db.execute(delete(PriceBook).where(PriceBook.project_id == projects["small-a"].id))
    db.commit()

    with pytest.raises(ValueError, match=rf"missing published or priced option projects: {SMALL_OPTION_CODES[0]}"):
        configure_footbath_option_drafts(db, store_id, dry_run=False)
    assert _table_counts(db) == before


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
            ProjectOptionChoice.code == SMALL_OPTION_CODES[0],
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
    assert choice.name == SMALL_OPTION_CODES[0]
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
    db.delete(projects[EXPECTED_TARGET_CODES[-1]])
    db.commit()
    before = _table_counts(db)

    with pytest.raises(ValueError, match=r"missing published target projects: hxy-spa-90"):
        configure_footbath_option_drafts(db, store_id, dry_run=False)

    assert _table_counts(db) == before


@pytest.mark.parametrize(
    ("key", "message"),
    [
            ("small-a", rf"missing published or priced option projects: {SMALL_OPTION_CODES[0]}"),
        ("local", r"no independently sellable published project in category: local-strength"),
    ],
)
def test_configurator_missing_reference_category_fails_before_writing(
    configuration_db,
    key,
    message,
):
    db, _, store_id, projects = configuration_db
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
    assert linked_ids == {
        projects["small-a"].id,
        projects["small-b"].id,
        projects["small-c"].id,
        projects["small-d"].id,
        projects["local"].id,
    }
    assert {projects["extra-small"].id, cross_store.id, unpublished.id, unpriced.id}.isdisjoint(linked_ids)


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
    assert report["projects"] == list(EXPECTED_TARGET_CODES)
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
    assert report["created_groups"] == 17
    verify_engine = create_engine(f"sqlite:///{database.as_posix()}")
    with Session(verify_engine) as db:
        assert _table_counts(db) == (5, 17, 68, 0)
        assert set(db.scalars(select(ProjectCatalogVersion.status))) == {"draft"}
    verify_engine.dispose()
