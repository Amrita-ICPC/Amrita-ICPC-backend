"""Tests for the instructor dashboard route's request handling.

The full app installs Keycloak middleware globally, so these tests mount
just the instructor dashboard router on a throwaway FastAPI app and override
its dependencies (auth gate, current-user id, and the service) -- this
verifies query-parameter validation and response wiring without a live
Keycloak server or database. Authorization *logic* itself is covered
separately in test_instructor_dashboard_authorization.py, against the real
dependency objects.
"""

from unittest.mock import AsyncMock
from uuid import uuid4

import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient

from app.api.routes.v1.instructors import dashboard as dashboard_route
from app.auth.dependencies import (
    get_current_user_id,
    instructor_manager_admin_procedure,
)
from app.schema.instructor_dashboard import (
    InstructorDashboardContestGroups,
    InstructorDashboardResponse,
    InstructorDashboardSummary,
)


def _empty_dashboard_response() -> InstructorDashboardResponse:
    return InstructorDashboardResponse(
        summary=InstructorDashboardSummary(
            live_contests=0,
            upcoming_contests=0,
            completed_contests=0,
            pending_team_approvals=0,
            pending_evaluations=0,
            results_ready_to_publish=0,
            question_banks=0,
        ),
        needs_attention=[],
        contests=InstructorDashboardContestGroups(live=[], upcoming=[], completed=[]),
        recent_banks=[],
    )


@pytest.fixture
def mock_service():
    service = AsyncMock()
    service.get_dashboard.return_value = _empty_dashboard_response()
    return service


@pytest.fixture
def client(mock_service):
    app = FastAPI()
    app.include_router(dashboard_route.router, prefix="/api/v1/instructors")

    app.dependency_overrides[get_current_user_id] = lambda: uuid4()
    app.dependency_overrides[instructor_manager_admin_procedure.dependency] = lambda: {
        "sub": "test-user"
    }
    app.dependency_overrides[dashboard_route.get_instructor_dashboard_service] = (
        lambda: mock_service
    )

    return TestClient(app)


class TestQueryParameterValidation:
    def test_defaults_are_applied_when_omitted(self, client, mock_service):
        response = client.get("/api/v1/instructors/dashboard")

        assert response.status_code == 200
        mock_service.get_dashboard.assert_awaited_once()
        _, kwargs = mock_service.get_dashboard.call_args
        assert kwargs["contest_limit"] == 5
        assert kwargs["bank_limit"] == 4

    @pytest.mark.parametrize(
        "params",
        [
            {"contest_limit": 0},
            {"contest_limit": 21},
            {"bank_limit": 0},
            {"bank_limit": 21},
        ],
    )
    def test_out_of_range_values_are_rejected(self, client, params):
        response = client.get("/api/v1/instructors/dashboard", params=params)
        assert response.status_code == 422

    @pytest.mark.parametrize(
        "params",
        [
            {"contest_limit": 1},
            {"contest_limit": 20},
            {"bank_limit": 1},
            {"bank_limit": 20},
        ],
    )
    def test_boundary_values_are_accepted(self, client, params):
        response = client.get("/api/v1/instructors/dashboard", params=params)
        assert response.status_code == 200

    def test_custom_values_are_forwarded_to_the_service(self, client, mock_service):
        response = client.get(
            "/api/v1/instructors/dashboard",
            params={"contest_limit": 10, "bank_limit": 8},
        )

        assert response.status_code == 200
        _, kwargs = mock_service.get_dashboard.call_args
        assert kwargs["contest_limit"] == 10
        assert kwargs["bank_limit"] == 8


class TestResponseEnvelope:
    def test_wraps_result_in_standard_api_response(self, client):
        response = client.get("/api/v1/instructors/dashboard")

        body = response.json()
        assert body["success"] is True
        assert body["data"]["summary"]["live_contests"] == 0
        assert body["data"]["contests"]["live"] == []
        assert "meta" in body
