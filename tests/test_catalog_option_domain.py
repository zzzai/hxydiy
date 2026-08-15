import json
import unittest
from datetime import UTC, datetime, timedelta

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
from app.domain.catalog_options import (
    CatalogDomainError,
    CatalogDraftNotFoundError,
    CatalogPublishedVersionNotFoundError,
    CatalogProjectNotFoundError,
    CatalogPublicationError,
    _snapshot_hash,
    copy_catalog_version_graph,
    lock_catalog_projects,
    publish_catalog_version,
    resolve_published_project_config,
    validate_catalog_version,
)
from app.models import (
    OptionChoicePrice,
    Project,
    ProjectCatalogVersion,
    ProjectOptionChoice,
    ProjectOptionGroup,
    PriceBook,
    Staff,
    Store,
)


class CatalogOptionDomainTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)

    def tearDown(self):
        self.engine.dispose()

    def test_catalog_project_locks_acquire_shared_postgres_advisory_lock_first(self):
        events = []

        class Dialect:
            name = "postgresql"

        class Bind:
            dialect = Dialect()

        class RecordingSession:
            def get_bind(self):
                return Bind()

            def execute(self, statement, params=None):
                events.append(("execute", str(statement), params or {}))

            def scalars(self, statement):
                events.append(("scalars", str(statement), {}))
                return []

        self.assertEqual(lock_catalog_projects(RecordingSession(), [9, 3]), {})
        self.assertEqual(events[0][0], "execute")
        self.assertIn("pg_advisory_xact_lock", events[0][1])
        self.assertEqual(events[0][2]["lock_id"], 1213757763)
        self.assertEqual([event[0] for event in events[1:]], ["scalars", "scalars"])

    @staticmethod
    def _add_store(db, code="catalog-domain-store"):
        store = Store(store_code=code, name="目录测试门店", address="测试地址", status="open")
        db.add(store)
        db.flush()
        return store

    @staticmethod
    def _add_project(db, store, code, *, publication_status="published"):
        project = Project(
            store_id=store.id,
            code=code,
            category="catalog-test",
            name=code,
            publication_status=publication_status,
        )
        db.add(project)
        db.flush()
        return project

    @staticmethod
    def _add_version(db, project, version=1, *, status="draft"):
        catalog_version = ProjectCatalogVersion(
            project_id=project.id,
            version=version,
            status=status,
        )
        db.add(catalog_version)
        db.flush()
        if status == "published":
            project.current_published_version_id = catalog_version.id
        return catalog_version

    @staticmethod
    def _add_group(
        db,
        version,
        code,
        *,
        required=False,
        min_select=0,
        max_select=1,
        display_order=0,
    ):
        group = ProjectOptionGroup(
            catalog_version_id=version.id,
            code=code,
            name=code,
            required=required,
            min_select=min_select,
            max_select=max_select,
            display_order=display_order,
        )
        db.add(group)
        db.flush()
        return group

    @staticmethod
    def _add_choice(
        db,
        group,
        code,
        *,
        choice_type="preference",
        linked_project_id=None,
        charge_mode="free",
        status="active",
        display_order=0,
        qualifies_for_foot_bath_bundle=False,
    ):
        choice = ProjectOptionChoice(
            option_group_id=group.id,
            code=code,
            name=code,
            choice_type=choice_type,
            linked_project_id=linked_project_id,
            charge_mode=charge_mode,
            status=status,
            display_order=display_order,
            qualifies_for_foot_bath_bundle=qualifies_for_foot_bath_bundle,
        )
        db.add(choice)
        db.flush()
        return choice

    @staticmethod
    def _add_store_price(db, choice, amount=1000, *, price_type="store", days_ago=0):
        db.add(OptionChoicePrice(
            option_choice_id=choice.id,
            price_type=price_type,
            amount_cents=amount,
            effective_from=datetime.now(UTC) - timedelta(days=days_ago),
        ))

    def test_validate_catalog_rejects_link_cycle(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            first = self._add_project(db, store, "cycle-first")
            second = self._add_project(db, store, "cycle-second")
            first_draft = self._add_version(db, first)
            second_published = self._add_version(db, second, status="published")
            first_group = self._add_group(db, first_draft, "first-links")
            second_group = self._add_group(db, second_published, "second-links")
            self._add_choice(
                db,
                first_group,
                "to-second",
                choice_type="linked_project",
                linked_project_id=second.id,
                charge_mode="inherit_linked_price",
            )
            self._add_choice(
                db,
                second_group,
                "to-first",
                choice_type="linked_project",
                linked_project_id=first.id,
                charge_mode="inherit_linked_price",
            )
            db.commit()

            errors = validate_catalog_version(db, first_draft.id)

            cycle = next(error for error in errors if error.code == "project_link_cycle")
            self.assertEqual(cycle.path, "groups.first-links.choices.to-second")

    def test_validate_catalog_rejects_custom_price_without_current_store_price(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "missing-price")
            version = self._add_version(db, project)
            group = self._add_group(db, version, "addons")
            choice = self._add_choice(
                db,
                group,
                "hot-pack",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            self._add_store_price(db, choice, days_ago=2)
            expired = datetime.now(UTC) - timedelta(days=1)
            db.flush()
            price = choice.id
            for row in db.query(OptionChoicePrice).filter_by(option_choice_id=price):
                row.effective_to = expired
            db.commit()

            errors = validate_catalog_version(db, version.id)

            missing = next(error for error in errors if error.code == "store_price_required")
            self.assertEqual(missing.path, "groups.addons.choices.hot-pack.prices.store")

    def test_validate_catalog_rejects_required_empty_group_and_invalid_counts(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "invalid-counts")
            version = self._add_version(db, project)
            self._add_group(db, version, "empty", required=True, min_select=1, max_select=1)
            limited = self._add_group(db, version, "limited", min_select=3, max_select=2)
            self._add_choice(db, limited, "only-active")
            self._add_choice(db, limited, "inactive", status="inactive")
            over_available = self._add_group(db, version, "over-available", max_select=2)
            self._add_choice(db, over_available, "one")
            db.commit()

            errors = validate_catalog_version(db, version.id)

            by_code = {error.code: error.path for error in errors}
            self.assertEqual(by_code["required_group_empty"], "groups.empty")
            self.assertEqual(by_code["min_select_exceeds_max"], "groups.limited.min_select")
            self.assertEqual(by_code["min_select_exceeds_available"], "groups.limited.min_select")
            self.assertEqual(by_code["max_select_exceeds_available"], "groups.over-available.max_select")

    def test_validate_catalog_rejects_negative_and_contradictory_selection_counts(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "invalid-selection-counts")
            version = self._add_version(db, project)
            negative_min = self._add_group(db, version, "negative-min", min_select=-1)
            self._add_choice(db, negative_min, "one")
            negative_max = self._add_group(db, version, "negative-max", max_select=-1)
            self._add_choice(db, negative_max, "one")
            required_zero = self._add_group(db, version, "required-zero", required=True, max_select=0)
            self._add_choice(db, required_zero, "one")
            single_too_many = self._add_group(db, version, "single-too-many", max_select=2)
            self._add_choice(db, single_too_many, "one")
            self._add_choice(db, single_too_many, "two")
            db.commit()

            errors = validate_catalog_version(db, version.id)

            by_code = {error.code: error.path for error in errors}
            self.assertEqual(by_code["min_select_negative"], "groups.negative-min.min_select")
            self.assertEqual(by_code["max_select_negative"], "groups.negative-max.max_select")
            self.assertEqual(by_code["required_group_max_zero"], "groups.required-zero.max_select")
            self.assertEqual(by_code["single_group_max_exceeds_one"], "groups.single-too-many.max_select")

    def test_validate_catalog_rejects_bundle_qualification_on_free_preference(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "invalid-bundle")
            version = self._add_version(db, project)
            group = self._add_group(db, version, "preference")
            self._add_choice(
                db,
                group,
                "soft",
                qualifies_for_foot_bath_bundle=True,
            )
            db.commit()

            errors = validate_catalog_version(db, version.id)

            invalid = next(error for error in errors if error.code == "bundle_qualification_requires_charge")
            self.assertEqual(invalid.path, "groups.preference.choices.soft.qualifies_for_foot_bath_bundle")

    def test_validate_catalog_reports_choice_type_charge_mode_contradictions_without_bundle_masking(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "invalid-choice-contracts")
            version = self._add_version(db, project)
            group = self._add_group(db, version, "choices")
            preference = self._add_choice(
                db,
                group,
                "preference-priced",
                choice_type="preference",
                charge_mode="custom_price",
                qualifies_for_foot_bath_bundle=True,
            )
            self._add_store_price(db, preference)
            self._add_choice(
                db,
                group,
                "linked-free",
                choice_type="linked_project",
                charge_mode="free",
                qualifies_for_foot_bath_bundle=True,
            )
            linked = self._add_project(db, store, "dedicated-linked")
            self._add_version(db, linked, status="published")
            dedicated = self._add_choice(
                db,
                group,
                "dedicated-inherit",
                choice_type="dedicated_charge",
                charge_mode="inherit_linked_price",
                linked_project_id=linked.id,
            )
            self._add_store_price(db, dedicated)
            db.commit()

            errors = validate_catalog_version(db, version.id)

            by_code = {error.code: error.path for error in errors}
            self.assertEqual(
                by_code["preference_must_be_free"],
                "groups.choices.choices.preference-priced.charge_mode",
            )
            self.assertEqual(
                by_code["linked_project_must_inherit_linked_price"],
                "groups.choices.choices.linked-free.charge_mode",
            )
            self.assertEqual(
                by_code["linked_project_required"],
                "groups.choices.choices.linked-free.linked_project_id",
            )
            self.assertEqual(
                by_code["dedicated_charge_must_use_custom_price"],
                "groups.choices.choices.dedicated-inherit.charge_mode",
            )
            self.assertEqual(
                by_code["dedicated_charge_cannot_link_project"],
                "groups.choices.choices.dedicated-inherit.linked_project_id",
            )
            self.assertNotIn("bundle_qualification_requires_charge", by_code)

    def test_validate_catalog_rejects_link_depth_beyond_two_levels(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            root = self._add_project(db, store, "depth-root")
            first = self._add_project(db, store, "depth-first")
            second = self._add_project(db, store, "depth-second")
            third = self._add_project(db, store, "depth-third")
            root_version = self._add_version(db, root)
            first_version = self._add_version(db, first, status="published")
            second_version = self._add_version(db, second, status="published")
            self._add_version(db, third, status="published")
            root_group = self._add_group(db, root_version, "root-link")
            first_group = self._add_group(db, first_version, "first-link")
            second_group = self._add_group(db, second_version, "second-link")
            self._add_choice(db, root_group, "to-first", choice_type="linked_project", linked_project_id=first.id, charge_mode="inherit_linked_price")
            self._add_choice(db, first_group, "to-second", choice_type="linked_project", linked_project_id=second.id, charge_mode="inherit_linked_price")
            self._add_choice(db, second_group, "to-third", choice_type="linked_project", linked_project_id=third.id, charge_mode="inherit_linked_price")
            db.commit()

            errors = validate_catalog_version(db, root_version.id)

            too_deep = next(error for error in errors if error.code == "project_link_depth_exceeded")
            self.assertEqual(too_deep.path, "groups.root-link.choices.to-first")

    def test_validate_catalog_rejects_unpublished_cross_store_and_archived_links(self):
        with self.SessionLocal() as db:
            main_store = self._add_store(db, "main-store")
            other_store = self._add_store(db, "other-store")
            root = self._add_project(db, main_store, "invalid-links-root")
            unpublished_catalog = self._add_project(db, main_store, "no-published-catalog")
            inactive = self._add_project(db, main_store, "inactive-project", publication_status="draft")
            cross_store = self._add_project(db, other_store, "cross-store")
            archived = self._add_project(db, main_store, "archived-project", publication_status="archived")
            self._add_version(db, cross_store, status="published")
            version = self._add_version(db, root)
            group = self._add_group(db, version, "links")
            for code, target in (
                ("no-catalog", unpublished_catalog),
                ("inactive", inactive),
                ("cross-store", cross_store),
                ("archived", archived),
            ):
                self._add_choice(db, group, code, choice_type="linked_project", linked_project_id=target.id, charge_mode="inherit_linked_price")
            db.commit()

            errors = validate_catalog_version(db, version.id)

            codes = {error.code for error in errors}
            # 已发布但没有选项目录的正式项目是稳定的 linked leaf，可以被引用。
            self.assertNotIn("linked_project_catalog_unpublished", codes)
            self.assertIn("linked_project_unpublished", codes)
            self.assertIn("linked_project_cross_store", codes)
            self.assertIn("linked_project_archived", codes)

    def test_validate_catalog_rejects_repeated_link_without_part(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            root = self._add_project(db, store, "duplicate-scope-root")
            linked = self._add_project(db, store, "duplicate-scope-linked")
            self._add_version(db, linked, status="published")
            version = self._add_version(db, root)
            first_group = self._add_group(db, version, "first")
            second_group = self._add_group(db, version, "second")
            self._add_choice(db, first_group, "same-code", choice_type="linked_project", linked_project_id=linked.id, charge_mode="inherit_linked_price")
            self._add_choice(db, second_group, "same-code", choice_type="linked_project", linked_project_id=linked.id, charge_mode="inherit_linked_price")
            db.commit()

            errors = validate_catalog_version(db, version.id)

            codes = {error.code for error in errors}
            self.assertIn("duplicate_linked_project", codes)

    def test_validate_catalog_allows_reusing_choice_code_in_different_groups(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "choice-code-scope")
            version = self._add_version(db, project)
            first_group = self._add_group(db, version, "first")
            second_group = self._add_group(db, version, "second")
            self._add_choice(db, first_group, "same-code")
            self._add_choice(db, second_group, "same-code")
            db.commit()

            errors = validate_catalog_version(db, version.id)

            self.assertNotIn("duplicate_choice_code", {error.code for error in errors})

    def test_publish_catalog_version_supersedes_old_version_and_updates_pointer_atomically(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "publish-success")
            old = self._add_version(db, project, version=1, status="published")
            draft = self._add_version(db, project, version=2)
            group = self._add_group(db, draft, "strength", required=True, min_select=1)
            self._add_choice(db, group, "medium")
            staff = Staff(username="publisher", password_hash="hash", name="发布人", store_id=store.id)
            db.add(staff)
            db.commit()

            published = publish_catalog_version(db, project.id, staff.id)

            self.assertEqual(published.id, draft.id)
            self.assertEqual(published.status, "published")
            self.assertEqual(published.published_by, staff.id)
            self.assertIsNotNone(published.published_at)
            self.assertEqual(len(published.snapshot_hash), 64)
            self.assertEqual(old.status, "superseded")
            self.assertEqual(project.current_published_version_id, draft.id)

    def test_publish_rejects_older_draft_than_current_published_version(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "publish-monotonic")
            current = self._add_version(db, project, version=3, status="published")
            stale = self._add_version(db, project, version=2, status="draft")
            group = self._add_group(db, stale, "preference")
            self._add_choice(db, group, "soft")
            staff = Staff(username="monotonic-publisher", password_hash="hash", name="发布人", store_id=store.id)
            db.add(staff)
            db.commit()

            with self.assertRaises(CatalogPublicationError) as raised:
                publish_catalog_version(db, project.id, staff.id)

            self.assertIn("catalog_version_not_monotonic", {error.code for error in raised.exception.errors})
            self.assertEqual(current.status, "published")
            self.assertEqual(stale.status, "draft")
            self.assertEqual(project.current_published_version_id, current.id)

    def test_published_hash_drift_fails_closed_for_read_and_copy_on_write(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "hash-drift")
            draft = self._add_version(db, project, version=1)
            group = self._add_group(db, draft, "preference")
            choice = self._add_choice(db, group, "soft")
            staff = Staff(username="hash-publisher", password_hash="hash", name="发布人", store_id=store.id)
            db.add(staff)
            db.commit()
            published = publish_catalog_version(db, project.id, staff.id)
            db.commit()

            choice.name = "被篡改的偏好"
            db.commit()

            with self.assertRaises(CatalogDomainError):
                resolve_published_project_config(db, project.id)

            target = self._add_version(db, project, version=2)
            with self.assertRaises(CatalogDomainError):
                copy_catalog_version_graph(db, published.id, target.id)

    def test_linked_published_leaf_is_pinned_even_if_target_later_publishes_catalog(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            parent = self._add_project(db, store, "pinned-parent")
            leaf = self._add_project(db, store, "pinned-leaf")
            db.add(PriceBook(project_id=leaf.id, price_type="store", amount_cents=1_000))
            parent_draft = self._add_version(db, parent, version=1)
            group = self._add_group(db, parent_draft, "link")
            self._add_choice(
                db,
                group,
                "leaf",
                choice_type="linked_project",
                linked_project_id=leaf.id,
                charge_mode="inherit_linked_price",
            )
            staff = Staff(username="leaf-publisher", password_hash="hash", name="发布人", store_id=store.id)
            db.add(staff)
            db.commit()

            self.assertNotIn(
                "linked_project_catalog_unpublished",
                {error.code for error in validate_catalog_version(db, parent_draft.id)},
            )
            publish_catalog_version(db, parent.id, staff.id)
            db.commit()

            leaf_draft = self._add_version(db, leaf, version=1)
            leaf_group = self._add_group(db, leaf_draft, "leaf-preference")
            self._add_choice(db, leaf_group, "warm")
            publish_catalog_version(db, leaf.id, staff.id)
            db.commit()

            config = resolve_published_project_config(db, parent.id)
            linked = config["groups"][0]["choices"][0]
            self.assertIsNone(linked["pinned_linked_catalog_version_id"])
            self.assertIsNone(linked["linked_catalog_version_id"])

    def test_strict_choice_contract_rejects_mixed_rows_in_validation_and_resolver(self):
        from app.domain.membership_pricing import PriceContext, resolve_option_charge

        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "strict-choice-root")
            linked = self._add_project(db, store, "strict-choice-target")
            version = self._add_version(db, project)
            group = self._add_group(db, version, "mixed")
            preference = self._add_choice(
                db,
                group,
                "bad-preference",
                choice_type="preference",
                linked_project_id=linked.id,
                charge_mode="free",
            )
            self._add_store_price(db, preference)
            db.commit()

            codes = {error.code for error in validate_catalog_version(db, version.id)}
            self.assertIn("preference_cannot_link_project", codes)
            self.assertIn("free_choice_cannot_have_prices", codes)
            with self.assertRaises(ValueError):
                resolve_option_charge(db, preference.id, PriceContext(
                    is_member=False,
                    confirmed_at=datetime(2026, 8, 15, tzinfo=UTC),
                    store_timezone="Asia/Shanghai",
                ))

    def test_publication_rejects_overlapping_option_price_intervals(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "overlapping-option-price")
            version = self._add_version(db, project)
            group = self._add_group(db, version, "upgrade")
            choice = self._add_choice(
                db,
                group,
                "hot-pack",
                choice_type="dedicated_charge",
                charge_mode="custom_price",
            )
            start = datetime(2026, 8, 1, tzinfo=UTC)
            db.add_all([
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="store",
                    amount_cents=1000,
                    effective_from=start,
                    effective_to=start + timedelta(days=10),
                ),
                OptionChoicePrice(
                    option_choice_id=choice.id,
                    price_type="store",
                    amount_cents=1200,
                    effective_from=start + timedelta(days=5),
                ),
            ])
            db.commit()

            codes = {error.code for error in validate_catalog_version(db, version.id)}
            self.assertIn("overlapping_option_price_intervals", codes)

    def test_publish_validation_failure_does_not_change_old_publication_or_pointer(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "publish-failure")
            old = self._add_version(db, project, version=1, status="published")
            draft = self._add_version(db, project, version=2)
            self._add_group(db, draft, "empty", required=True, min_select=1)
            staff = Staff(username="failed-publisher", password_hash="hash", name="发布人", store_id=store.id)
            db.add(staff)
            db.commit()

            with self.assertRaises(CatalogPublicationError) as raised:
                publish_catalog_version(db, project.id, staff.id)

            self.assertTrue(any(error.code == "required_group_empty" for error in raised.exception.errors))
            self.assertEqual(old.status, "published")
            self.assertEqual(draft.status, "draft")
            self.assertEqual(project.current_published_version_id, old.id)

    def test_publish_does_not_commit_and_can_be_rolled_back_by_caller(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "publish-rollback")
            old = self._add_version(db, project, version=1, status="published")
            draft = self._add_version(db, project, version=2)
            group = self._add_group(db, draft, "strength")
            self._add_choice(db, group, "soft")
            staff = Staff(username="rollback-publisher", password_hash="hash", store_id=store.id)
            db.add(staff)
            db.commit()
            project_id = project.id
            old_id = old.id
            draft_id = draft.id
            staff_id = staff.id

            publish_catalog_version(db, project_id, staff_id)
            db.rollback()

        with self.SessionLocal() as db:
            project = db.get(Project, project_id)
            old = db.get(ProjectCatalogVersion, old_id)
            draft = db.get(ProjectCatalogVersion, draft_id)
            self.assertEqual(project.current_published_version_id, old_id)
            self.assertEqual(old.status, "published")
            self.assertEqual(draft.status, "draft")
            self.assertEqual(draft.snapshot_hash, "")
            self.assertIsNone(draft.published_at)
            self.assertIsNone(draft.published_by)

    def test_publish_uses_latest_draft_and_reports_missing_project_or_draft(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "latest-draft")
            older = self._add_version(db, project, version=1, status="superseded")
            latest = self._add_version(db, project, version=2)
            staff = Staff(username="latest-publisher", password_hash="hash", store_id=store.id)
            db.add(staff)
            db.commit()

            published = publish_catalog_version(db, project.id, staff.id)

            self.assertEqual(published.id, latest.id)
            self.assertEqual(older.status, "superseded")
            no_draft_project = self._add_project(db, store, "no-draft")
            self._add_version(db, no_draft_project, status="published")
            db.flush()
            with self.assertRaises(CatalogDraftNotFoundError):
                publish_catalog_version(db, no_draft_project.id, staff.id)
            with self.assertRaises(CatalogProjectNotFoundError):
                publish_catalog_version(db, 999999, staff.id)

    def test_snapshot_hash_is_deterministic_when_insertion_order_changes(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "stable-hash")
            first = self._add_version(db, project, version=1)
            first_b = self._add_group(db, first, "b", display_order=2)
            first_a = self._add_group(db, first, "a", display_order=1)
            self._add_choice(db, first_b, "two", display_order=2)
            self._add_choice(db, first_a, "one", display_order=1)
            staff = Staff(username="hash-publisher", password_hash="hash", store_id=store.id)
            db.add(staff)
            db.commit()
            first_published = publish_catalog_version(db, project.id, staff.id)
            first_hash = first_published.snapshot_hash
            db.commit()

            second = self._add_version(db, project, version=2)
            second_a = self._add_group(db, second, "a", display_order=1)
            second_b = self._add_group(db, second, "b", display_order=2)
            self._add_choice(db, second_a, "one", display_order=1)
            self._add_choice(db, second_b, "two", display_order=2)
            db.commit()
            second_published = publish_catalog_version(db, project.id, staff.id)

            self.assertEqual(second_published.snapshot_hash, first_hash)

    def test_resolve_reads_only_pointer_and_returns_stably_sorted_serializable_config(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "resolve-published")
            published = self._add_version(db, project, version=1, status="published")
            group_b = self._add_group(db, published, "b", display_order=2)
            group_a = self._add_group(db, published, "a", display_order=1)
            choice_b = self._add_choice(db, group_a, "b", display_order=2, choice_type="dedicated_charge", charge_mode="custom_price")
            choice_a = self._add_choice(db, group_a, "a", display_order=1)
            self._add_store_price(db, choice_b, amount=2000)
            self._add_store_price(db, choice_a, amount=1000, price_type="member")
            draft = self._add_version(db, project, version=2)
            draft_group = self._add_group(db, draft, "draft-only")
            self._add_choice(db, draft_group, "hidden")
            published.snapshot_hash = _snapshot_hash(db, published.id)
            db.commit()

            config = resolve_published_project_config(db, project.id)

            self.assertEqual(config["catalog_version_id"], published.id)
            self.assertEqual([group["code"] for group in config["groups"]], ["a", "b"])
            self.assertEqual([choice["code"] for choice in config["groups"][0]["choices"]], ["a", "b"])
            self.assertNotIn("draft-only", json.dumps(config, ensure_ascii=False))
            json.dumps(config, ensure_ascii=False)

    def test_resolve_does_not_fallback_to_published_version_without_pointer(self):
        with self.SessionLocal() as db:
            store = self._add_store(db)
            project = self._add_project(db, store, "resolve-no-pointer")
            published = self._add_version(db, project, version=1, status="published")
            project.current_published_version_id = None
            group = self._add_group(db, published, "published")
            self._add_choice(db, group, "visible")
            draft = self._add_version(db, project, version=2)
            draft_group = self._add_group(db, draft, "draft")
            self._add_choice(db, draft_group, "hidden")
            db.commit()

            with self.assertRaises(CatalogPublishedVersionNotFoundError):
                resolve_published_project_config(db, project.id)


if __name__ == "__main__":
    unittest.main()
