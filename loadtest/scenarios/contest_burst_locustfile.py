"""
Locust load test: contest-start burst.

Models the thundering herd at contest T0: students who are already logged
in and sitting in the contest lobby all click "Start Contest" within the
same instant, once the contest opens. This is usually the sharpest spike a
contest platform sees - way sharper than the request rate implied by
--spawn-rate alone, since real students don't arrive at a steady rate, they
all act the moment the countdown hits zero.

Each simulated student:
  1. Logs in via Keycloak (on_start).
  2. Views contest details and participation status (lobby browsing).
  3. Registers a solo team for the contest if not already registered
     (idempotent - a 409 STUDENT_ALREADY_IN_CONTEST from a previous run is
     treated as success, not a failure).
  4. Blocks on a shared gate until Locust finishes spawning every user for
     this run, then - in the same instant as every other simulated
     student - fires start_contest_session followed by a runtime fetch.
     Only step 4 is measured as "the burst"; steps 1-3 are setup noise.

Requires a published, registration-open, INDIVIDUAL-mode contest (see
loadtest/setup/setup_contest.py) and student accounts that exist both in
Keycloak and in the app DB - loadtest/run_contest_burst.sh handles the
whole pipeline (contest + registration + this locustfile) end to end.

Usage:
    locust -f loadtest/scenarios/contest_burst_locustfile.py --host http://<backend-host>:8000 \
        --users 200 --spawn-rate 200 --run-time 2m --headless

Env vars:
    LOAD_TEST_CONTEST_ID    - UUID of the target contest (required).
    LOAD_TEST_STUDENT_COUNT - size of the studentN account pool (default 10),
                               must be >= --users.

Keep --spawn-rate close to --users: the ramp-up itself doesn't need to be
instant, since the gate is what makes the "start" call synchronous
regardless of how spread out spawning was.
"""

import os
import sys
import threading
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
from locust import HttpUser, between, events, task

STUDENT_POOL_SIZE = int(os.environ.get("LOAD_TEST_STUDENT_COUNT", "10"))
CONTEST_ID = os.environ.get("LOAD_TEST_CONTEST_ID")

username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)

# Opens once Locust has finished spawning every user for this run, so every
# spawned student fires "start contest" at (as close as possible to) the
# same instant, regardless of when its own spawn/setup finished.
_start_gate = threading.Event()


@events.spawning_complete.add_listener
def _open_gate(**kwargs):
    _start_gate.set()


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


class StudentUser(HttpUser):
    wait_time = between(1, 2)

    def on_start(self):
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()
        self._fired_burst = False

        self._browse_lobby()
        self._ensure_registered()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def _browse_lobby(self):
        self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]",
        )
        self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/participation/me",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/participation/me",
        )

    def _ensure_registered(self):
        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/teams",
            json={"name": f"{self.username}-team"},
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/teams (setup)",
            catch_response=True,
        ) as response:
            # 409 STUDENT_ALREADY_IN_CONTEST just means a previous run
            # already registered this student - not a failure.
            if response.status_code < 300 or response.status_code == 409:
                response.success()
            else:
                response.failure(
                    f"unexpected status {response.status_code} registering "
                    f"{self.username}: {response.text[:200]}"
                )

    @task
    def burst_start(self):
        if self._fired_burst:
            self._poll_runtime()
            return
        self._fired_burst = True

        _start_gate.wait()

        headers = self._auth_headers()
        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/start",
            headers=headers,
            name="/api/v1/students/contests/[id]/start (BURST)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} for {self.username}: "
                    f"{response.text[:200]}"
                )

        self._poll_runtime()

    def _poll_runtime(self):
        self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/runtime",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/runtime",
        )
