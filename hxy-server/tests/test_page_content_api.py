import unittest

from fastapi.testclient import TestClient
from sqlalchemy import create_engine
from sqlalchemy.orm import sessionmaker
from sqlalchemy.pool import StaticPool

from app.api.admin import create_staff_token, hash_password
from app.db.session import Base, get_db
from app.main import app
from app.models import PageContent, Staff, Store


class PageContentApiTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.engine = create_engine("sqlite://", connect_args={"check_same_thread": False}, poolclass=StaticPool)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, expire_on_commit=False)
        Base.metadata.create_all(cls.engine)
        with cls.SessionLocal() as db:
            store = Store(store_code="page-content-store", name="页面内容门店", address="测试地址")
            db.add(store)
            db.flush()
            staff = Staff(username="page-content-admin", name="管理员", role="admin", status="active", password_hash=hash_password("pass"), store_id=store.id)
            db.add(staff)
            db.commit()
            cls.store_id = store.id
            cls.staff_id = staff.id

        def override_get_db():
            db = cls.SessionLocal()
            try:
                yield db
            finally:
                db.close()

        app.dependency_overrides[get_db] = override_get_db
        cls.client = TestClient(app)
        cls.headers = {"Authorization": f"Bearer {create_staff_token(cls.staff_id, 'admin')}"}

    @classmethod
    def tearDownClass(cls):
        cls.client.close()
        app.dependency_overrides.clear()
        cls.engine.dispose()

    def test_public_content_returns_defaults_and_hides_draft(self):
        response = self.client.get(f"/api/v1/stores/{self.store_id}/page-content", params={"page_key": "diy-home-defaults"})
        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.json()["page_key"], "diy-home-defaults")
        self.assertEqual(len(response.json()["tea_options"]), 3)
        self.assertEqual(response.json()["published"], True)

        with self.SessionLocal() as db:
            db.add(PageContent(store_id=self.store_id, page_key="diy-home-defaults", published=False, title="草稿标题"))
            db.commit()
        response = self.client.get(f"/api/v1/stores/{self.store_id}/page-content", params={"page_key": "diy-home-defaults"})
        self.assertNotEqual(response.json()["title"], "草稿标题")

    def test_admin_can_publish_content_for_its_store(self):
        response = self.client.put(
            "/api/v1/admin/v2/page-content",
            params={"page_key": "diy-home"},
            headers=self.headers,
            json={
                "title": "到店服务选单",
                "subtitle": "按需要，自由搭配",
                "published": True,
                "tea_options": [{"name": "桂花茶", "note": "清香", "description": "桂花清香"}],
                "promo_banners": [{"eyebrow": "今日推荐", "title": "草本泡脚", "project_code": "hxy-qiqing-30"}],
                "coupon_prompt": {"title": "登录领取到店礼", "body": "手机号登录后领取"},
                "brand_story": {"title": "把服务做到身边", "body": "从真实需求出发"},
            },
        )
        self.assertEqual(response.status_code, 200, response.text)
        result = self.client.get(f"/api/v1/stores/{self.store_id}/page-content", params={"page_key": "diy-home"})
        self.assertEqual(result.json()["title"], "到店服务选单")
        self.assertEqual(result.json()["tea_options"][0]["name"], "桂花茶")

    def test_public_content_falls_back_when_published_value_contains_placeholder_question_marks(self):
        with self.SessionLocal() as db:
            db.add(PageContent(
                store_id=self.store_id,
                page_key="diy-home-placeholders",
                published=True,
                title="?????",
                subtitle="????????",
                promo_banners=[{"eyebrow": "????", "title": "????"}],
                tea_options=[{"name": "???", "note": "????", "description": "????????"}],
                coupon_prompt={"title": "????", "body": "????"},
                brand_story={"title": "????", "body": "????"},
            ))
            db.commit()

        result = self.client.get(
            f"/api/v1/stores/{self.store_id}/page-content",
            params={"page_key": "diy-home-placeholders"},
        ).json()

        self.assertEqual(result["title"], "到店服务选单")
        self.assertEqual(result["tea_options"][0]["name"], "老姜茶")
        self.assertEqual(result["coupon_prompt"]["title"], "登录领取到店礼")
        self.assertNotIn("?", str(result))

    def test_public_content_upgrades_legacy_customer_copy(self):
        with self.SessionLocal() as db:
            db.add(PageContent(
                store_id=self.store_id,
                page_key="diy-home-legacy-copy",
                published=True,
                title="到店选项目",
                coupon_prompt={"title": "登录领取到店礼", "body": "手机号登录后领取，优惠券保存到账号"},
            ))
            db.commit()

        result = self.client.get(
            f"/api/v1/stores/{self.store_id}/page-content",
            params={"page_key": "diy-home-legacy-copy"},
        ).json()

        self.assertEqual(result["title"], "到店服务选单")
        self.assertEqual(result["coupon_prompt"]["body"], "手机号登录后保存到账号，符合条件后预计自动抵扣")


if __name__ == "__main__":
    unittest.main()
