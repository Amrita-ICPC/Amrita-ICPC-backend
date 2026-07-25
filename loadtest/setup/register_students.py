"""
Register student1..studentN into a contest ahead of a load test, so the
load test itself measures the contest-start burst rather than first-time
team creation traffic.

Assumes the students already exist in Keycloak and are already synced into
the app DB (a separate provisioning step, not this script's job).

Logs each student in via Keycloak and calls
POST /students/contests/{contest_id}/teams (a solo team - the target
contest should be contest_mode=INDIVIDUAL, see setup/setup_contest.py, so the
team is auto-confirmed on creation with no separate approval step). A 409
(STUDENT_ALREADY_IN_CONTEST) means a previous run already registered that
student and is treated as success, not a failure.

Runs with a bounded thread pool (--concurrency, default 50) rather than
one student at a time - at 1000 students, sequential registration is slow
enough to matter. Transient errors (e.g. a connection reset under the
concurrent login/registration burst) are retried a few times per student
before being counted as a real failure.

Usage:
    LOAD_TEST_CONTEST_ID=<uuid> LOAD_TEST_STUDENT_COUNT=1000 \
        .venv/bin/python loadtest/setup/register_students.py --host http://10.10.10.23:8000
"""

import argparse
import os
import sys
import threading
import time
from concurrent.futures import ThreadPoolExecutor, as_completed
from pathlib import Path

# keycloak_auth.py lives one level up, in loadtest/.
sys.path.insert(0, str(Path(__file__).resolve().parent.parent))

import requests
from keycloak_auth import (
    BROWSER_USER_AGENT,
    DEFAULT_PASSWORD,
    USERNAME_PREFIX,
    KeycloakTokenManager,
)

# A single flaky request shouldn't fail a whole registration run - retry
# transient errors a couple of times before giving up on a student.
MAX_ATTEMPTS = 3
RETRY_BACKOFF_SECONDS = 1.5


def register_one(host: str, contest_id: str, username: str) -> tuple[str, bool, str]:
    try:
        token = KeycloakTokenManager(username, DEFAULT_PASSWORD).login()
    except Exception as exc:
        return username, False, f"login failed: {exc}"

    last_error = ""
    for attempt in range(1, MAX_ATTEMPTS + 1):
        try:
            response = requests.post(
                f"{host}/api/v1/students/contests/{contest_id}/teams",
                json={"name": f"{username}-team"},
                headers={
                    "Authorization": f"Bearer {token}",
                    "User-Agent": BROWSER_USER_AGENT,
                },
                timeout=30,
            )
        except requests.exceptions.RequestException as exc:
            last_error = f"request failed: {exc}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue

        if response.status_code < 300 or response.status_code == 409:
            return username, True, ""

        if response.status_code in (429, 502, 503, 504):
            # Transient overload signals (rate limited / bad gateway / service
            # unavailable / gateway timeout) -- exactly what a burst of
            # concurrent registrations can trigger. Retry like a connection
            # error instead of failing the student outright.
            last_error = f"status {response.status_code}: {response.text[:200]}"
            if attempt < MAX_ATTEMPTS:
                time.sleep(RETRY_BACKOFF_SECONDS * attempt)
            continue

        # Non-transient (auth, validation, server bug) - retrying won't help.
        return username, False, f"status {response.status_code}: {response.text[:200]}"

    return username, False, last_error


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--host", required=True, help="Backend base URL, e.g. http://10.10.10.23:8000"
    )
    parser.add_argument("--concurrency", type=int, default=50)
    args = parser.parse_args()

    contest_id = os.environ.get("LOAD_TEST_CONTEST_ID")
    count = int(os.environ.get("LOAD_TEST_STUDENT_COUNT", "10"))
    if not contest_id:
        sys.exit("LOAD_TEST_CONTEST_ID env var must be set")

    host = args.host.rstrip("/")
    usernames = [f"{USERNAME_PREFIX}{i}" for i in range(1, count + 1)]
    ok = 0
    failed: list[tuple[str, str]] = []
    lock = threading.Lock()

    print(
        f"Registering {len(usernames)} students into contest {contest_id} on {host} "
        f"(concurrency={args.concurrency})"
    )

    with ThreadPoolExecutor(max_workers=args.concurrency) as pool:
        futures = [pool.submit(register_one, host, contest_id, u) for u in usernames]
        for i, future in enumerate(as_completed(futures), start=1):
            username, success, error = future.result()
            with lock:
                if success:
                    ok += 1
                else:
                    failed.append((username, error))
            if i % 50 == 0 or i == len(usernames):
                print(
                    f"  {i}/{len(usernames)} processed ({ok} ok, {len(failed)} failed)"
                )

    print(f"\nDone. {ok}/{len(usernames)} registered successfully.")
    if failed:
        print(f"{len(failed)} failures (showing up to 10):")
        for username, error in failed[:10]:
            print(f"  {username}: {error}")
        sys.exit(1)


if __name__ == "__main__":
    main()
