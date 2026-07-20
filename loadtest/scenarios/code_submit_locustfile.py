"""
Locust load test: contest code submission + judge verdict polling.

Each simulated student:
  1. Logs in via Keycloak (on_start).
  2. Fetches the contest's question list once and picks the first question
     (on_start) - this scenario always targets that one question, it isn't
     modeling "browse then pick", just the submit/judge pipeline.
  3. Repeatedly (one @task iteration): submits a trivial Python solution to
     that question, then polls the submission detail endpoint roughly once a
     second until the verdict is terminal (or a bounded number of attempts is
     exhausted).

Requires a published contest whose session the caller has already started
(POST .../start) for the target student accounts - this scenario does not
register or start a session itself, it only submits code, so run it against
a contest set up the same way contest_burst_locustfile.py's contest is (see
loadtest/setup/setup_contest.py), after a session has been started for every
account in the pool.

Usage:
    locust -f loadtest/scenarios/code_submit_locustfile.py --host http://<backend-host>:8000 \
        --users 5 --spawn-rate 5 --run-time 2m --headless

Env vars:
    LOAD_TEST_CONTEST_ID    - UUID of the target contest (required). Must be
                               published, and every studentN account in the
                               pool below must already be registered and have
                               a started session for it.
    LOAD_TEST_STUDENT_COUNT - size of the studentN account pool (default 10),
                               must be >= --users.

A note on the judge backend
----------------------------
This scenario hits the real execution/judge backend end-to-end by design: a
submit call enqueues a Celery task, which drives Judge0, which writes the
verdict back to Postgres - and this scenario polls until that verdict lands.
So its numbers conflate API latency with judge throughput; read them as one
number for the whole submit -> queue -> Judge0 -> verdict pipeline, not an
isolated measurement of the API layer.

The submitted code is a generic stub (see SOLUTION_CODE below) since this
scenario doesn't know in advance which question it will be assigned - it
just needs to be syntactically valid Python so the submission runs through
Judge0 rather than failing at the request layer. Whatever terminal verdict
comes back (AC/WA/RE/TLE/...) is treated purely as pipeline latency data,
not correctness data; this was confirmed end-to-end against the live Judge0
instance (source concatenated exactly as the platform does it: solution
code, blank line, a real question's driver_code), which reports a clean
"Runtime Error (NZEC)" - no infra failure, no compile error, a genuine
terminal Judge0 status.

Also note: this platform doesn't persist an explicit QUEUED/PENDING status
value on a submission. Submission.status (app/models/question.py) is a
computed property that returns None while is_evaluated is False, and only
resolves to one of SubmissionStatus's terminal values (AC/WA/TLE/RE/CE/MLE/
SYSTEM_ERROR) once evaluation completes. So "poll until terminal" here means
"poll until the submission detail response's data.status is non-null".

Rate limiting / wait_time
--------------------------
POST .../submit is rate-limited per authenticated user to
RATE_LIMIT_SUBMIT_TIMES requests per RATE_LIMIT_SUBMIT_SECONDS seconds
(currently 5 per 10s - see app/core/config.py, enforced per-user via Redis
buckets in app/core/rate_limit.py; the polling GET is not rate-limited, only
the submit POST is). That's an average ceiling of one submit every 2s per
user. Each task iteration here issues exactly one submit call and then
sleeps ~1s between up to POLL_MAX_ATTEMPTS polls before wait_time even
starts, so a single iteration already spans several seconds; wait_time is
set to between(3, 6)s on top of that purely as a safety margin so a run of
fast verdicts (submission resolves after only 1-2 polls) can't push a single
user's average submit rate anywhere near the per-user limit.
"""

import os
import sys
import time
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

# 71 = Python (3.8.1) on this Judge0 instance - chosen deliberately, see
# module docstring; do not swap for another language_id.
PYTHON_LANGUAGE_ID = 71

# ~1 poll/sec, up to ~15s total, matching a realistic student-facing
# "waiting for verdict" timeout without hammering the poll endpoint.
POLL_INTERVAL_SECONDS = 1.0
POLL_MAX_ATTEMPTS = 15

# Generic stub: whichever question this scenario is assigned, the platform
# concatenates this exactly as f"{code}\n\n{driver_code}" at judge time (see
# app/service/code_execution_service.py / worker/evaluation_service.py). Real
# driver_code templates in this question bank instantiate `Solution()` and
# call a question-specific method on it (see scripts/seed_question_bank.py),
# so a plain `pass`-only class risks a NameError on an unknown method. This
# __getattr__ stub answers any method call with a harmless default instead,
# guaranteeing the source is valid and runs through Judge0 to a genuine
# terminal verdict (typically a runtime error against the real expected
# output shape) rather than dying at compile/request time.
SOLUTION_CODE = """class Solution:
    def __getattr__(self, name):
        def _stub(*args, **kwargs):
            return 0

        return _stub
"""


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not CONTEST_ID:
        raise RuntimeError(
            "LOAD_TEST_CONTEST_ID env var must be set to a published contest UUID"
        )


username_pool = StudentUsernamePool(STUDENT_POOL_SIZE)


class StudentUser(HttpUser):
    wait_time = between(3, 6)

    def on_start(self):
        self.client.headers.update({"User-Agent": BROWSER_USER_AGENT})
        self.username = username_pool.acquire()
        self.token_manager = KeycloakTokenManager(self.username, DEFAULT_PASSWORD)
        self.token_manager.login()
        self.question_id = self._fetch_first_question_id()

    def _auth_headers(self):
        return {"Authorization": f"Bearer {self.token_manager.get_access_token()}"}

    def _fetch_first_question_id(self):
        response = self.client.get(
            f"/api/v1/students/contests/{CONTEST_ID}/questions",
            headers=self._auth_headers(),
            name="/api/v1/students/contests/[id]/questions (setup)",
        )
        questions = response.json()["data"]["questions"]
        return questions[0]["id"]

    @task
    def submit_and_poll(self):
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
                # Expected under load once a user's own submit rate crosses
                # RATE_LIMIT_SUBMIT_TIMES/RATE_LIMIT_SUBMIT_SECONDS - the
                # limiter doing its job, not a backend defect.
                response.success()
                return None
            if response.status_code != 201:
                response.failure(
                    f"unexpected status {response.status_code} submitting for "
                    f"{self.username}: {response.text[:200]}"
                )
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
                    # Terminal verdict reached (AC/WA/TLE/RE/CE/MLE/etc) -
                    # this is what the whole pipeline was measured for.
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
