import unittest

from sqlalchemy import create_engine
from sqlalchemy.exc import IntegrityError
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base
import app.models as models
from app.models import User


class CustomerIdentityConstraintTests(unittest.TestCase):
    def setUp(self):
        self.engine = create_engine(
            "sqlite://",
            connect_args={"check_same_thread": False},
            poolclass=StaticPool,
        )
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine)

    def tearDown(self):
        self.engine.dispose()

    def test_nonempty_phone_can_only_bind_one_customer(self):
        with self.SessionLocal() as db:
            db.add_all([
                User(openid="phone-owner-one", phone="13800138111"),
                User(openid="phone-owner-two", phone="13800138111"),
            ])

            with self.assertRaises(IntegrityError):
                db.commit()

    def test_empty_phone_does_not_merge_anonymous_customers(self):
        with self.SessionLocal() as db:
            db.add_all([
                User(openid="anonymous-phone-one", phone=""),
                User(openid="anonymous-phone-two", phone=""),
            ])
            db.commit()

            self.assertEqual(db.query(User).filter(User.phone == "").count(), 2)

    def test_external_subject_can_only_map_to_one_customer_per_provider(self):
        identity_model = getattr(models, "CustomerExternalIdentity", None)
        self.assertIsNotNone(identity_model)
        with self.SessionLocal() as db:
            first = User(openid="external-owner-one")
            second = User(openid="external-owner-two")
            db.add_all([first, second])
            db.flush()
            db.add_all([
                identity_model(
                    customer_id=first.id,
                    provider="member_system",
                    external_subject_id="MEMBER-1001",
                ),
                identity_model(
                    customer_id=second.id,
                    provider="member_system",
                    external_subject_id="MEMBER-1001",
                ),
            ])

            with self.assertRaises(IntegrityError):
                db.commit()


if __name__ == "__main__":
    unittest.main()
