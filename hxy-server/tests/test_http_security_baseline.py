import unittest

from fastapi.testclient import TestClient

from app.main import app


class HttpSecurityBaselineTests(unittest.TestCase):
    @classmethod
    def setUpClass(cls):
        cls.client = TestClient(app)

    @classmethod
    def tearDownClass(cls):
        cls.client.close()

    def test_customer_api_returns_browser_security_headers_and_never_caches(self):
        response = self.client.get("/api/v1/health")

        self.assertEqual(response.status_code, 200)
        self.assertEqual(response.headers["x-content-type-options"], "nosniff")
        self.assertEqual(response.headers["referrer-policy"], "strict-origin-when-cross-origin")
        self.assertEqual(response.headers["x-frame-options"], "SAMEORIGIN")
        self.assertEqual(response.headers["cache-control"], "no-store")
        self.assertIn("default-src 'self'", response.headers["content-security-policy"])
        self.assertIn("object-src 'none'", response.headers["content-security-policy"])
        self.assertIn("script-src 'self'", response.headers["content-security-policy"])


if __name__ == "__main__":
    unittest.main()
