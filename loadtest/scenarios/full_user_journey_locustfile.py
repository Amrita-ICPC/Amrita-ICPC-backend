"""
Locust load test: full student contest journey.

Models a realistic production contest session instead of one isolated endpoint:

Per simulated student, on_start does the one-time journey setup:
  1. Log in through Keycloak.
  2. View the student dashboard.
  3. Open the contest lobby/details and participation status.
  4. Ensure an INDIVIDUAL solo team exists (409 already-in-contest is OK).
  5. Start/resume the contest session.
  6. Fetch contest questions and lock onto one question.

After setup, each user repeats a weighted mix of normal in-contest behavior:
  - autosave workspace while typing (highest weight),
  - reload workspace occasionally,
  - fetch runtime / questions while navigating,
  - run sample code,
  - submit and poll for verdict less often,
  - refresh leaderboard / dashboard occasionally.

This is the closest single locustfile to a normal production user journey. Use
narrow scenario files when you need endpoint-specific capacity numbers.

Usage with the env-switch pipeline:

    HOST=http://127.0.0.1:19000 \
    KEYCLOAK_SERVER_URL=http://127.0.0.1:19080/ \
    loadtest/run_env_switch_test.sh \
        --scenario loadtest/scenarios/full_user_journey_locustfile.py \
        --shape baseline \
        --students 50

Env vars:
    LOAD_TEST_CONTEST_ID    - UUID of a published contest (set by the pipeline).
    LOAD_TEST_STUDENT_COUNT - size of the studentN account pool (default 10),
                              should be >= peak concurrent users.
"""

import os
import random
import sys
import time
from pathlib import Path

# keycloak_auth.py lives one level up, in loadtest/ - Locust only auto-adds
# this file's own directory to sys.path, not its parent, so add it ourselves.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

from keycloak_auth import (  # noqa: E402
    BROWSER_USER_AGENT,
    DEFAULT_PASSWORD,
    KeycloakTokenManager,
    StudentUsernamePool,
)
from locust import HttpUser, between, events, task  # noqa: E402

STUDENT_POOL_SIZE = int(os.environ.get("LOAD_TEST_STUDENT_COUNT", "10"))
CONTEST_ID = os.environ.get("LOAD_TEST_CONTEST_ID")

# 71 = Python (3.8.1) on this Judge0 instance - fastest no-compile option.
PYTHON_LANGUAGE_ID = 71

RUN_CODE = "import sys\nsys.stdout.write(sys.stdin.read())\n"

SOLUTION_CODE = """class Solution:
    def __getattr__(self, name):
        def _stub(*args, **kwargs):
            return 0

        return _stub
"""

POLL_INTERVAL_SECONDS = 1.0
POLL_MAX_ATTEMPTS = 15
PAGE_SIZE = 50
PAGE_ONE_PROBABILITY = 0.8
MAX_SCROLL_PAGE = 3
RESULTS_NOT_VISIBLE_ERROR_CODE = "ContestResultsNotVisibleError"

username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


class FullJourneyStudent(HttpUser):
    # Human-ish pacing between page actions. Individual helper methods that poll
    # verdicts include their own sleeps and should not be made too aggressive.
    wait_time = between(2, 6)

    def on_start(self):
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()

        self.question_ids: list[str] = []
        self.question_id: str | None = None
        self._source_lines = ["def solve():", "    pass"]
        self._edit_count = 0

        self.view_dashboard()
        self._browse_lobby()
        if self._start_or_resume_session():
            self._fetch_questions(setup=True)
            self._poll_runtime()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def _failure_text(self, response, action: str) -> str:
        return (
            f"unexpected status {response.status_code} {action} for "
            f"{self.username}: {response.text[:200]}"
        )

    def _error_code(self, response) -> str | None:
        try:
            return response.json().get("error", {}).get("code")
        except ValueError:
            return None

    def _is_no_team_member(self, response) -> bool:
        return (
            response.status_code == 404
            and self._error_code(response) == "NO_CONTEST_TEAM_MEMBER"
        )

    @task(1)
    def view_dashboard(self):
        with self.client.get(
            "/api/v1/students/contests",
            headers=self._auth_headers(),
            name="/api/v1/students/contests",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(self._failure_text(response, "viewing dashboard"))

    def _browse_lobby(self):
        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(self._failure_text(response, "viewing contest details"))

        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/participation/me",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/participation/me",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(self._failure_text(response, "checking participation"))

    def _ensure_registered(self) -> bool:
        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/teams",
            json={"name": f"{self.username}-team"},
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/teams (setup)",
            catch_response=True,
        ) as response:
            if response.status_code < 300:
                response.success()
                return True
            if response.status_code == 409 and self._error_code(response) in {
                "STUDENT_ALREADY_IN_CONTEST",
                "StudentAlreadyInContestError",
            }:
                response.success()
                return True

            response.failure(self._failure_text(response, "registering team"))
            return False

    def _start_or_resume_session(self, allow_retry: bool = True) -> bool:
        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/start",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/start (setup)",
            catch_response=True,
        ) as response:
            if response.status_code == 200:
                return True

            if allow_retry and self._is_no_team_member(response):
                # In production, students can arrive while registration state is
                # still being established (or after a prior setup attempt was
                # interrupted). Treat the first no-member response as setup
                # noise, re-run idempotent registration, then retry once.
                response.success()
                self._ensure_registered()
                time.sleep(0.5)
                return self._start_or_resume_session(allow_retry=False)

            response.failure(self._failure_text(response, "starting session"))
            return False

    @task(2)
    def browse_in_contest(self):
        self._poll_runtime()
        if random.random() < 0.35:
            self._fetch_questions(setup=False)

    def _poll_runtime(self):
        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/runtime",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/runtime",
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                response.failure(self._failure_text(response, "polling runtime"))

    def _fetch_questions(self, setup: bool, allow_retry: bool = True):
        request_name = "/api/v1/students/contests/[id]/questions"
        if setup:
            request_name += " (setup)"

        with self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/questions",
            headers=self._auth_headers(),
            name=request_name,
            catch_response=True,
        ) as response:
            if response.status_code != 200:
                if setup and allow_retry and self._is_no_team_member(response):
                    response.success()
                    self._ensure_registered()
                    self._start_or_resume_session()
                    time.sleep(0.5)
                    return self._fetch_questions(setup=True, allow_retry=False)

                response.failure(self._failure_text(response, "fetching questions"))
                return

            questions = response.json().get("data", {}).get("questions", [])
            if not questions:
                response.failure(f"contest {CONTEST_ID} has no questions")
                return

            self.question_ids = [question["id"] for question in questions]
            # Stay on one question most of the time, but sometimes switch tabs.
            if self.question_id not in self.question_ids or random.random() < 0.15:
                self.question_id = random.choice(self.question_ids[: min(5, len(self.question_ids))])
            response.success()

    def _grow_source_code(self):
        self._edit_count += 1
        self._source_lines.append(f"    # full-journey edit {self._edit_count}")
        return "\n".join(self._source_lines) + "\n"

    @task(6)
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
                response.failure(self._failure_text(response, "saving workspace"))

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
                response.failure(self._failure_text(response, "reloading workspace"))

    @task(2)
    def run_code(self):
        if not self.question_id:
            return

        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/questions/{self.question_id}/run",
            json={"code": RUN_CODE, "language_id": PYTHON_LANGUAGE_ID},
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions/[id]/run",
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                response.success()
            elif response.status_code >= 400:
                response.failure(self._failure_text(response, "running code"))

    @task(1)
    def submit_and_poll(self):
        if not self.question_id:
            return

        headers = self._auth_headers()
        submission_id = self._submit_code(headers)
        if submission_id is not None:
            self._poll_until_terminal(submission_id, headers)

    def _submit_code(self, headers):
        with self.client.post(
            f"/api/v1/students/contests/{CONTEST_ID}/questions/{self.question_id}/submit",
            json={"code": SOLUTION_CODE, "language_id": PYTHON_LANGUAGE_ID},
            headers=headers,
            name="/api/v1/students/contests/[id]/questions/[id]/submit",
            catch_response=True,
        ) as response:
            if response.status_code == 429:
                response.success()
                return None
            if response.status_code != 201:
                response.failure(self._failure_text(response, "submitting code"))
                return None
            response.success()
            try:
                return response.json()["data"]["id"]
            except (KeyError, ValueError, TypeError):
                response.failure(
                    f"malformed submit response for {self.username}: "
                    f"{response.text[:200]}"
                )
                return None

    def _poll_until_terminal(self, submission_id, headers):
        poll_name = "/api/v1/students/contests/[id]/submissions/[id] (poll)"
        for attempt in range(1, POLL_MAX_ATTEMPTS + 1):
            time.sleep(POLL_INTERVAL_SECONDS)
            is_last_attempt = attempt == POLL_MAX_ATTEMPTS

            with self.client.get(
                f"/api/v1/students/contests/{CONTEST_ID}/submissions/{submission_id}",
                headers=headers,
                name=poll_name,
                catch_response=True,
            ) as response:
                if response.status_code != 200:
                    if is_last_attempt:
                        response.failure(
                            f"unexpected status {response.status_code} polling "
                            f"submission {submission_id} for {self.username}: "
                            f"{response.text[:200]}"
                        )
                    else:
                        response.success()
                    continue

                submission_status = response.json().get("data", {}).get("status")
                if submission_status is not None:
                    response.success()
                    return

                if is_last_attempt:
                    response.failure(
                        f"submission {submission_id} still not terminal after "
                        f"{POLL_MAX_ATTEMPTS} polls "
                        f"(~{POLL_MAX_ATTEMPTS * POLL_INTERVAL_SECONDS:.0f}s) "
                        f"for {self.username}"
                    )
                else:
                    response.success()

    @task(2)
    def poll_leaderboard(self):
        page = 1 if random.random() < PAGE_ONE_PROBABILITY else random.randint(1, MAX_SCROLL_PAGE)
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

            try:
                error_code = response.json().get("error", {}).get("code")
            except ValueError:
                error_code = None
            if response.status_code == 403 and error_code == RESULTS_NOT_VISIBLE_ERROR_CODE:
                response.success()
                return

            response.failure(self._failure_text(response, "polling leaderboard"))
