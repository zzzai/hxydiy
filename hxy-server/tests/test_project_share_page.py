import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.db.session import Base, get_db
from app.main import app
from app.models import Project, Store


class ProjectSharePageTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            primary_store = Store(store_code="share-primary", name="分享门店", address="测试地址")
            secondary_store = Store(store_code="share-secondary", name="另一门店", address="测试地址")
            db.add_all([primary_store, secondary_store])
            db.flush()
            db.add_all([
                Project(
                    store_id=primary_store.id,
                    code="share-published",
                    category="bath",
                    name="草本泡脚 <精选>",
                    summary="现煮草本 & 到店体验",
                    image_url="/assets/projects/share-published.webp",
                    publication_status="published",
                ),
                Project(
                    store_id=primary_store.id,
                    code="share-draft",
                    category="bath",
                    name="草稿项目",
                    publication_status="draft",
                ),
            ])
            db.commit()
            cls.primary_store_id = primary_store.id
            cls.secondary_store_id = secondary_store.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_published_project_share_page_exposes_safe_wechat_card_and_project_redirect(self):
        response = self.client.get("/share/project/share-published", params={"store": self.primary_store_id})

        self.assertEqual(response.status_code, 200, response.text)
        self.assertIn("text/html", response.headers["content-type"])
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn('property="og:title" content="荷小悦 · 草本泡脚 &lt;精选&gt;"', response.text)
        self.assertIn('property="og:description" content="现煮草本 &amp; 到店体验"', response.text)
        self.assertIn('property="og:image" content="https://diy.hexiaoyue.com/assets/projects/share-published.webp"', response.text)
        self.assertIn('property="og:url" content="https://diy.hexiaoyue.com/share/project/share-published?store=', response.text)
        self.assertIn("source=project_share", response.text)
        self.assertIn("project=share-published", response.text)
        self.assertNotIn("seat=", response.text)
        self.assertNotIn("token=", response.text)

    def test_share_page_hides_draft_projects_and_cross_store_requests(self):
        self.assertEqual(self.client.get("/share/project/share-draft", params={"store": self.primary_store_id}).status_code, 404)
        self.assertEqual(self.client.get("/share/project/share-published", params={"store": self.secondary_store_id}).status_code, 404)


if __name__ == "__main__":
    unittest.main()
