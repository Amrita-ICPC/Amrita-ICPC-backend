"""
Locust load test: leaderboard polling.

Models students who obsessively refresh the contest leaderboard during a
contest, watching for their rank to change - a very common real pattern,
distinct from the actual submit/run workload. Unlike the contest-burst and
dashboard scenarios, viewing the leaderboard does not require an active
contest session or any question fetch: it is gated purely by the contest's
result visibility setting, not by session state (see
get_student_contest_leaderboard in app/api/routes/v1/students/contests.py,
which delegates to get_contest_leaderboard in
app/service/student/contest_team.py). If results haven't been published yet,
or the contest owner has hidden the leaderboard, that service raises
ContestResultsNotVisibleError, which the API surfaces as HTTP 403 with
error.code == "ContestResultsNotVisibleError" - that is an expected gated
state during a load test run (e.g. one started before results are
published), not a failure, and is treated as such below. Any other >=400
status is a real failure.

Each simulated student:
  1. Logs in via Keycloak (on_start). No contest session start, no question
     fetch - just auth, matching what the leaderboard endpoint actually
     requires.
  2. Repeatedly GETs the leaderboard. Most requests ask for page 1
     (page_size=50, the route's own defaults) since most students just want
     to see the top of the board / their own rank near the top; ~20% of
     requests ask for a random page in [1, 3] to simulate students scrolling
     further down to find themselves.

wait_time is deliberately slower (3-8s) than the autosave/typing scenarios:
refreshing the leaderboard is a human "let me check my rank" action, not a
tight background poll.

Usage:
    locust -f loadtest/scenarios/leaderboard_poll_locustfile.py --host http://<backend-host>:8000 \
        --users 50 --spawn-rate 10 --run-time 2m --headless

Env vars:
    LOAD_TEST_CONTEST_ID    - UUID of the target contest (required).
    LOAD_TEST_STUDENT_COUNT - size of the studentN account pool (default 10),
                               must be >= --users.
"""

import os
import random
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

# The route's own defaults (see get_student_contest_leaderboard).
PAGE_SIZE = 50
# Fraction of requests that ask for page 1 rather than a deeper page.
PAGE_ONE_PROBABILITY = 0.8
MAX_SCROLL_PAGE = 3

# error.code emitted by ContestResultsNotVisibleError (falls back to the
# class name since it doesn't set a custom error_code) - see
# app/exceptions/contest.py and app/api/errors.py's _create_error_response.
RESULTS_NOT_VISIBLE_ERROR_CODE = "ContestResultsNotVisibleError"

username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


class StudentUser(HttpUser):
    # Refreshing the leaderboard is a slower, human-driven "check my rank"
    # action - not a background poll like autosave, so wait longer between
    # requests than the other scenarios do.
    wait_time = between(3, 8)

    def on_start(self):
        # Same reverse proxy sits in front of the backend, so spoof a
        # browser User-Agent here too (see keycloak_auth.py for why).
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    @task
    def view_leaderboard(self):
        if random.random() < PAGE_ONE_PROBABILITY:
            page = 1
        else:
            page = random.randint(1, MAX_SCROLL_PAGE)

        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/leaderboard",
            params={"page": page, "page_size": PAGE_SIZE},
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/leaderboard",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                response.success()
                return

            if response.status_code == 403:
                error_code = None
                try:
                    error_code = response.json().get("error", {}).get("code")
                except ValueError:
                    pass
                if error_code == RESULTS_NOT_VISIBLE_ERROR_CODE:
                    # Results simply aren't published/visible yet - an
                    # expected gated state during a run, not a failure.
                    response.success()
                    return

            response.failure(
                f"unexpected status {response.status_code} for {self.username} "
                f"(page={page}): {response.text[:200]}"
            )
