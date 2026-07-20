"""
Staged load shapes for the methodology in the load-testing plan: baseline ->
load -> stress -> spike -> soak, each as a distinct, reusable `LoadTestShape`.

Combine with any User-class scenario by passing both files to Locust - the
shape controls user count/spawn rate over time, the scenario controls what
each user does:

    LOAD_TEST_CONTEST_ID=<uuid> LOAD_TEST_SHAPE=load \
        .venv/bin/locust -f loadtest/scenarios/dashboard_locustfile.py,loadtest/shapes.py \
            --host http://10.10.10.23:8000 --headless

`--users`/`--spawn-rate`/`--run-time` are ignored once a shape is active
(Locust's own behavior) - the shape's stage table is the only thing that
controls ramp/duration. LOAD_TEST_SHAPE selects which one runs (default
"load"); LOAD_TEST_STUDENT_COUNT (read by the scenario files themselves,
not here) must be >= the shape's peak user count or Locust will re-use
student accounts beyond the pool size, which is fine (StudentUsernamePool
wraps around) but means concurrent duplicate logins for the same student -
size the pool to match if you want one session per student.

Stage tables (user_count, spawn_rate, duration_seconds), run in order:

  baseline  10 users for 5 minutes - confirms no errors, dashboards populate,
            logs are clean, before pushing any real load.
  load      50 -> 100 -> 200 -> 300 users, each held 3 minutes - watch CPU,
            memory, p95 latency, error rate at each step.
  stress    100 -> 250 -> 500 -> 750 -> 1000 users, each held 3 minutes -
            push until an SLO breaks (p95 latency, error rate, CPU
            saturation, DB connection exhaustion) to find the actual ceiling
            of the current replica count.
  spike     10 -> 500 users within 10 seconds, held 2 minutes, back to 10 -
            can Traefik/FastAPI/Postgres absorb a sudden burst instead of a
            steady ramp (this is the shape of a real contest T0, closer to
            what contest_burst_locustfile.py's gate models more precisely
            for the exact "everyone clicks start now" instant).
  soak      200 users for 8 hours - watch for memory leaks, connection
            leaks, and latency creeping up over time, not just an instant
            snapshot.

Usage:
    LOAD_TEST_SHAPE=baseline .venv/bin/locust -f <scenario.py>,loadtest/shapes.py \\
        --host http://10.10.10.23:8000 --headless

Env vars:
    LOAD_TEST_SHAPE   One of baseline|load|stress|spike|soak (default "load").
"""

import os

from locust import LoadTestShape

# Each stage: (user_count, spawn_rate, duration_seconds).
STAGE_TABLES: dict[str, list[tuple[int, float, float]]] = {
    "baseline": [
        (10, 10, 5 * 60),
    ],
    "load": [
        (50, 50, 3 * 60),
        (100, 50, 3 * 60),
        (200, 50, 3 * 60),
        (300, 50, 3 * 60),
    ],
    "stress": [
        (100, 100, 3 * 60),
        (250, 100, 3 * 60),
        (500, 100, 3 * 60),
        (750, 100, 3 * 60),
        (1000, 100, 3 * 60),
    ],
    "spike": [
        (10, 10, 30),
        (500, 500, 2 * 60),  # spawn_rate=500 reaches 500 users in ~1s -> the burst
        (10, 500, 60),  # drain back down at the same rate, hold to observe recovery
    ],
    "soak": [
        (200, 50, 8 * 60 * 60),
    ],
}


class StagedLoadShape(LoadTestShape):
    """Runs the stage table selected by LOAD_TEST_SHAPE in order, then stops."""

    def __init__(self):
        super().__init__()
        shape_name = os.environ.get("LOAD_TEST_SHAPE", "load")
        if shape_name not in STAGE_TABLES:
            raise RuntimeError(
                f"LOAD_TEST_SHAPE={shape_name!r} is not one of "
                f"{sorted(STAGE_TABLES)} - see loadtest/shapes.py"
            )
        self.stages = STAGE_TABLES[shape_name]

    def tick(self):
        run_time = self.get_run_time()

        elapsed = 0.0
        for user_count, spawn_rate, duration in self.stages:
            elapsed += duration
            if run_time < elapsed:
                return (user_count, spawn_rate)

        return None
