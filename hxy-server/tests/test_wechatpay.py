import base64
import json
import time
import unittest
from unittest import mock

from cryptography.hazmat.primitives import hashes
from cryptography.hazmat.primitives.asymmetric import padding, rsa
from cryptography.hazmat.primitives.ciphers.aead import AESGCM

from app.services import wechatpay


class WechatPaySignatureTests(unittest.IsolatedAsyncioTestCase):
    def setUp(self):
        self.private_key = rsa.generate_private_key(public_exponent=65537, key_size=2048)
        self.public_key = self.private_key.public_key()
        self.public_key_id = "PUB_KEY_ID_3000000001"
        self.api_v3_key = "0123456789abcdef0123456789abcdef"

    def _sign(self, message: str) -> str:
        signature = self.private_key.sign(
            message.encode("utf-8"),
            padding.PKCS1v15(),
            hashes.SHA256(),
        )
        return base64.b64encode(signature).decode()

    @mock.patch.object(wechatpay, "_load_public_key")
    def test_response_signature_uses_wechatpay_headers_and_timestamp_nonce_body(
        self,
        load_public_key,
    ):
        load_public_key.return_value = self.public_key
        timestamp = str(int(time.time()))
        nonce = "response-nonce"
        body = '{"prepay_id":"wx-test"}'
        message = f"{timestamp}\n{nonce}\n{body}\n"
        headers = {
            "Wechatpay-Serial": self.public_key_id,
            "Wechatpay-Timestamp": timestamp,
            "Wechatpay-Nonce": nonce,
            "Wechatpay-Signature": self._sign(message),
        }

        with mock.patch.object(wechatpay.settings, "wxpay_public_key_id", self.public_key_id):
            wechatpay._verify_response_signature(headers, body)

    @mock.patch.object(wechatpay, "_load_public_key")
    async def test_notify_uses_wechatpay_headers_and_decrypts_resource(
        self,
        load_public_key,
    ):
        load_public_key.return_value = self.public_key
        plaintext = json.dumps({
            "trade_state": "SUCCESS",
            "out_trade_no": "HXY202608220001",
            "transaction_id": "wx-transaction-1",
        }).encode("utf-8")
        nonce_bytes = b"notify-nonce"
        associated_data = b"transaction"
        ciphertext = AESGCM(self.api_v3_key.encode("utf-8")).encrypt(
            nonce_bytes,
            plaintext,
            associated_data,
        )
        raw_body = json.dumps({
            "resource": {
                "algorithm": "AEAD_AES_256_GCM",
                "ciphertext": base64.b64encode(ciphertext).decode(),
                "nonce": nonce_bytes.decode(),
                "associated_data": associated_data.decode(),
            }
        }, separators=(",", ":")).encode("utf-8")
        timestamp = str(int(time.time()))
        nonce = "header-nonce"
        message = f"{timestamp}\n{nonce}\n{raw_body.decode('utf-8')}\n"
        headers = {
            "wechatpay-serial": self.public_key_id,
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": nonce,
            "wechatpay-signature": self._sign(message),
        }

        with (
            mock.patch.object(wechatpay.settings, "wxpay_public_key_id", self.public_key_id),
            mock.patch.object(wechatpay.settings, "wxpay_apiv3_key", self.api_v3_key),
            mock.patch.object(wechatpay.settings, "wxpay_mchid", "1900000001"),
            mock.patch.object(wechatpay.settings, "wxpay_cert_serial_no", "SERIAL"),
            mock.patch.object(wechatpay.settings, "wxpay_private_key_path", "/tmp/private.pem"),
            mock.patch.object(wechatpay.settings, "wxpay_public_key_path", "/tmp/public.pem"),
            mock.patch.object(wechatpay.settings, "wxpay_appid", "wx-test"),
            mock.patch.object(wechatpay.settings, "wxpay_notify_url", "https://example.com/notify"),
        ):
            payload = await wechatpay.verify_and_decrypt_notify(headers, raw_body)

        self.assertEqual(payload["trade_state"], "SUCCESS")
        self.assertEqual(payload["out_trade_no"], "HXY202608220001")

    @mock.patch.object(wechatpay, "_load_public_key")
    def test_response_signature_failure_is_not_silently_accepted(self, load_public_key):
        load_public_key.return_value = self.public_key
        timestamp = str(int(time.time()))
        headers = {
            "wechatpay-serial": self.public_key_id,
            "wechatpay-timestamp": timestamp,
            "wechatpay-nonce": "nonce",
            "wechatpay-signature": base64.b64encode(b"invalid").decode(),
        }

        with mock.patch.object(wechatpay.settings, "wxpay_public_key_id", self.public_key_id):
            with self.assertRaisesRegex(wechatpay.WechatPayError, "响应验签失败"):
                wechatpay._verify_response_signature(headers, "{}")

    def test_configuration_requires_appid_and_notify_url(self):
        with (
            mock.patch.object(wechatpay.settings, "wxpay_mchid", "1900000001"),
            mock.patch.object(wechatpay.settings, "wxpay_apiv3_key", self.api_v3_key),
            mock.patch.object(wechatpay.settings, "wxpay_cert_serial_no", "SERIAL"),
            mock.patch.object(wechatpay.settings, "wxpay_private_key_path", "/tmp/private.pem"),
            mock.patch.object(wechatpay.settings, "wxpay_public_key_id", self.public_key_id),
            mock.patch.object(wechatpay.settings, "wxpay_public_key_path", "/tmp/public.pem"),
            mock.patch.object(wechatpay.settings, "wxpay_appid", ""),
            mock.patch.object(wechatpay.settings, "wxpay_notify_url", ""),
        ):
            with self.assertRaisesRegex(wechatpay.WechatPayError, "WXPAY_APPID.*WXPAY_NOTIFY_URL"):
                wechatpay._ensure_configured()


if __name__ == "__main__":
    unittest.main()
