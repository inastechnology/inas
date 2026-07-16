import io
import os
import tempfile
import unittest
from unittest.mock import patch

os.environ.setdefault("WORK_DIR", tempfile.mkdtemp())
os.environ.setdefault("TURSO_DATABASE_URL", "x")
os.environ.setdefault("TURSO_AUTH_TOKEN", "x")
os.environ.setdefault("S3_ENDPOINT_URL", "x")
os.environ.setdefault("S3_BUCKET_NAME", "x")
os.environ.setdefault("S3_BUCKET_REGION", "auto")
os.environ.setdefault("S3_ACCESS_KEY", "x")
os.environ.setdefault("S3_SECRET_KEY", "x")
os.environ.setdefault("MQTT_BROKER_URL", "localhost")
os.environ.setdefault("MQTT_BROKER_PORT", "1883")
os.environ.setdefault("MQTT_BROKER_USERNAME", "")
os.environ.setdefault("MQTT_BROKER_PASSWORD", "")
os.environ.setdefault("TIMELAPSE_INTERVAL", "600")

from werkzeug.datastructures import FileStorage  # noqa: E402

from ina_device_hub.field_record_media_service import (  # noqa: E402
    FieldRecordMediaService,
    FieldRecordMediaValidationError,
)


class FakeStorageConnector:
    def __init__(self):
        self.objects = {}
        self.deleted = []

    def save_bytes_to_cloud(self, object_key, image_bytes, content_type):
        self.objects[object_key] = (image_bytes, content_type)
        return object_key

    def fetch_from_cloud_as_bytes(self, object_key):
        stored = self.objects.get(object_key)
        return stored[0] if stored else None

    def delete_from_cloud(self, object_key):
        self.deleted.append(object_key)
        self.objects.pop(object_key, None)


class FieldRecordMediaServiceTest(unittest.TestCase):
    def setUp(self):
        self.connector = FakeStorageConnector()
        self.service = FieldRecordMediaService(self.connector)

    def test_uploads_image_to_r2_key_and_reads_it(self):
        image_bytes = b"\x89PNG\r\n\x1a\n" + b"test-image"
        image = FileStorage(stream=io.BytesIO(image_bytes), filename="leaf.png", content_type="image/png")

        attachments = self.service.upload_images("field-1", "2026-07-14T09:30", [image])

        self.assertEqual(len(attachments), 1)
        attachment = attachments[0]
        self.assertTrue(attachment["object_key"].startswith("field-records/field-1/2026-07-14/"))
        self.assertEqual(attachment["storage"], "r2")
        self.assertEqual(attachment["content_type"], "image/png")
        self.assertEqual(self.service.fetch_image(attachment), image_bytes)

    @patch("ina_device_hub.field_record_media_service.storage_connector")
    def test_no_images_does_not_initialize_cloud_storage(self, connector_factory):
        service = FieldRecordMediaService()

        self.assertEqual(service.upload_images("field-1", "2026-07-16", []), [])
        connector_factory.assert_not_called()

    def test_rejects_non_image_content_even_with_image_filename(self):
        image = FileStorage(stream=io.BytesIO(b"<script>not an image</script>"), filename="fake.png", content_type="image/png")

        with self.assertRaises(FieldRecordMediaValidationError):
            self.service.upload_images("field-1", "2026-07-14", [image])


if __name__ == "__main__":
    unittest.main()
