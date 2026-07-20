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
  shapes.py                        Staged LoadTestShape: baseline -> load ->
                                    stress -> spike -> soak. Combine with any
                                    scenario via `-f scenario.py,shapes.py`.
  question_bank_data/              Verified DSA question sets (DP/recursion,
                                    stack/queue, graph/binary search),
                                    spliced into scripts/seed_question_bank.py's
                                    QUESTIONS list at import time.
  scenarios/
    dashboard_locustfile.py         Scenario: dashboard browsing (baseline).
    contest_burst_locustfile.py     Scenario: contest-start burst (T0 herd).
    code_run_locustfile.py          Scenario: repeated /run calls, respects
                                    RATE_LIMIT_RUN_*.
    code_submit_locustfile.py       Scenario: /submit + poll for verdict,
                                    respects RATE_LIMIT_SUBMIT_*. Measures the
                                    full API -> Celery -> Judge0 pipeline.
    workspace_autosave_locustfile.py Scenario: periodic PUT .../workspace
                                    with a growing payload, simulating a
                                    student typing throughout the contest.
    leaderboard_poll_locustfile.py  Scenario: students repeatedly refreshing
                                    the leaderboard.
    full_user_journey_locustfile.py Scenario: realistic end-to-end student
                                    session mix: dashboard, lobby/register,
                                    start/resume, questions, workspace,
                                    /run, /submit+poll, leaderboard.
  setup/
    setup_contest.py                 Creates one live, published,
                                    INDIVIDUAL-mode contest, clones every
                                    question from the curated bank
                                    (scripts/seed_question_bank.py) into it,
                                    and publishes results so the leaderboard
                                    is visible. Requires
                                    scripts/seed_question_bank.py to have
                                    already been run against the same DB.
    register_students.py             Registers student1..N into a contest
                                    ahead of time (concurrent, default 50 at
                                    a time; retries transient connection
                                    errors). Assumes students already exist
                                    in Keycloak and the app DB.
  summarize_report.py               Prints a terminal summary from a Locust
                                    --json-file report.
  run_contest_burst.sh              One-shot pipeline: contest + registration
                                    + burst load test + report (production DB,
                                    no isolation - use for a quick check
                                    against data you don't mind touching).
  run_env_switch_test.sh            One-shot pipeline for any scenario against
                                    an ISOLATED test database/Redis-DB/MinIO-
                                    bucket, swapped into the live backend's
                                    .env for the run and unconditionally
                                    restored afterward (even on failure/
                                    Ctrl-C). Preflights against a live contest
                                    in production before touching anything.
                                    See its own header comment for the full
                                    step-by-step and every flag.
  logs/
    latest/                         Symlink to the most recent run's directory.
    contest_burst_<N>students_<timestamp>/
    envswitch_<timestamp>/
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

All seven scenarios above are built and Judge0/live-contest verified. New
question bank content (`scripts/seed_question_bank.py` + `question_bank_data/`)
is Judge0-verified per-question - see each file's module docstring for its
own verification method.

Team-based flows (joining a team, `LEADER_ONLY` submission) are out of
scope for now - all current scenarios use solo (`min_team_size: 1`) teams
so each simulated student acts independently.

## Quickstart: staged test against an isolated database

`run_env_switch_test.sh` is the primary way to run any scenario now: it
swaps the live backend onto an isolated test database/Redis-DB/MinIO-bucket,
seeds the verified question bank + a published contest + registered
students, runs the scenario (optionally as one of the staged shapes in
`shapes.py`), and unconditionally restores the production `.env` afterward -
even if the run fails or is interrupted. It refuses to run if it finds a
live contest in the production database, unless `--force` is passed.

```bash
loadtest/run_env_switch_test.sh --scenario loadtest/scenarios/code_submit_locustfile.py \
    --shape load --students 300
```

See the script's own header comment for every flag (`--skip-seed` to reuse
an already-seeded test environment across repeat runs, `--drop-test-db` to
clean up afterward, `--force` to bypass the live-contest guard, etc.) and
`shapes.py`'s docstring for what each named shape (`baseline`/`load`/
`stress`/`spike`/`soak`) actually does.

### Local tunnel setup

Use `open_tunnels.sh` when direct access to `10.10.10.23:8000` or
`10.10.10.23:8080` is flaky. The tunnels still hit Traefik on the remote
host; they only move the TCP path into SSH.

```bash
./loadtest/open_tunnels.sh start
```

`start` writes `loadtest/.tunnel.env`:

```bash
HOST=http://127.0.0.1:19000
KEYCLOAK_SERVER_URL=http://127.0.0.1:19080/
```

`run_env_switch_test.sh` auto-loads that file when it exists, so you do not
need to export anything manually. Explicit env vars still win if you pass
them on the command line.

Check or stop tunnels:

```bash
./loadtest/open_tunnels.sh status
./loadtest/open_tunnels.sh stop
```

### Which scenario to run

| Scenario | Journey modeled | Use when |
|---|---|---|
| `full_user_journey_locustfile.py` | Dashboard -> lobby/register -> start/resume -> questions -> workspace autosave/reload -> `/run` -> `/submit`+poll -> leaderboard | You want the closest single test to a normal production contest session. Run this first for overall confidence. |
| `dashboard_locustfile.py` | Login + contest dashboard/list browsing | Smoke test auth, dashboard API, and basic read-path latency. |
| `contest_burst_locustfile.py` | Everyone already in lobby clicks **Start Contest** at the same instant | Measure the T0 thundering herd separately from normal traffic. |
| `workspace_autosave_locustfile.py` | Students type and autosave code repeatedly | Measure background write load during a contest. |
| `code_run_locustfile.py` | Students repeatedly click **Run** against sample tests | Measure API + Celery + Judge0 practice-run throughput. |
| `code_submit_locustfile.py` | Students submit and poll until verdict | Measure the full submission -> queue -> Judge0 -> verdict path. This is the heaviest journey. |
| `leaderboard_poll_locustfile.py` | Students refresh ranking pages | Measure leaderboard query/read behavior. |

### Shape selection

| Shape | Stage table | Minimum `--students` | Use when |
|---|---:|---:|---|
| `baseline` | 10 users for 5 minutes | `--students 10` or higher | First correctness run: expect 0 failures before scaling. |
| `load` | 50 -> 100 -> 200 -> 300 users, 3 minutes each | `--students 300` | Normal capacity check for expected contest load. |
| `stress` | 100 -> 250 -> 500 -> 750 -> 1000 users, 3 minutes each | `--students 1000` | Find the breaking point: latency, error rate, DB pool, Redis, Celery, Judge0, CPU. |
| `spike` | 10 users for 30s -> 500 users fast for 2 minutes -> 10 users for 60s | `--students 500` | Sudden contest-open traffic / recovery behavior. |
| `soak` | 200 users for 8 hours | `--students 200` | Memory leaks, connection leaks, latency creep, worker drift. |

### Recommended test progression

Start with the full journey at baseline:

```bash
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/full_user_journey_locustfile.py \
  --shape baseline \
  --students 50
```

If baseline is clean, scale the same full journey:

```bash
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/full_user_journey_locustfile.py \
  --shape load \
  --students 300
```

Then isolate specific bottlenecks:

```bash
# T0 start spike
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/contest_burst_locustfile.py \
  --shape spike \
  --students 500

# Judge0 practice-run path
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/code_run_locustfile.py \
  --shape load \
  --students 300

# Full submission/verdict path; start lower because this hits Judge0 + Celery hardest
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/code_submit_locustfile.py \
  --shape baseline \
  --students 50
```

Run `stress` only after `baseline` and `load` are clean:

```bash
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/full_user_journey_locustfile.py \
  --shape stress \
  --students 1000
```

Run `soak` only when you can leave the environment alone for the full window:

```bash
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/full_user_journey_locustfile.py \
  --shape soak \
  --students 200
```

Add `--drop-test-db` to the final run in a session if you want the isolated
test database removed after restore:

```bash
./loadtest/run_env_switch_test.sh \
  --scenario loadtest/scenarios/full_user_journey_locustfile.py \
  --shape baseline \
  --students 10 \
  --drop-test-db
```

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

`code_run`/`code_submit` scenarios hit the real execution/judge backend
end-to-end by design, so their results conflate API
performance with judge throughput - read them as one number for the whole
pipeline, not an isolated measurement of the API layer.
