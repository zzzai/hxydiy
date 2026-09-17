import unittest
from unittest.mock import AsyncMock, patch

from fastapi.testclient import TestClient

from app.core.config import settings
from app.main import app


class OfficialAccountJssdkTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_jssdk_config_rejects_a_url_outside_the_public_h5_origin(self):
        response = self.client.get(
            "/api/v1/wechat/jssdk-config",
            params={"url": "https://example.invalid/?store=1"},
        )

        self.assertEqual(response.status_code, 422)

    def test_jssdk_config_returns_the_server_signature_for_the_current_h5_page(self):
        signed = {
            "appId": "wx1ded0c963fafbd22",
            "timestamp": 1726387200,
            "nonceStr": "nonce-value",
            "signature": "e40c8d00b4cdeaf6000000000000000000000000",
        }
        with (
            patch.object(settings, "wechat_official_appid", "wx1ded0c963fafbd22"),
            patch.object(settings, "wechat_official_appsecret", "test-secret"),
            patch("app.api.wechat_official.official_wechat_jssdk.config_for_url", new=AsyncMock(return_value=signed)) as configure,
        ):
            response = self.client.get(
                "/api/v1/wechat/jssdk-config",
                params={"url": "https://diy.hexiaoyue.com/?store=1&seat=sofa-06"},
            )

        self.assertEqual(response.status_code, 200, response.text)
        self.assertEqual(response.json(), signed)
        configure.assert_awaited_once_with("https://diy.hexiaoyue.com/?store=1&seat=sofa-06")


if __name__ == "__main__":
    unittest.main()
