"""
Locust load test: Judge0 execution API, hit directly (bypassing the backend).

Purpose: isolate Judge0's own capacity ceiling from the backend's. The
backend (single replica) already saturates around ~50-100 concurrent users
(see loadtest results); routing a Judge0 capacity test through it would just
re-measure that ceiling, not Judge0's. This scenario talks straight to
Judge0's public endpoint (:2358, already exposed via Traefik) with the same
AUTHN_TOKEN the backend uses, so results reflect Judge0's own sandbox/queue
throughput independent of backend/auth/DB overhead.

Each simulated client repeatedly submits a trivial, always-valid program and
waits synchronously for the verdict (`wait=true`) - this measures real
per-request latency directly, the same thing a naive direct caller would
experience. Production's actual path is different (async submit + a
dedicated poller queue, see app/tasks/worker/poller.py) - this scenario is
deliberately NOT modeling that path; it isolates raw Judge0 throughput.

No Keycloak/contest/database setup required - point this at Judge0 alone:

    JUDGE0_API_KEY=<key> LOAD_TEST_SHAPE=load \\
        .venv/bin/locust -f loadtest/scenarios/judge0_direct_locustfile.py,loadtest/shapes.py \\
            --host http://10.10.10.23:2358 --headless

Env vars:
    JUDGE0_API_KEY  - X-Auth-Token value (required; same as the backend's
                      JUDGE0_API_KEY / group_vars/vault.yml backend_judge0_api_key).
    LOAD_TEST_LANGUAGE_ID - Judge0 language id to submit (default 71 = Python
                      3.8.1, no compile step, matches the other scenarios'
                      rationale for isolating queue/exec overhead).
"""

import os
import sys

from locust import HttpUser, between, events, task

API_KEY = os.environ.get("JUDGE0_API_KEY")
LANGUAGE_ID = int(os.environ.get("LOAD_TEST_LANGUAGE_ID", "71"))

# Trivial, always-valid program: reads stdin and echoes it back. Correctness
# doesn't matter here - only that Judge0 accepts and executes it.
SOURCE_CODE = "import sys\nsys.stdout.write(sys.stdin.read())\n"
STDIN = "hello\n"


@events.test_start.add_listener
def _check_config(environment, **kwargs):
    if not API_KEY:
        sys.stderr.write(
            "JUDGE0_API_KEY env var must be set to Judge0's AUTHN_TOKEN.\n"
        )
        environment.runner.quit()


class Judge0Client(HttpUser):
    # No backend rate limiter applies here (direct to Judge0) - a short,
    # steady drip per simulated client so total throughput scales with
    # --users instead of each client hammering as fast as possible.
    wait_time = between(0.5, 1.5)

    def on_start(self):
        self.client.headers.update(
            {"X-Auth-Token": API_KEY, "Content-Type": "application/json"}
        )

    @task
    def submit_and_wait(self):
        with self.client.post(
            "/submissions",
            params={"base64_encoded": "false", "wait": "true"},
            json={
                "source_code": SOURCE_CODE,
                "language_id": LANGUAGE_ID,
                "stdin": STDIN,
            },
            name="/submissions (wait=true)",
            catch_response=True,
        ) as response:
            if response.status_code != 201:
                response.failure(
                    f"unexpected status {response.status_code} submitting to "
                    f"Judge0: {response.text[:200]}"
                )
                return

            data = response.json()
            status_id = data.get("status", {}).get("id")
            # 1=in queue, 2=processing - wait=true should never return these,
            # but guard anyway rather than silently treating it as success.
            if status_id in (1, 2):
                response.failure(
                    f"submission still {data.get('status', {}).get('description')} "
                    f"despite wait=true (token={data.get('token')})"
                )
                return

            response.success()
