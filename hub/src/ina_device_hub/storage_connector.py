import os
import time
import boto3
from urllib.parse import quote

from ina_device_hub.setting import setting
from ina_device_hub.general_log import logger


class StorageConnector:
    """
    StorageConnector provides saving and fetching helpers for cloud storage.

    Attributes:
    LOCAL_STORAGE_BASE_DIR: str - The base directory for saving files.
    s3: boto3.client - The boto3 client for S3.

    Methods:
    save_to_cloud: str - Saves the file to cloud storage.
    fetch_from_cloud_as_bytes: str - Fetches the file from cloud storage.

    """

    LOCAL_STORAGE_BASE_DIR = f"{setting().get('local_storage_base_dir')}"

    def __init__(self):
        if not os.path.exists(self.LOCAL_STORAGE_BASE_DIR):
            os.makedirs(self.LOCAL_STORAGE_BASE_DIR)

        self.s3 = self._create_s3_client(setting().get("storage_bucket"))
        self.tmp_s3 = self._create_optional_s3_client(setting().get("temporary_storage_bucket"))

    def _create_s3_client(self, bucket_settings: dict):
        return boto3.client(
            "s3",
            endpoint_url=bucket_settings.get("endpoint_url"),
            aws_access_key_id=bucket_settings.get("access_key"),
            aws_secret_access_key=bucket_settings.get("secret_key"),
            region_name=bucket_settings.get("region"),
        )

    def _create_optional_s3_client(self, bucket_settings: dict):
        if not bucket_settings:
            return None
        required_values = [
            bucket_settings.get("endpoint_url"),
            bucket_settings.get("bucket_name"),
            bucket_settings.get("access_key"),
            bucket_settings.get("secret_key"),
        ]
        if not all(required_values):
            return None
        return self._create_s3_client(bucket_settings)

    def save_to_cloud(self, file_key, fileBytes, content_type="image/jpeg"):
        """
        Saves the file to cloud storage.
        Automatically generates the file path based on the file key and UTC.
        e.g.) {tenant_id}/{file_key}/{yyyymmdd}/{yyyymmdd_hhmmss}.jpg
        """
        file_path = self.get_file_path(file_key)
        return self.save_bytes_to_cloud(file_path, fileBytes, content_type)

    def save_bytes_to_cloud(self, file_path, fileBytes, content_type="image/jpeg"):
        try:
            self._put_object(
                self.s3,
                setting().get("storage_bucket").get("bucket_name"),
                file_path,
                fileBytes,
                content_type,
            )
            logger.info(f"Image uploaded to {file_path}({len(fileBytes)} bytes)")
        except Exception as e:
            print(f"Error: {e}")
            return None
        return file_path

    def save_bytes_to_temporary_cloud(self, file_path, fileBytes, content_type="application/octet-stream"):
        if self.tmp_s3 is None:
            raise ValueError("temporary storage bucket is not configured")

        bucket_name = setting().get("temporary_storage_bucket").get("bucket_name")
        try:
            self._put_object(
                self.tmp_s3,
                bucket_name,
                file_path,
                fileBytes,
                content_type,
            )
            logger.info(f"Temporary object uploaded to {file_path}({len(fileBytes)} bytes)")
        except Exception as e:
            print(f"Error: {e}")
            return None
        return file_path

    def _put_object(self, client, bucket_name, file_path, fileBytes, content_type):
        # TODO: [Multi-tenancy] Generate the bucket name from tenant_id.
        client.put_object(
            Bucket=bucket_name,
            Key=file_path,
            Body=fileBytes,
            ContentType=content_type,
        )

    def save_to_local(self, file_key, fileBytes):
        file_path = os.path.join(
            self.LOCAL_STORAGE_BASE_DIR,
            self.get_file_path(file_key),
        )
        file_dir = os.path.dirname(file_path)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
        with open(file_path, "wb") as f:
            f.write(fileBytes)

        return file_path

    def save_bytes_to_local_path(self, relative_path: str, fileBytes):
        file_path = os.path.join(self.LOCAL_STORAGE_BASE_DIR, relative_path)
        file_dir = os.path.dirname(file_path)
        if not os.path.exists(file_dir):
            os.makedirs(file_dir)
        with open(file_path, "wb") as file:
            file.write(fileBytes)
        return file_path

    def fetch_from_cloud_as_bytes(self, file_full_key):
        try:
            # TODO: [Multi-tenancy] Generate the bucket name from tenant_id.
            response = self.s3.get_object(
                Bucket=setting().get("storage_bucket").get("bucket_name"),
                Key=file_full_key,
            )
            return response["Body"].read()
        except Exception as e:
            print(f"Error: {e}")
            return None

    def get_file_dir(self, file_key):
        yyyymmdd = time.strftime("%Y%m%d", time.gmtime())
        return os.path.join(setting().get("tenant_id"), file_key, yyyymmdd)

    def get_file_path(self, file_key):
        return os.path.join(
            self.get_file_dir(file_key),
            time.strftime("%Y%m%d_%H%M%S", time.gmtime()) + ".jpg",
        )

    def is_temporary_storage_configured(self):
        tmp_bucket = setting().get("temporary_storage_bucket")
        return bool(self.tmp_s3 and tmp_bucket.get("base_url"))

    def get_temporary_public_url(self, file_path: str):
        base_url = setting().get("temporary_storage_bucket").get("base_url", "")
        if not base_url:
            return None
        normalized_base = base_url.rstrip("/")
        normalized_path = "/".join(quote(part) for part in file_path.split(os.sep))
        return f"{normalized_base}/{normalized_path}"


# singleton instance
__instance = None


def storage_connector():
    global __instance
    if not __instance:
        __instance = StorageConnector()
    return __instance
