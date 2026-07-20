"""
Locust load test: practice "run code" endpoint.

Models a student iterating on their solution during a contest: repeatedly
hitting "Run" against the sample test case(s) to sanity-check their code
before submitting it for real. Unlike burst-style scenarios, this one is
about sustained, per-user request rate rather than a synchronized spike -
the thing that matters here is how the API + Judge0 queue behave under a
steady drip of run requests from many students at once.

Each simulated student:
  1. Logs in via Keycloak (on_start).
  2. Fetches the contest's question list and caches the first question's id
     (on_start) - avoids needing a per-student question id env var, and any
     published contest with at least one question works.
  3. Repeatedly POSTs a trivial, Judge0-valid Python program (echoes stdin)
     to the run endpoint (the @task).

Language is pinned to id 71 (Python 3.8.1) deliberately: it has no compile
step on this Judge0 instance, so run latency reflects API + queue overhead
rather than compile-time variance across languages.

Rate limiting: the backend caps practice runs at
config.RATE_LIMIT_RUN_TIMES requests per config.RATE_LIMIT_RUN_SECONDS
per user (currently 10 requests / 10 seconds, see app/core/config.py and
the `rate_limit(...)` dependency on the run route). wait_time is set to
between(1.2, 2) seconds, i.e. an average of ~1.6s between requests per
simulated user, which works out to at most ~8.3 requests per 10s window
per user - comfortably under the 10/10s cap so a single user's own traffic
doesn't trip its own limit. With enough concurrent users you can still
saturate the *shared* Judge0 queue (that's the point), but each user's own
429 rate should stay near zero unless the limiter's Redis bucket is being
hit by other traffic (other locustfiles, other students) sharing the same
identifier space. Any 429 that does show up is treated as an expected,
non-failing response (see run_code below) rather than a bug.

Requires a published contest with at least one question, with the calling
students already registered/started for it (see
loadtest/setup/setup_contest.py). Always pass --host explicitly, e.g.:

    locust -f loadtest/scenarios/code_run_locustfile.py --host http://<backend-host>:8000 \
        --users 10 --spawn-rate 10 --run-time 1m --headless

Env vars:
    LOAD_TEST_CONTEST_ID    - UUID of the target contest (required).
    LOAD_TEST_STUDENT_COUNT - size of the studentN account pool (default 10),
                               must be >= --users.
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
from locust import HttpUser, between, events, task

STUDENT_POOL_SIZE = int(os.environ.get("LOAD_TEST_STUDENT_COUNT", "10"))
CONTEST_ID = os.environ.get("LOAD_TEST_CONTEST_ID")

# Judge0 language id 71 = Python (3.8.1) on this platform's DB - fastest
# option with no compile step, chosen deliberately (see module docstring).
PYTHON_LANGUAGE_ID = 71

# Trivial, always-valid program: reads stdin and echoes it back. It doesn't
# need to match any test case's expected output - this endpoint is being
# exercised for API + Judge0 queue overhead, not correctness.
RUN_CODE = "import sys\nsys.stdout.write(sys.stdin.read())\n"

username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


class StudentUser(HttpUser):
    # ~1.6s average between requests per user => <=~8.3 req/10s per user,
    # under the RATE_LIMIT_RUN_TIMES/RATE_LIMIT_RUN_SECONDS (10/10s) cap.
    wait_time = between(1.2, 2)

    def on_start(self):
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()
        self.question_id = None

        self._fetch_first_question()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def _fetch_first_question(self):
        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/questions",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions (setup)",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} fetching questions "
                    f"for {self.username}: {response.text[:200]}"
                )
                return
            questions = response.json().get("data", {}).get("questions", [])
            if not questions:
                response.failure(
                    f"contest {CONTEST_ID} has no questions to run code against"
                )
                return
            self.question_id = questions[0]["id"]

    @task
    def run_code(self):
        if not self.question_id:
            # Setup failed (e.g. empty question list) - nothing to run.
            return

        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/questions/{self.question_id}/run",
            json={"code": RUN_CODE, "language_id": PYTHON_LANGUAGE_ID},
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions/[id]/run",
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                # Rate limited - expected/normal under load once enough
                # concurrent users share the limiter's bucket, not a bug.
                response.success()
            elif response.status_code >= 500 or response.status_code >= 400:
                response.failure(
                    f"unexpected status {response.status_code} running code for "
                    f"{self.username}: {response.text[:200]}"
                )
