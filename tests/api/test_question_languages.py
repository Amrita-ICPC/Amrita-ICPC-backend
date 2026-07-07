"""Tests for the Judge0 languages route and its authorization."""

from unittest.mock import AsyncMock

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import setup_exception_handlers
from app.api.routes.v1.question import get_question_service
from app.api.routes.v1.question import router as question_router
from app.auth.dependencies import get_current_user, require_admin
from app.exceptions.auth import PermissionDeniedError
from app.exceptions.question import (
    InvalidQuestionError,
    Judge0ServiceError,
    LanguageNotFoundError,
)
from app.schema.question import Judge0LanguageResponse

# Create mock response list
MOCK_LANGUAGES = [
    Judge0LanguageResponse(id=50, name="C (GCC 9.2.0)"),
    Judge0LanguageResponse(id=54, name="C++ (GCC 9.2.0)"),
]


@pytest.fixture
def mock_service():
    """Mock QuestionService with default language listings."""
    service = AsyncMock()
    service.get_judge0_languages.return_value = MOCK_LANGUAGES
    service.get_unmapped_judge0_languages.return_value = MOCK_LANGUAGES
    return service


@pytest.fixture
def client(mock_service):
    """FastAPI TestClient with overridden service and admin dependencies."""
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(question_router, prefix="/api/v1/questions")

    # Override standard service injection
    app.dependency_overrides[get_question_service] = lambda: mock_service
    # Override get_current_user dependency
    app.dependency_overrides[get_current_user] = lambda: {
        "sub": "admin-id",
        "groups": ["admin"],
    }
    # Override require_admin dependency to return mock user
    app.dependency_overrides[require_admin] = lambda: {
        "sub": "admin-id",
        "groups": ["admin"],
    }

    return TestClient(app)


class TestGetJudge0LanguagesRoute:
    def test_get_languages_success(self, client, mock_service):
        """Verify that an admin can successfully fetch Judge0 languages."""
        response = client.get("/api/v1/questions/languages/judge0")
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert len(body["data"]) == 2
        assert body["data"][0]["id"] == 50
        assert body["data"][0]["name"] == "C (GCC 9.2.0)"
        assert body["data"][1]["id"] == 54
        assert body["data"][1]["name"] == "C++ (GCC 9.2.0)"

        mock_service.get_unmapped_judge0_languages.assert_awaited_once()

    def test_get_languages_unauthorized(self, client):
        """Verify that when require_admin raises PermissionDeniedError, a 403 status code is returned."""

        def mock_require_admin_fail():
            raise PermissionDeniedError("Admin privileges required")

        client.app.dependency_overrides[require_admin] = mock_require_admin_fail

        response = client.get("/api/v1/questions/languages/judge0")
        assert response.status_code == 403

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PermissionDeniedError"
        assert body["message"] == "Admin privileges required"

    def test_get_languages_service_error(self, client, mock_service):
        """Verify that service-level Judge0 errors are handled and return 502 Bad Gateway."""
        mock_service.get_unmapped_judge0_languages.side_effect = Judge0ServiceError(
            "Judge0 API is down"
        )

        response = client.get("/api/v1/questions/languages/judge0")
        assert response.status_code == 502

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "Judge0ServiceError"
        assert body["message"] == "Judge0 API is down"


class TestDeletePlatformLanguageRoute:
    def test_delete_language_success(self, client, mock_service):
        """Verify that an admin can successfully delete a platform language mapping."""
        mock_service.delete_platform_language.return_value = None

        response = client.delete("/api/v1/questions/languages/platform/50")
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["message"] == "Platform language deleted successfully"

        mock_service.delete_platform_language.assert_awaited_once_with(50)

    def test_delete_language_unauthorized(self, client):
        """Verify that non-admins cannot delete a platform language mapping."""

        def mock_require_admin_fail():
            raise PermissionDeniedError("Admin privileges required")

        client.app.dependency_overrides[require_admin] = mock_require_admin_fail

        response = client.delete("/api/v1/questions/languages/platform/50")
        assert response.status_code == 403

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "PermissionDeniedError"

    def test_delete_language_not_found(self, client, mock_service):
        """Verify that 404 is returned if the platform language mapping does not exist."""
        mock_service.delete_platform_language.side_effect = LanguageNotFoundError(50)

        response = client.delete("/api/v1/questions/languages/platform/50")
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "LANGUAGE_NOT_FOUND"
        assert body["message"] == "Language with ID 50 not found."

    def test_delete_language_in_use(self, client, mock_service):
        """Verify that 400 is returned if the language mapping is in use."""
        mock_service.delete_platform_language.side_effect = InvalidQuestionError(
            "Language is in use"
        )

        response = client.delete("/api/v1/questions/languages/platform/50")
        assert response.status_code == 400

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "InvalidQuestionError"
        assert "Language is in use" in body["message"]


class TestGetUnmappedJudge0LanguagesService:
    @pytest.mark.asyncio
    async def test_get_unmapped_languages_filtering(self):
        """Verify that get_unmapped_judge0_languages correctly filters out already mapped platform languages."""
        from unittest.mock import MagicMock

        from app.schema.question import PlatformLanguageResponse
        from app.service.question_service import QuestionService

        # Mock dependencies
        repo = MagicMock()
        lang_repo = AsyncMock()
        guard = MagicMock()
        validator = MagicMock()
        storage = MagicMock()

        service = QuestionService(
            repository=repo,
            language_repository=lang_repo,
            guard=guard,
            validator=validator,
            code_storage_service=storage,
        )

        # Mock service methods
        service.get_judge0_languages = AsyncMock(
            return_value=[
                Judge0LanguageResponse(id=50, name="C (GCC 9.2.0)"),
                Judge0LanguageResponse(id=54, name="C++ (GCC 9.2.0)"),
                Judge0LanguageResponse(id=62, name="Java (OpenJDK 13.0.1)"),
            ]
        )

        # Mock already mapped languages in local database: ID 50 and 54
        service.get_platform_languages = AsyncMock(
            return_value=[
                PlatformLanguageResponse(
                    id=50,
                    name="C (GCC 9.2.0)",
                    slug="c",
                    file_extension=".c",
                    monaco_language="c",
                ),
                PlatformLanguageResponse(
                    id=54,
                    name="C++ (GCC 9.2.0)",
                    slug="cpp",
                    file_extension=".cpp",
                    monaco_language="cpp",
                ),
            ]
        )

        # Call get_unmapped_judge0_languages
        unmapped = await service.get_unmapped_judge0_languages()

        # Should only return ID 62 (Java) because 50 and 54 are already mapped
        assert len(unmapped) == 1
        assert unmapped[0].id == 62
        assert unmapped[0].name == "Java (OpenJDK 13.0.1)"
