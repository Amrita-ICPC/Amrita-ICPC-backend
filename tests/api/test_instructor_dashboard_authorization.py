"""Tests for the instructor dashboard's authorization gate.

This exercises the *actual* dependency objects wired onto
GET /api/v1/instructors/dashboard (``get_current_user`` and
``instructor_manager_admin_procedure``) directly, rather than through a full
HTTP request. The app installs Keycloak middleware globally (real JWT/JWKS
validation against a live Keycloak server), which this test suite has no
fixture for anywhere -- going through TestClient would either need a running
IDP or a JWT-verification mock, neither of which exists in this codebase's
test conventions. Calling the dependency callables directly still exercises
the real production authorization logic, just without the ASGI/network
round trip.
"""

from types import SimpleNamespace

import pytest

from app.auth.dependencies import get_current_user, instructor_manager_admin_procedure
from app.exceptions.auth import PermissionDeniedError, UnauthorizedError


class TestUnauthenticatedRequest:
    def test_missing_user_attribute_is_unauthorized(self):
        request = SimpleNamespace()  # no `.user` at all
        with pytest.raises(UnauthorizedError):
            get_current_user(request)

    def test_none_user_is_unauthorized(self):
        request = SimpleNamespace(user=None)
        with pytest.raises(UnauthorizedError):
            get_current_user(request)


class TestGroupGate:
    """The route gates on instructor_manager_admin_procedure, whose
    underlying callable is AccessControl(allowed_groups=["admin",
    "instructor", "manager"])."""

    @property
    def access_control(self):
        return instructor_manager_admin_procedure.dependency

    def test_student_is_denied(self):
        user = {"sub": "u1", "groups": ["student"], "roles": []}
        with pytest.raises(PermissionDeniedError):
            self.access_control(user=user)

    def test_instructor_is_allowed(self):
        user = {"sub": "u2", "groups": ["instructor"], "roles": []}
        result = self.access_control(user=user)
        assert result is user

    def test_manager_is_allowed(self):
        """Manager currently carries no client roles in this realm (see
        keycloak/realm-export.json), so only the group-based check admits
        them -- a permission-based check (e.g. can_read("contests")) would
        not."""
        user = {"sub": "u3", "groups": ["manager"], "roles": []}
        result = self.access_control(user=user)
        assert result is user

    def test_admin_is_allowed(self):
        user = {"sub": "u4", "groups": ["admin"], "roles": []}
        result = self.access_control(user=user)
        assert result is user

    def test_leading_slash_group_names_are_normalized(self):
        """Keycloak commonly sends groups as '/instructor' rather than
        'instructor'; AccessControl normalizes this the same way it does
        for every other group-gated endpoint."""
        user = {"sub": "u5", "groups": ["/instructor"], "roles": []}
        result = self.access_control(user=user)
        assert result is user

    def test_user_with_no_relevant_group_is_denied(self):
        user = {"sub": "u6", "groups": [], "roles": []}
        with pytest.raises(PermissionDeniedError):
            self.access_control(user=user)
