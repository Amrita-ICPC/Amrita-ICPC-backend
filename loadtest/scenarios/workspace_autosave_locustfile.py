"""
Locust load test: workspace autosave.

Models a student sitting on a contest question, typing code over the course
of the contest while the frontend autosaves their workspace in the
background - plus the occasional page reload, which restores the saved
workspace from the server.

Each simulated student:
  1. Logs in via Keycloak (on_start).
  2. Fetches the contest's question list and locks onto the first question,
     the way a student who has just opened a question tab would.
  3. Repeatedly (task-weighted 5:1):
       - PUT .../workspace with a source_code string that grows by one line
         every call, simulating incremental typing rather than resending a
         fixed-size blob every autosave.
       - GET .../workspace, simulating a page reload/tab restore pulling the
         last-saved code back down.

Unlike code_run/code_submit, the workspace endpoints have no rate_limit
dependency (see app/api/routes/v1/students/contest_questions.py - the
run/submit routes carry `dependencies=[rate_limit(...)]`, get_workspace and
save_workspace do not). So wait_time here is NOT rate-limit-driven; it's
picked to resemble a realistic autosave debounce / pause-between-keystrokes
cadence instead.

Requires a published contest that the target student accounts are already
registered for and have started (see loadtest/setup/setup_contest.py) - this
locustfile only exercises the workspace endpoints, not registration/start.

Usage:
    locust -f loadtest/scenarios/workspace_autosave_locustfile.py --host http://<backend-host>:8000 \
        --users 50 --spawn-rate 10 --run-time 5m --headless

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

# Python 3.8.1 on the target Judge0 instance - see Language.id comment in
# app/models/language.py ("use judge0 id directly").
PYTHON_LANGUAGE_ID = 71

username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


class StudentUser(HttpUser):
    # Autosave debounce / thinking-time between keystrokes - not rate-limit
    # driven, since these endpoints carry no rate_limit dependency.
    wait_time = between(2, 5)

    def on_start(self):
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()

        # In-memory "what the student has typed so far" - grows by one line
        # per autosave call so payload size grows realistically over the
        # run instead of resending a fixed-size string every time.
        self._source_lines = ["def solve():", "    pass"]
        self._edit_count = 0

        self.question_id = self._fetch_first_question_id()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def _fetch_first_question_id(self):
        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/questions",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} fetching questions "
                    f"for {self.username}: {response.text[:200]}"
                )
                return None

            questions = response.json().get("data", {}).get("questions", [])
            if not questions:
                response.failure(
                    f"contest {CONTEST_ID} has no questions for {self.username}"
                )
                return None

            response.success()
            return questions[0]["id"]

    def _grow_source_code(self):
        self._edit_count += 1
        self._source_lines.append(f"    # autosave edit {self._edit_count}")
        return "\n".join(self._source_lines) + "\n"

    @task(5)
    def autosave_workspace(self):
        if not self.question_id:
            return

        with self.client.put(
            f"/api/v1/students/contests/{CONTEST_ID}/questions/{self.question_id}/workspace",
            json={
                "language_id": PYTHON_LANGUAGE_ID,
                "source_code": self._grow_source_code(),
            },
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions/[id]/workspace",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} saving workspace "
                    f"for {self.username}: {response.text[:200]}"
                )

    @task(1)
    def reload_workspace(self):
        if not self.question_id:
            return

        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/questions/{self.question_id}/workspace",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions/[id]/workspace",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(
                    f"unexpected status {response.status_code} reloading workspace "
                    f"for {self.username}: {response.text[:200]}"
                )
