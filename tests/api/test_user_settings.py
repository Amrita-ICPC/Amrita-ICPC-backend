"""Tests for user settings API routes."""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.errors import setup_exception_handlers
from app.api.routes.v1.user import router as user_router
from app.auth.dependencies import get_current_user_id
from app.exceptions.user import UserNotFoundError
from app.schema.user import UserResponse, UserSettingsResponse
from app.utils.enums import UserRole


@pytest.fixture
def mock_user_service(monkeypatch):
    """Mock UserService methods used by the routes."""
    mock_service = AsyncMock()
    monkeypatch.setattr("app.api.routes.v1.user.UserService", mock_service)
    return mock_service


@pytest.fixture
def client(mock_user_service):
    """FastAPI TestClient with overridden dependencies."""
    app = FastAPI()
    setup_exception_handlers(app)
    app.include_router(user_router, prefix="/api/v1/users")

    # Override get_current_user_id dependency
    app.dependency_overrides[get_current_user_id] = lambda: uuid4()

    return TestClient(app)


class TestUserSettingsRoutes:
    def test_get_settings_success(self, client, mock_user_service):
        """Verify that a user can fetch their settings."""
        mock_user_service.get_settings.return_value = UserSettingsResponse(theme="dark")

        response = client.get("/api/v1/users/me/settings")
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["data"]["theme"] == "dark"
        assert body["message"] == "Settings fetched successfully"

        mock_user_service.get_settings.assert_awaited_once()

    def test_get_settings_user_not_found(self, client, mock_user_service):
        """Verify that get settings returns 404 if the user is not found in database."""
        mock_user_service.get_settings.side_effect = UserNotFoundError("some-id")

        response = client.get("/api/v1/users/me/settings")
        assert response.status_code == 404

        body = response.json()
        assert body["success"] is False
        assert body["error"]["code"] == "UserNotFoundError"

    def test_patch_settings_success(self, client, mock_user_service):
        """Verify that a user can update their settings."""
        from datetime import datetime

        # Mocking return value of update_settings which is UserResponse (as defined in UserService)
        mock_user_response = UserResponse(
            id=uuid4(),
            user_id="kc-id",
            name="Test User",
            email="test@example.com",
            role=UserRole.student,
            theme="light",
            created_at=datetime.now(),
            last_updated=datetime.now(),
        )
        mock_user_service.update_settings.return_value = mock_user_response

        response = client.patch("/api/v1/users/me/settings", json={"theme": "light"})
        assert response.status_code == 200

        body = response.json()
        assert body["success"] is True
        assert body["data"]["theme"] == "light"
        assert body["message"] == "Settings updated successfully"

        mock_user_service.update_settings.assert_awaited_once()
