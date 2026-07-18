from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.v1.image import get_image_service
from app.api.routes.v1.image import router as image_router


class FakeImageService:
    def create_presigned_download_url(self, *, bucket_name: str, object_key: str) -> str:
        assert bucket_name == "icpc"
        assert object_key == "contest/image.png"
        return "https://minio.example/icpc/contest/image.png?signature=test"


def test_download_image_redirects_to_presigned_url():
    app = FastAPI()
    app.include_router(image_router, prefix="/api/v1")
    app.dependency_overrides[get_image_service] = lambda: FakeImageService()
    client = TestClient(app)

    response = client.get(
        "/api/v1/images/icpc/contest/image.png",
        follow_redirects=False,
    )

    assert response.status_code == 307
    assert response.headers["location"] == (
        "https://minio.example/icpc/contest/image.png?signature=test"
    )
