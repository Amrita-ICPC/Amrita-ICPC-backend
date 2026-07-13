"""
Locust load test for the ICPC backend.

Step 1: Keycloak-authenticated student users hitting the student dashboard
(GET /api/v1/students/). Always pass --host explicitly, e.g.:

    locust -f loadtest/scenarios/dashboard_locustfile.py --host http://<backend-host>:8000 \
        --users 1 --spawn-rate 1 --run-time 30s --headless

The number of seeded student accounts (student1..studentN) available to draw
from is controlled by the LOAD_TEST_STUDENT_COUNT env var (default 10) - it
should be >= the peak number of concurrent users you plan to simulate.
"""

import os
import sys
from pathlib import Path

# keycloak_auth.py lives one level up, in loadtest/ - Locust only auto-adds
# this file's own directory to sys.path, not its parent, so add it ourselves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keycloak_auth import (
    BROWSER_USER_AGENT,
    DEFAULT_PASSWORD,
    KeycloakTokenManager,
    StudentUsernamePool,
)
from locust import HttpUser, between, task

STUDENT_POOL_SIZE = int(os.environ.get("LOAD_TEST_STUDENT_COUNT", "10"))
username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


class StudentUser(HttpUser):
    wait_time = between(1, 3)

    def on_start(self):
        # Same reverse proxy sits in front of the backend, so spoof a
        # browser User-Agent here too (see keycloak_auth.py for why).
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()

    @task
    def view_dashboard(self):
        token = self.token_manager.get_access_token()
        with self.client.get(
            "/api/v1/students/contests",
            headers={"Authorization": f"Bearer {token}"},
            name="/api/v1/students/contests",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} for {self.username}: "
                    f"{response.text[:200]}"
                )
