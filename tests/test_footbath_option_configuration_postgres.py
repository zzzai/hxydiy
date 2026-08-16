import os
import queue
import threading
import time
import uuid

import pytest
from sqlalchemy import create_engine, delete, select, text
from sqlalchemy.engine import make_url
from sqlalchemy.orm import sessionmaker

from app.db.session import Base
from app.domain.catalog_options import lock_catalog_projects
from app.models import PriceBook, Project, ProjectCatalogVersion, Store
from scripts.configure_footbath_options import TARGET_CODES, configure_footbath_option_drafts


def _isolated_postgres_url() -> str:
    value = os.getenv("HXY_FOOTBATH_TEST_POSTGRES_URL")
    if not value:
        pytest.skip(
            "HXY_FOOTBATH_TEST_POSTGRES_URL is required for real PostgreSQL lock verification"
        )
    parsed = make_url(value)
    if (
        parsed.get_backend_name() != "postgresql"
        or parsed.host not in {"127.0.0.1", "localhost"}
        or not (parsed.database or "").startswith("hxy_footbath_concurrency_")
    ):
        pytest.fail(
            "HXY_FOOTBATH_TEST_POSTGRES_URL must target an isolated local PostgreSQL "
            "database named hxy_footbath_concurrency_*"
        )
    return value


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


@pytest.mark.parametrize("mutation", ["unpublish", "delete-store-price"])
def test_apply_waits_for_concurrent_eligibility_change_and_revalidates_after_lock(mutation):
    engine = create_engine(_isolated_postgres_url(), pool_pre_ping=True)
    SessionLocal = sessionmaker(bind=engine, autoflush=False, expire_on_commit=False)
    Base.metadata.drop_all(engine)
    Base.metadata.create_all(engine)
    suffix = uuid.uuid4().hex
    with SessionLocal.begin() as setup:
        store = Store(
            store_code=f"footbath-lock-{suffix[:12]}",
            name="沐足配置并发测试门店",
            address="isolated postgres test",
        )
        setup.add(store)
        setup.flush()
        for code in TARGET_CODES:
            _add_project(setup, store.id, code, "bath")
        small = _add_project(setup, store.id, f"small-{suffix[:12]}", "small")
        _add_project(setup, store.id, f"local-{suffix[:12]}", "local-strength")
        store_id = store.id
        small_id = small.id

    apply_started = threading.Event()
    apply_pid_queue: queue.Queue[int] = queue.Queue()
    apply_result_queue: queue.Queue[object] = queue.Queue()
    apply_error_queue: queue.Queue[BaseException] = queue.Queue()

    def apply_configuration() -> None:
        with SessionLocal() as transaction:
            try:
                transaction.execute(text("SET LOCAL lock_timeout = '15s'"))
                apply_pid_queue.put(transaction.scalar(text("SELECT pg_backend_pid()")))
                apply_started.set()
                result = configure_footbath_option_drafts(
                    transaction,
                    store_id,
                    dry_run=False,
                )
                transaction.commit()
                apply_result_queue.put(result)
            except BaseException as exc:
                transaction.rollback()
                apply_error_queue.put(exc)

    mutator = SessionLocal()
    apply_thread = threading.Thread(target=apply_configuration, daemon=True)
    mutator_committed = False
    try:
        mutator.execute(text("SET LOCAL lock_timeout = '15s'"))
        mutator_pid = mutator.scalar(text("SELECT pg_backend_pid()"))
        locked = lock_catalog_projects(mutator, [small_id])
        if mutation == "unpublish":
            locked[small_id].publication_status = "draft"
        else:
            list(
                mutator.scalars(
                    select(PriceBook)
                    .where(PriceBook.project_id == small_id)
                    .with_for_update()
                )
            )
            mutator.execute(delete(PriceBook).where(PriceBook.project_id == small_id))
        mutator.flush()

        apply_thread.start()
        assert apply_started.wait(timeout=5)
        apply_pid = apply_pid_queue.get(timeout=5)
        blocking_pids = _wait_for_blocking_pid(engine, apply_pid, mutator_pid)
        assert mutator_pid in blocking_pids
        assert apply_thread.is_alive()
        print(
            f"LOCK_EVIDENCE mutation={mutation} blocker_pid={mutator_pid} "
            f"blocked_pid={apply_pid} pg_blocking_pids={blocking_pids}"
        )

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
