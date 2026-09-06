from datetime import datetime, timezone

from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import hash_password
from app.db.session import Base
from app.models import CustomerProfileRecord, Staff, Store, User
from app.services.customer_profile_projection import rebuild_customer_profile_current


class TestCustomerProfileProjection:
    def setup_method(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        self.SessionLocal = sessionmaker(bind=self.engine, expire_on_commit=False)
        Base.metadata.create_all(self.engine)
        with self.SessionLocal() as db:
            store = Store(store_code="projection-store", name="投影测试店", address="测试地址")
            customer = User(openid="projection-customer")
            db.add_all([store, customer])
            db.flush()
            staff = Staff(
                username="projection-manager",
                password_hash=hash_password("pass"),
                name="店长",
                role="manager",
                status="active",
                store_id=store.id,
            )
            db.add(staff)
            db.commit()
            self.store_id = store.id
            self.customer_id = customer.id
            self.staff_id = staff.id

    def teardown_method(self):
        self.engine.dispose()

    def _record(self, db, *, profile, confirmed=True, confirmed_at=None, correction_of_id=None):
        record = CustomerProfileRecord(
            store_id=self.store_id,
            user_id=self.customer_id,
            created_by_staff_id=self.staff_id,
            source="both" if confirmed else "service_observation",
            schema_version=3,
            taxonomy_version="service_reference_v2",
            customer_confirmed=confirmed,
            confirmed_at=confirmed_at,
            profile=profile,
            signals=[],
            note="",
            correction_of_id=correction_of_id,
        )
        db.add(record)
        db.flush()
        return record

    def test_rebuild_keeps_only_confirmed_safe_customer_values(self):
        confirmed_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            self._record(db, confirmed_at=confirmed_at, profile={
                "schema_version": 3,
                "taxonomy_version": "service_reference_v2",
                "customer_reported": {
                    "force_preference": "medium",
                    "service_related_context": {
                        "contexts": ["medication_mentioned"],
                        "quote": "顾客自述正在用药",
                    },
                },
                "technician_observed": {"service_feedback": "suitable"},
            })
            self._record(db, confirmed=False, profile={
                "schema_version": 3,
                "taxonomy_version": "service_reference_v2",
                "customer_reported": {"force_preference": "strong"},
            })
            db.commit()

            rows = rebuild_customer_profile_current(
                db,
                customer_id=self.customer_id,
                store_id=self.store_id,
                now=datetime(2026, 9, 7, tzinfo=timezone.utc),
            )

            assert [(row.profile_code, row.profile_value_key) for row in rows] == [
                ("force_preference", "medium"),
            ]
            assert rows[0].valid_until == datetime(2027, 3, 5, tzinfo=timezone.utc)

    def test_confirmed_correction_replaces_prior_record_and_unconfirmed_correction_clears_it(self):
        confirmed_at = datetime(2026, 9, 6, tzinfo=timezone.utc)
        with self.SessionLocal() as db:
            original = self._record(db, confirmed_at=confirmed_at, profile={
                "schema_version": 3,
                "taxonomy_version": "service_reference_v2",
                "customer_reported": {"force_preference": "medium"},
            })
            correction = self._record(
                db,
                confirmed_at=datetime(2026, 9, 7, tzinfo=timezone.utc),
                correction_of_id=original.id,
                profile={
                    "schema_version": 3,
                    "taxonomy_version": "service_reference_v2",
                    "customer_reported": {"force_preference": "gentle"},
                },
            )
            db.commit()

            rows = rebuild_customer_profile_current(db, customer_id=self.customer_id, store_id=self.store_id)
            assert [(row.profile_code, row.profile_value_key) for row in rows] == [
                ("force_preference", "gentle"),
            ]

            self._record(
                db,
                confirmed=False,
                correction_of_id=correction.id,
                profile={
                    "schema_version": 3,
                    "taxonomy_version": "service_reference_v2",
                    "customer_reported": {"force_preference": "strong"},
                },
            )
            db.commit()

            assert rebuild_customer_profile_current(db, customer_id=self.customer_id, store_id=self.store_id) == []

    def test_explicit_empty_multi_value_replaces_prior_values_without_erasing_other_codes(self):
        with self.SessionLocal() as db:
            self._record(db, confirmed_at=datetime(2026, 9, 6, tzinfo=timezone.utc), profile={
                "schema_version": 3,
                "taxonomy_version": "service_reference_v2",
                "customer_reported": {
                    "focus_areas": ["neck_shoulder", "legs"],
                    "force_preference": "medium",
                },
            })
            self._record(db, confirmed_at=datetime(2026, 9, 7, tzinfo=timezone.utc), profile={
                "schema_version": 3,
                "taxonomy_version": "service_reference_v2",
                "customer_reported": {"focus_areas": []},
            })
            db.commit()

            rows = rebuild_customer_profile_current(db, customer_id=self.customer_id, store_id=self.store_id)

            assert {(row.profile_code, row.profile_value_key) for row in rows} == {
                ("force_preference", "medium"),
            }
