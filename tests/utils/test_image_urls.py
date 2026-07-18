from datetime import timedelta

from app.core.config import config
from app.utils.image import create_presigned_image_url, image_object_key_to_url


class FakeMinioClient:
    def __init__(self):
        self.calls = []

    def presigned_get_object(self, *, bucket_name, object_name, expires):
        self.calls.append((bucket_name, object_name, expires))
        return f"https://signed.example/{bucket_name}/{object_name}?signature=test"


def test_image_object_key_to_url_returns_stable_backend_url(monkeypatch):
    monkeypatch.setattr(config, "API_PUBLIC_BASE_URL", "https://api.example/api/v1")

    url = image_object_key_to_url("contest/image name.png", bucket_name="icpc")

    assert url == "https://api.example/api/v1/images/icpc/contest/image%20name.png"


def test_image_object_key_to_url_normalizes_direct_minio_urls(monkeypatch):
    monkeypatch.setattr(config, "API_PUBLIC_BASE_URL", "https://api.example/api/v1")
    monkeypatch.setattr(config, "MINIO_HOST", "10.10.10.23")
    monkeypatch.setattr(config, "MINIO_PORT", 9000)
    monkeypatch.setattr(config, "MINIO_PUBLIC_HOST", "minio.example")
    monkeypatch.setattr(config, "MINIO_PUBLIC_PORT", 9443)

    url = image_object_key_to_url(
        "http://10.10.10.23:9000/icpc/contest/image%20name.png?X-Amz-Signature=old"
    )

    assert url == "https://api.example/api/v1/images/icpc/contest/image%20name.png"

    public_url = image_object_key_to_url(
        "http://minio.example:9443/icpc/contest/public%20image.png?X-Amz-Signature=old"
    )

    assert public_url == "https://api.example/api/v1/images/icpc/contest/public%20image.png"


def test_image_object_key_to_url_keeps_existing_external_urls():
    url = "https://cdn.example/image.png"

    assert image_object_key_to_url(url) == url


def test_image_object_key_to_url_returns_none_for_empty_values():
    assert image_object_key_to_url(None) is None
    assert image_object_key_to_url("") is None


def test_create_presigned_image_url_uses_configured_expiry(monkeypatch):
    client = FakeMinioClient()
    monkeypatch.setattr("app.utils.image.get_minio_presign_client", lambda: client)
    monkeypatch.setattr(config, "MINIO_PRESIGNED_URL_EXPIRY_SECONDS", 900)

    url = create_presigned_image_url("icpc", "contest/image.png")

    assert url == "https://signed.example/icpc/contest/image.png?signature=test"
    assert client.calls == [("icpc", "contest/image.png", timedelta(seconds=900))]
