import os
import queue
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, delete, func, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.models import (
    PriceBook,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    Store,
)
from scripts.configure_footbath_options import TARGET_CODES, configure_footbath_option_drafts


def _isolated_postgres_url() -> str:
    value = os.getenv("HXY_FOOTBATH_TEST_POSTGRES_URL")
    if not value:
        pytest.skip(
            "HXY_FOOTBATH_TEST_POSTGRES_URL is required for real PostgreSQL lock verification"
        )
    parsed = make_url(value)
    if parsed.query:
        pytest.fail(
            "HXY_FOOTBATH_TEST_POSTGRES_URL must not include query parameters"
        )
    if (
        parsed.drivername != "postgresql+psycopg"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or not (parsed.database or "").startswith("hxy_footbath_concurrency_")
    ):
        pytest.fail(
            "HXY_FOOTBATH_TEST_POSTGRES_URL must use the postgresql+psycopg driver and "
            "target an isolated local PostgreSQL database named hxy_footbath_concurrency_*"
        )
    return value


@pytest.mark.parametrize(
    "query",
    [
        "host=production.internal",
        "hostaddr=203.0.113.10",
        "service=production",
        "port=6432",
        "sslmode=require",
    ],
)
def test_postgres_url_guard_rejects_all_query_parameter_overrides(monkeypatch, query):
    monkeypatch.setenv(
        "HXY_FOOTBATH_TEST_POSTGRES_URL",
        "postgresql+psycopg://test:secret@localhost/"
        f"hxy_footbath_concurrency_guard?{query}",
    )

    with pytest.raises(pytest.fail.Exception, match="must not include query parameters"):
        _isolated_postgres_url()


@pytest.mark.parametrize("driver", ["postgresql", "postgresql+psycopg2", "postgresql+asyncpg"])
def test_postgres_url_guard_rejects_unapproved_postgresql_drivers(monkeypatch, driver):
    monkeypatch.setenv(
        "HXY_FOOTBATH_TEST_POSTGRES_URL",
        f"{driver}://test:secret@localhost/hxy_footbath_concurrency_guard",
    )

    with pytest.raises(pytest.fail.Exception, match="must use the postgresql\\+psycopg driver"):
        _isolated_postgres_url()


def _wait_for_blocking_pid(engine, blocked_pid: int, blocker_pid: int) -> list[int]:
    deadline = time.monotonic() + 10
    with engine.connect() as observer:
        while time.monotonic() < deadline:
            blocking_pids = list(
                observer.scalar(
                    text("SELECT pg_blocking_pids(:blocked_pid)"),
                    {"blocked_pid": blocked_pid},
                )
                or []
            )
            if blocker_pid in blocking_pids:
                return blocking_pids
            time.sleep(0.05)
    return []


def _add_project(db, store_id: int, code: str, category: str) -> Project:
    project = Project(
        store_id=store_id,
        code=code,
        category=category,
        name=code,
        publication_status="published",
    )
    db.add(project)
    db.flush()
    db.add(PriceBook(project_id=project.id, price_type="store", amount_cents=1_000))
    return project


def _reset_database(engine) -> None:
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)


def _seed_configuration(SessionLocal, suffix: str, *, include_low_scope_project: bool = False):
    with SessionLocal.begin() as setup:
        store = Store(
            store_code=f"footbath-lock-{suffix[:12]}",
            name="沐足配置并发测试门店",
            address="isolated postgres test",
        )
        setup.add(store)
        setup.flush()
        low = None
        if include_low_scope_project:
            low = _add_project(setup, store.id, f"aaa-low-{suffix[:12]}", "small")
            low.publication_status = "draft"
        targets = [_add_project(setup, store.id, code, "bath") for code in TARGET_CODES]
        small = _add_project(setup, store.id, f"small-{suffix[:12]}", "small")
        local = _add_project(setup, store.id, f"local-{suffix[:12]}", "local-strength")
        return {
            "store_id": store.id,
            "low_id": low.id if low is not None else None,
            "target_ids": [project.id for project in targets],
            "small_id": small.id,
            "local_id": local.id,
        }


def _apply_worker(
    SessionLocal,
    store_id: int,
    start: threading.Event,
    pid_queue: queue.Queue[int],
    result_queue: queue.Queue[object],
    error_queue: queue.Queue[BaseException],
) -> None:
    with SessionLocal() as transaction:
        try:
            transaction.execute(text("SET LOCAL lock_timeout = '15s'"))
            pid_queue.put(transaction.scalar(text("SELECT pg_backend_pid()")))
            start.wait(timeout=10)
            result = configure_footbath_option_drafts(transaction, store_id, dry_run=False)
            transaction.commit()
            result_queue.put(result)
        except BaseException as exc:
            transaction.rollback()
            error_queue.put(exc)


def test_apply_locks_complete_project_scope_in_one_order_before_revalidation():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _reset_database(engine)
    suffix = uuid.uuid4().hex
    seeded = _seed_configuration(SessionLocal, suffix, include_low_scope_project=True)

    apply_start = threading.Event()
    apply_pid_queue: queue.Queue[int] = queue.Queue()
    apply_result_queue: queue.Queue[object] = queue.Queue()
    apply_error_queue: queue.Queue[BaseException] = queue.Queue()
    mutator = SessionLocal()
    apply_thread = threading.Thread(
        target=_apply_worker,
        args=(
            SessionLocal,
            seeded["store_id"],
            apply_start,
            apply_pid_queue,
            apply_result_queue,
            apply_error_queue,
        ),
        daemon=True,
    )
    mutator_committed = False
    try:
        mutator.execute(text("SET LOCAL lock_timeout = '15s'"))
        mutator_pid = mutator.scalar(text("SELECT pg_backend_pid()"))
        mutator.scalar(
            select(Project)
            .where(Project.id == seeded["low_id"])
            .with_for_update()
        )

        apply_thread.start()
        apply_pid = apply_pid_queue.get(timeout=5)
        apply_start.set()
        blocking_pids = _wait_for_blocking_pid(engine, apply_pid, mutator_pid)
        assert mutator_pid in blocking_pids
        assert apply_thread.is_alive()
        print(
            f"PROJECT_ROW_LOCK_EVIDENCE blocker_pid={mutator_pid} "
            f"blocked_pid={apply_pid} pg_blocking_pids={blocking_pids}"
        )

        small = mutator.get(Project, seeded["small_id"])
        small.publication_status = "draft"
        mutator.flush()
        mutator.commit()
        mutator_committed = True
        apply_thread.join(timeout=10)
        assert not apply_thread.is_alive()
        assert apply_result_queue.empty()
        error = apply_error_queue.get_nowait()
        assert isinstance(error, ValueError)
        assert "no independently sellable published project in category: small" in str(error)

        with SessionLocal() as verification:
            assert verification.scalar(
                select(ProjectCatalogVersion.id).limit(1)
            ) is None
    finally:
        if not mutator_committed and mutator.in_transaction():
            mutator.rollback()
        mutator.close()
        if apply_thread.is_alive():
            apply_thread.join(timeout=20)
        engine.dispose()


def test_direct_project_and_pricebook_writers_wait_for_configurator_row_locks():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _reset_database(engine)
    seeded = _seed_configuration(SessionLocal, uuid.uuid4().hex)
    with SessionLocal.begin() as first_apply:
        configure_footbath_option_drafts(first_apply, seeded["store_id"], dry_run=False)
    with SessionLocal.begin() as tamper:
        group = tamper.scalar(
            select(ProjectOptionGroup)
            .join(ProjectCatalogVersion)
            .where(
                ProjectCatalogVersion.project_id == seeded["target_ids"][0],
                ProjectCatalogVersion.status == "draft",
                ProjectOptionGroup.code == "small-services",
            )
        )
        group.name = "force-configurator-update"
        group_id = group.id

    group_blocker = SessionLocal()
    apply_start = threading.Event()
    apply_pid_queue: queue.Queue[int] = queue.Queue()
    apply_result_queue: queue.Queue[object] = queue.Queue()
    apply_error_queue: queue.Queue[BaseException] = queue.Queue()
    apply_thread = threading.Thread(
        target=_apply_worker,
        args=(
            SessionLocal,
            seeded["store_id"],
            apply_start,
            apply_pid_queue,
            apply_result_queue,
            apply_error_queue,
        ),
        daemon=True,
    )
    price_pid_queue: queue.Queue[int] = queue.Queue()
    price_result_queue: queue.Queue[str] = queue.Queue()
    price_error_queue: queue.Queue[BaseException] = queue.Queue()
    project_pid_queue: queue.Queue[int] = queue.Queue()
    project_result_queue: queue.Queue[str] = queue.Queue()
    project_error_queue: queue.Queue[BaseException] = queue.Queue()

    def direct_project_update_then_rollback() -> None:
        with SessionLocal() as transaction:
            try:
                transaction.execute(text("SET LOCAL lock_timeout = '15s'"))
                project_pid_queue.put(transaction.scalar(text("SELECT pg_backend_pid()")))
                project = transaction.get(Project, seeded["small_id"])
                project.publication_status = "draft"
                transaction.flush()
                transaction.rollback()
                project_result_queue.put("rolled-back")
            except BaseException as exc:
                transaction.rollback()
                project_error_queue.put(exc)

    def direct_price_delete_then_rollback() -> None:
        with SessionLocal() as transaction:
            try:
                transaction.execute(text("SET LOCAL lock_timeout = '15s'"))
                price_pid_queue.put(transaction.scalar(text("SELECT pg_backend_pid()")))
                transaction.execute(
                    delete(PriceBook).where(PriceBook.project_id == seeded["small_id"])
                )
                transaction.rollback()
                price_result_queue.put("rolled-back")
            except BaseException as exc:
                transaction.rollback()
                price_error_queue.put(exc)

    price_thread = threading.Thread(target=direct_price_delete_then_rollback, daemon=True)
    project_thread = threading.Thread(target=direct_project_update_then_rollback, daemon=True)
    group_blocker_committed = False
    try:
        group_blocker.execute(text("SET LOCAL lock_timeout = '15s'"))
        group_blocker_pid = group_blocker.scalar(text("SELECT pg_backend_pid()"))
        group_blocker.scalar(
            select(ProjectOptionGroup)
            .where(ProjectOptionGroup.id == group_id)
            .with_for_update()
        )
        apply_thread.start()
        apply_pid = apply_pid_queue.get(timeout=5)
        apply_start.set()
        apply_blocking = _wait_for_blocking_pid(engine, apply_pid, group_blocker_pid)
        assert group_blocker_pid in apply_blocking

        project_thread.start()
        project_pid = project_pid_queue.get(timeout=5)
        project_blocking = _wait_for_blocking_pid(engine, project_pid, apply_pid)
        assert apply_pid in project_blocking
        print(
            f"PROJECT_WRITER_ROW_LOCK_EVIDENCE blocker_pid={apply_pid} "
            f"blocked_pid={project_pid} pg_blocking_pids={project_blocking}"
        )

        price_thread.start()
        price_pid = price_pid_queue.get(timeout=5)
        price_blocking = _wait_for_blocking_pid(engine, price_pid, apply_pid)
        assert apply_pid in price_blocking
        print(
            f"PRICEBOOK_ROW_LOCK_EVIDENCE blocker_pid={apply_pid} "
            f"blocked_pid={price_pid} pg_blocking_pids={price_blocking}"
        )

        group_blocker.commit()
        group_blocker_committed = True
        apply_thread.join(timeout=10)
        project_thread.join(timeout=10)
        price_thread.join(timeout=10)
        assert not apply_thread.is_alive()
        assert not project_thread.is_alive()
        assert not price_thread.is_alive()
        assert apply_error_queue.empty()
        assert project_error_queue.empty()
        assert price_error_queue.empty()
        assert apply_result_queue.get_nowait().created_choices == 0
        assert project_result_queue.get_nowait() == "rolled-back"
        assert price_result_queue.get_nowait() == "rolled-back"
        with SessionLocal() as verification:
            assert verification.scalar(
                select(func.count())
                .select_from(PriceBook)
                .where(PriceBook.project_id == seeded["small_id"])
            ) == 1
    finally:
        if not group_blocker_committed and group_blocker.in_transaction():
            group_blocker.rollback()
        group_blocker.close()
        if apply_thread.is_alive():
            apply_thread.join(timeout=20)
        if project_thread.is_alive():
            project_thread.join(timeout=20)
        if price_thread.is_alive():
            price_thread.join(timeout=20)
        engine.dispose()


def test_concurrent_applies_serialize_without_duplicate_drafts():
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    _reset_database(engine)
    seeded = _seed_configuration(SessionLocal, uuid.uuid4().hex)
    start = threading.Event()
    pid_queue: queue.Queue[int] = queue.Queue()
    result_queue: queue.Queue[object] = queue.Queue()
    error_queue: queue.Queue[BaseException] = queue.Queue()
    threads = [
        threading.Thread(
            target=_apply_worker,
            args=(
                SessionLocal,
                seeded["store_id"],
                start,
                pid_queue,
                result_queue,
                error_queue,
            ),
            daemon=True,
        )
        for _ in range(2)
    ]
    try:
        for thread in threads:
            thread.start()
        pids = sorted(pid_queue.get(timeout=5) for _ in threads)
        start.set()
        for thread in threads:
            thread.join(timeout=15)
        assert all(not thread.is_alive() for thread in threads)
        assert error_queue.empty()
        reports = [result_queue.get_nowait() for _ in threads]
        assert sorted(report.created_groups for report in reports) == [0, 6]
        assert sorted(report.created_choices for report in reports) == [0, 6]
        with SessionLocal() as verification:
            assert verification.scalar(
                select(func.count()).select_from(ProjectCatalogVersion)
            ) == 3
            assert verification.scalar(select(func.count()).select_from(ProjectOptionGroup)) == 6
            assert verification.scalar(select(func.count()).select_from(ProjectOptionChoice)) == 6
        print(f"DUAL_APPLY_SERIALIZED pids={pids} versions=3 groups=6 choices=6")
    finally:
        for thread in threads:
            if thread.is_alive():
                thread.join(timeout=20)
        engine.dispose()
