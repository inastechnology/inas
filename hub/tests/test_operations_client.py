import io
import json
import sys
import unittest
from email.message import Message
from pathlib import Path
from unittest.mock import Mock
from urllib.error import HTTPError, URLError

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "scripts/operations"))

from common.api_client import OperationsApiClient, OperationsApiError, _RejectRedirects  # noqa: E402
from fields.read_client import FieldReadClient  # noqa: E402


class OperationsClientTest(unittest.TestCase):
    def setUp(self):
        self.settings = {
            "INAS_HUB_OPERATIONS_URL": "https://hub.example.com/operations/api/v1",
            "CF_ACCESS_CLIENT_ID": "test-client",
            "CF_ACCESS_CLIENT_SECRET": "test-secret",
        }
        self.api = OperationsApiClient(self.settings)
        self.opener = Mock()
        self.api.opener = self.opener
        self.reader = FieldReadClient(self.api)

    def response(self, data, content_type):
        stream = io.BytesIO(data)
        stream.headers = Message()
        stream.headers["Content-Type"] = content_type
        self.opener.open.return_value = stream

    def test_only_https_operations_base_is_accepted(self):
        for url in (
            "http://hub.example.com/operations/api/v1",
            "https://hub.example.com/local/api",
            "https://person:secret@hub.example.com/operations/api/v1",
            "https://hub.example.com/operations/api/v1?token=x",
            "https://hub.example.com/operations/api/v1#fragment",
        ):
            with self.subTest(url=url), self.assertRaises(OperationsApiError):
                OperationsApiClient({**self.settings, "INAS_HUB_OPERATIONS_URL": url})

    def test_query_encoding_and_machine_headers(self):
        self.response(json.dumps({"items": []}).encode(), "application/json")
        self.assertEqual(self.reader.search_records("field-a", query="葉 & fruit"), {"items": []})
        request = self.opener.open.call_args.args[0]
        self.assertIn("q=%E8%91%89+%26+fruit", request.full_url)
        self.assertEqual(request.get_header("Cf-access-client-secret"), "test-secret")
        self.assertEqual(request.get_method(), "GET")

    def test_binary_image_is_returned_with_mime_type(self):
        self.response(b"\x89PNG\r\n\x1a\nleaf", "image/png")
        data, content_type = self.reader.record_image("field-a", "image-a")
        self.assertTrue(data.startswith(b"\x89PNG"))
        self.assertEqual(content_type, "image/png")

    def test_arbitrary_urls_and_traversal_are_never_requested(self):
        for value in ("https://other.example/secret", "../secrets", "%2e%2e/private", "//other.example/secret", "..\\private"):
            with self.subTest(value=value), self.assertRaises(OperationsApiError):
                self.api.get(value)
        for value in ("../other", "field/a", "%2e%2e", "https://example.com"):
            with self.subTest(value=value), self.assertRaises(OperationsApiError):
                self.reader.record_image("field-a", value)
        self.opener.open.assert_not_called()

    def test_redirects_are_refused_and_error_bodies_are_not_exposed(self):
        handler = _RejectRedirects()
        self.assertIsNone(handler.redirect_request(None, None, 302, "redirect", {}, "https://login.example"))
        for status in (302, 401, 403, 502):
            self.opener.open.side_effect = HTTPError("https://private.example", status, "test-secret", {}, io.BytesIO(b"test-secret private body"))
            with self.subTest(status=status), self.assertRaises(OperationsApiError) as raised:
                self.api.get("health")
            self.assertIn(str(status), str(raised.exception))
            self.assertNotIn("test-secret", str(raised.exception))
            self.assertNotIn("private", str(raised.exception))

    def test_connection_error_details_are_not_exposed(self):
        self.opener.open.side_effect = URLError("test-secret private URL")
        with self.assertRaises(OperationsApiError) as raised:
            self.api.get("health")
        self.assertEqual(str(raised.exception), "Operations API connection failed")

    def test_non_json_and_non_image_responses_are_rejected(self):
        self.response(b"<html>Login</html>", "text/html")
        with self.assertRaises(OperationsApiError):
            self.api.get("health")
        self.response(b"<html>Login</html>", "text/html")
        with self.assertRaises(OperationsApiError):
            self.reader.record_image("field-a", "photo-a")

    def test_response_size_is_bounded(self):
        self.response(b"x" * (2 * 1024 * 1024 + 1), "application/json")
        with self.assertRaisesRegex(OperationsApiError, "size limit"):
            self.api.get("fields")
        self.response(b"x" * (10 * 1024 * 1024 + 1), "image/jpeg")
        with self.assertRaisesRegex(OperationsApiError, "size limit"):
            self.reader.camera_image("field-a", "camera-a", "20260923_080000")

    def test_existing_firmware_publication_still_posts_binary(self):
        self.response(b'{"sha256":"value"}', "application/json")
        self.api.post_binary("devices/firmware-artifacts/WTR/1.0.0", b"firmware")
        request = self.opener.open.call_args.args[0]
        self.assertEqual(request.data, b"firmware")
        self.assertEqual(request.get_method(), "POST")


if __name__ == "__main__":
    unittest.main()
