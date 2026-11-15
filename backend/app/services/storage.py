import os
import time
from abc import ABC, abstractmethod
from pathlib import Path
from typing import Optional
import boto3
from botocore.client import Config
from botocore.exceptions import ClientError, EndpointConnectionError
from app.core.config import settings
from app.core.logging import get_logger

logger = get_logger("storage")


class StorageService(ABC):
    @abstractmethod
    def put_file(self, key: str, data: bytes) -> str:
        """Stores file bytes under key and returns key."""
        pass

    @abstractmethod
    def get_file(self, key: str) -> bytes:
        """Retrieves file bytes for key."""
        pass

    @abstractmethod
    def delete_file(self, key: str) -> None:
        """Deletes file for key."""
        pass

    @abstractmethod
    def exists(self, key: str) -> bool:
        """Checks if key exists."""
        pass

    @abstractmethod
    def check_health(self) -> bool:
        """Verifies storage backend health."""
        pass


class LocalStorage(StorageService):
    def __init__(self, base_dir: Optional[str] = None):
        raw_dir = base_dir or settings.LOCAL_STORAGE_DIR
        # Ensure cross-platform compatibility on Windows where /tmp is not writable
        if os.name == "nt" and (raw_dir.startswith("/tmp") or raw_dir.startswith("\\tmp")):
            import tempfile
            self.base_dir = Path(tempfile.gettempdir()) / "algorevive-storage"
        else:
            self.base_dir = Path(raw_dir)
        self.base_dir.mkdir(parents=True, exist_ok=True)

    def _get_path(self, key: str) -> Path:
        # Sanitize key and resolve relative to base_dir
        clean_key = key.lstrip("/\\")
        path = (self.base_dir / clean_key).resolve()
        if not str(path).startswith(str(self.base_dir.resolve())):
            raise ValueError("Path traversal attempt in storage key")
        return path

    def put_file(self, key: str, data: bytes) -> str:
        path = self._get_path(key)
        path.parent.mkdir(parents=True, exist_ok=True)
        path.write_bytes(data)
        return key

    def get_file(self, key: str) -> bytes:
        path = self._get_path(key)
        if not path.is_file():
            raise FileNotFoundError(f"Storage key not found: {key}")
        return path.read_bytes()

    def delete_file(self, key: str) -> None:
        path = self._get_path(key)
        if path.exists():
            path.unlink()

    def exists(self, key: str) -> bool:
        path = self._get_path(key)
        return path.is_file()

    def check_health(self) -> bool:
        try:
            test_file = self.base_dir / ".health_check"
            test_file.write_text("ok", encoding="utf-8")
            if test_file.exists():
                test_file.unlink()
                return True
            return False
        except Exception as e:
            logger.error(f"LocalStorage health check failed: {e}")
            return False


class S3Storage(StorageService):
    def __init__(self):
        self.bucket = settings.S3_BUCKET
        self.s3_client = boto3.client(
            "s3",
            endpoint_url=settings.S3_ENDPOINT_URL,
            aws_access_key_id=settings.S3_ACCESS_KEY,
            aws_secret_access_key=settings.S3_SECRET_KEY,
            config=Config(signature_version="s3v4"),
            region_name="us-east-1",
        )
        self._ensure_bucket_with_retry()

    def _ensure_bucket_with_retry(self, max_retries: int = 5, delay: float = 1.0) -> None:
        for attempt in range(1, max_retries + 1):
            try:
                self.s3_client.head_bucket(Bucket=self.bucket)
                logger.info(f"S3 bucket '{self.bucket}' exists and is accessible.")
                return
            except ClientError as e:
                error_code = e.response.get("Error", {}).get("Code")
                if error_code in ("404", "NoSuchBucket"):
                    try:
                        self.s3_client.create_bucket(Bucket=self.bucket)
                        logger.info(f"Created S3 bucket '{self.bucket}'.")
                        return
                    except Exception as create_err:
                        logger.warning(f"Could not create bucket '{self.bucket}': {create_err}")
                else:
                    logger.warning(f"S3 head_bucket error ({error_code}) on attempt {attempt}: {e}")
            except (EndpointConnectionError, Exception) as e:
                logger.warning(f"S3 connection attempt {attempt} failed: {e}")

            if attempt < max_retries:
                time.sleep(delay * attempt)
        logger.error(f"Failed to ensure S3 bucket '{self.bucket}' after {max_retries} attempts.")

    def put_file(self, key: str, data: bytes) -> str:
        clean_key = key.lstrip("/")
        self.s3_client.put_object(
            Bucket=self.bucket,
            Key=clean_key,
            Body=data,
        )
        return key

    def get_file(self, key: str) -> bytes:
        clean_key = key.lstrip("/")
        try:
            response = self.s3_client.get_object(Bucket=self.bucket, Key=clean_key)
            return response["Body"].read()
        except ClientError as e:
            if e.response.get("Error", {}).get("Code") == "NoSuchKey":
                raise FileNotFoundError(f"Storage key not found: {key}")
            raise

    def delete_file(self, key: str) -> None:
        clean_key = key.lstrip("/")
        self.s3_client.delete_object(Bucket=self.bucket, Key=clean_key)

    def exists(self, key: str) -> bool:
        clean_key = key.lstrip("/")
        try:
            self.s3_client.head_object(Bucket=self.bucket, Key=clean_key)
            return True
        except ClientError:
            return False

    def check_health(self) -> bool:
        try:
            self.s3_client.head_bucket(Bucket=self.bucket)
            return True
        except Exception as e:
            logger.error(f"S3Storage health check failed: {e}")
            return False


_storage_instance: Optional[StorageService] = None


def get_storage_service() -> StorageService:
    global _storage_instance
    if _storage_instance is None:
        if settings.STORAGE_BACKEND == "s3":
            try:
                _storage_instance = S3Storage()
            except Exception as e:
                logger.warning(f"Could not initialize S3 storage ({e}), falling back to LocalStorage.")
                _storage_instance = LocalStorage()
        else:
            _storage_instance = LocalStorage()
    return _storage_instance
