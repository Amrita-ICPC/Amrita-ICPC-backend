# Load testing

Locust-based load tests for student-facing flows, targeting a staging
environment sized like a real contest (100-1000+ concurrent students).

## Layout

```
loadtest/
  keycloak_auth.py                 Shared Keycloak ROPC login/refresh +
                                    student username pool. Imported by every
                                    locustfile and setup script (each adds
                                    loadtest/'s parent onto sys.path itself
                                    to reach it, since it's one level up).
  scenarios/
    dashboard_locustfile.py         Scenario: dashboard browsing (baseline).
    contest_burst_locustfile.py     Scenario: contest-start burst (T0 herd).
  setup/
    setup_contest.py                 Creates one live, published,
                                    INDIVIDUAL-mode contest directly in the DB.
    register_students.py             Registers student1..N into a contest
                                    ahead of time (concurrent, default 50 at
                                    a time; retries transient connection
                                    errors). Assumes students already exist
                                    in Keycloak and the app DB.
  summarize_report.py               Prints a terminal summary from a Locust
                                    --json-file report.
  run_contest_burst.sh              One-shot pipeline: contest + registration
                                    + burst load test + report.
  logs/
    latest/                         Symlink to the most recent run's directory.
    contest_burst_<N>students_<timestamp>/
      report.html                   Interactive charts (open this first).
      run.json                      Final per-endpoint metrics.
      run_stats.csv                  Same metrics as CSV.
      run_stats_history.csv          Full time-series snapshot.
      run_failures.csv               Failure breakdown.
      run_exceptions.csv             Uncaught exceptions, if any.
      meta.txt                      host/student_count/contest_id/timings
                                    for this run.
    (all gitignored - every run gets its own directory, nothing is
    overwritten between runs)
```

One locustfile per scenario (Locust convention), always run with `-f`
explicitly and `--host` pointed at the target environment. New scenarios go
in `scenarios/` and should follow the same shape: reuse `keycloak_auth.py`
for auth (via the same-directory `sys.path.insert` pattern the existing
scenarios use), read their target contest/question IDs from env vars, and
name requests (`name=...`) so Locust groups stats by endpoint instead of by
path param.

Planned next scenarios (not yet built):
- `scenarios/code_run_locustfile.py` - repeated `/run` calls against sample
  tests, respects `RATE_LIMIT_RUN_*`.
- `scenarios/code_submit_locustfile.py` - `/submit` + SSE verdict stream
  (`GET /students/contests/{id}/submission`), respects `RATE_LIMIT_SUBMIT_*`.
- `scenarios/workspace_autosave_locustfile.py` - periodic `PUT .../workspace`
  calls simulating students typing throughout the contest.
- `scenarios/leaderboard_poll_locustfile.py`.

Team-based flows (joining a team, `LEADER_ONLY` submission) are out of
scope for now - all current scenarios use solo (`min_team_size: 1`) teams
so each simulated student acts independently.

## Quickstart: contest-start burst, end to end

`run_contest_burst.sh` creates a contest, registers students into it, runs
the burst, and prints a report:

```bash
loadtest/run_contest_burst.sh 1000 http://10.10.10.23:8000
# or: STUDENT_COUNT=1000 HOST=http://10.10.10.23:8000 loadtest/run_contest_burst.sh
```

**Prerequisite**: `student1..studentN` must already exist in Keycloak *and*
be synced into the app DB - this script doesn't create or sync users, it
assumes that's already been done (by whatever provisioning script/process
you're using for that).

This is still a real, consequential action against whatever host you point
it at - it fires a synchronized burst of requests. Don't run it against a
host you don't control or that other people are actively using, and start
with a small `student_count` (e.g. 10-50) the first time to confirm
everything's wired up correctly.

Steps performed (each is also runnable standalone, see docstrings):
1. `setup/setup_contest.py` - one live, published, `INDIVIDUAL`-mode contest
   (auto-confirms each solo team on creation, so no separate approval step).
2. `setup/register_students.py` - registers all N students into the contest
   *before* the load test runs (concurrently, `--concurrency`/`$CONCURRENCY`,
   default 50), so the burst measures the `/start` spike itself, not
   first-time registration traffic.
3. The burst load test itself, with `--reset-stats` so the report reflects
   only the synchronized burst - not the setup/registration-retry traffic
   from each simulated user's `on_start`.

## Reading the report

Each run gets its own directory - nothing is overwritten between runs, and
`loadtest/logs/latest` always symlinks to the most recent one:

```
loadtest/logs/contest_burst_<student_count>students_<timestamp>/
```

| File | What it's for |
|---|---|
| `report.html` | **Open this first.** Interactive charts: requests/sec, response times, and user count, all over the run's timeline - this is "how long did the burst take to drain" and "how did latency behave during it," visually. |
| `run.json` | Final per-endpoint metrics (request count, failures, response-time histogram, first/last request timestamp). Printed as a terminal table automatically at the end of `run_contest_burst.sh` via `summarize_report.py`; re-run that script manually against any `run.json` to reprint it. |
| `run_stats.csv` / `run_stats_history.csv` | Same numbers as CSV - the `_history` one is a full time-series snapshot, for building your own charts (Excel, a notebook, Grafana, etc.) if the HTML report isn't enough. |
| `run_failures.csv` | Every distinct failure, with a sample error message. |
| `meta.txt` | Host, student count, contest id, and timing for that specific run - so an old report is self-describing without having to dig through shell history. |

The terminal summary highlights the row whose name contains `BURST` (the
`/start` call) with a `*` - that's the number that matters most: its
p50/p95/p99/max response time, and the Duration/Avg RPS columns show how
long the synchronized burst actually took to complete and at what
throughput it drained.

## Running a scenario manually

For scenarios other than the full pipeline above (or to reuse students you
already provisioned):

```bash
export LOAD_TEST_STUDENT_COUNT=200        # must be >= --users
export LOAD_TEST_CONTEST_ID=<live-contest-uuid>

RUN_DIR=loadtest/logs/contest_burst_200students_manual && mkdir -p "$RUN_DIR"
locust -f loadtest/scenarios/contest_burst_locustfile.py \
    --host https://staging.example.com \
    --users 200 --spawn-rate 200 --run-time 2m --headless \
    --reset-stats \
    --csv "$RUN_DIR/run" --csv-full-history \
    --html "$RUN_DIR/report.html" \
    --json-file "$RUN_DIR/run"
```

- Start small (10-50 users) against staging first to confirm the scenario
  is correct end-to-end before scaling up.
- For burst scenarios, keep `--spawn-rate` close to `--users` - the
  in-script gate (see `contest_burst_locustfile.py`) is what actually
  synchronizes the measured action, but a slow ramp-up still delays when
  the gate opens.
- `--json-file <name>` writes `<name>.json` (Locust appends the extension
  itself - don't include it).

## A note on the judge backend

`code_run`/`code_submit` scenarios (once added) will hit the real
execution/judge backend end-to-end by design, so their results conflate API
performance with judge throughput - read them as one number for the whole
pipeline, not an isolated measurement of the API layer.
