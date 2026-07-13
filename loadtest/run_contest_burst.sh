#!/usr/bin/env bash
#
# End-to-end: create a live contest, register N already-provisioned
# students into it, then run the contest-start burst load test against
# them.
#
# Assumes students already exist in Keycloak and are already synced into
# the app DB (a separate provisioning script handles that, not this one).
#
# Talks to Postgres directly to create the contest (via the app's own DB
# config in .env - same as scripts/seed_contests.py), and to the backend's
# HTTP API for registration and the load test itself.
#
# Usage:
#   loadtest/run_contest_burst.sh [student_count] [host]
#
# Env var overrides:
#   STUDENT_COUNT   number of students to register/simulate (default 1000)
#   HOST            backend base URL (default http://10.10.10.23:8000)
#   SPAWN_RATE      locust spawn rate (default: same as STUDENT_COUNT)
#   RUN_TIME        locust run duration (default 2m)
#   CONCURRENCY     concurrent registration requests (default 50)

set -euo pipefail

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$REPO_ROOT"

STUDENT_COUNT="${1:-${STUDENT_COUNT:-1000}}"
HOST="${2:-${HOST:-http://10.10.10.23:8000}}"
SPAWN_RATE="${SPAWN_RATE:-$STUDENT_COUNT}"
RUN_TIME="${RUN_TIME:-2m}"
PYTHON="$REPO_ROOT/.venv/bin/python"
LOCUST="$REPO_ROOT/.venv/bin/locust"

echo "=================================================================="
echo " Contest-start burst load test"
echo "   host:          $HOST"
echo "   student count: $STUDENT_COUNT"
echo "=================================================================="

echo
echo "==> [1/2] Creating a live INDIVIDUAL-mode contest..."
CONTEST_ID="$("$PYTHON" loadtest/setup/setup_contest.py | tail -1)"
if [[ -z "$CONTEST_ID" ]]; then
    echo "Failed to create contest - see output above." >&2
    exit 1
fi
echo "    contest id: $CONTEST_ID"

echo
echo "==> [2/2] Registering $STUDENT_COUNT students into contest $CONTEST_ID..."
LOAD_TEST_CONTEST_ID="$CONTEST_ID" LOAD_TEST_STUDENT_COUNT="$STUDENT_COUNT" \
    "$PYTHON" loadtest/setup/register_students.py --host "$HOST" --concurrency "${CONCURRENCY:-50}"

echo
echo "==> Running contest-start burst load test..."
# Every run gets its own directory (not loose timestamped files directly in
# logs/) so results stay easy to find and never overwrite each other:
# loadtest/logs/contest_burst_<students>students_<timestamp>/
RUN_TAG="contest_burst_${STUDENT_COUNT}students_$(date +%Y%m%d_%H%M%S)"
RUN_DIR="loadtest/logs/$RUN_TAG"
mkdir -p "$RUN_DIR"

cat > "$RUN_DIR/meta.txt" <<EOF
host:          $HOST
student_count: $STUDENT_COUNT
spawn_rate:    $SPAWN_RATE
run_time:      $RUN_TIME
contest_id:    $CONTEST_ID
started_at:    $(date -u +"%Y-%m-%dT%H:%M:%SZ")
EOF

# --reset-stats zeroes the stats the instant spawning finishes, so the
# saved report reflects only the synchronized burst (and its aftermath),
# not the lobby-browsing/registration-retry traffic from on_start.
# Locust exits 1 if the run had any failures, which is expected/normal for
# a burst test - don't let `set -e` cut the script off before the report
# is summarized and its paths are printed.
set +e
LOAD_TEST_CONTEST_ID="$CONTEST_ID" LOAD_TEST_STUDENT_COUNT="$STUDENT_COUNT" \
    "$LOCUST" -f loadtest/scenarios/contest_burst_locustfile.py \
        --host "$HOST" \
        --users "$STUDENT_COUNT" \
        --spawn-rate "$SPAWN_RATE" \
        --run-time "$RUN_TIME" \
        --headless \
        --reset-stats \
        --csv "$RUN_DIR/run" \
        --csv-full-history \
        --html "$RUN_DIR/report.html" \
        --json-file "$RUN_DIR/run"
LOCUST_EXIT=$?
set -e

echo
"$PYTHON" loadtest/summarize_report.py "$RUN_DIR/run.json"

# Convenience pointer at the most recent run, so you don't have to hunt for
# the latest timestamp - loadtest/logs/latest always resolves to it.
ln -sfn "$RUN_TAG" loadtest/logs/latest

echo
echo "Full artifacts in $RUN_DIR/ (also: loadtest/logs/latest):"
echo "  report.html          interactive report (RPS/response-time/users over time)"
echo "  run.json             final per-endpoint metrics (used above)"
echo "  run_stats.csv         same final metrics, as CSV"
echo "  run_stats_history.csv full time-series snapshot"
echo "  run_failures.csv      failure breakdown"
echo "  meta.txt              host/student_count/contest_id for this run"
echo "Contest id: $CONTEST_ID"

if [[ "$LOCUST_EXIT" -ne 0 ]]; then
    echo
    echo "Note: locust exited $LOCUST_EXIT because the run had failures - see the report above/csv for details."
fi
exit "$LOCUST_EXIT"
