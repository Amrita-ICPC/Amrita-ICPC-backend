#!/usr/bin/env bash
#
# Run a Locust scenario against the LIVE backend with its database, Redis DB
# index, and MinIO bucket temporarily swapped to isolated test values, then
# restore the original .env unconditionally (success, failure, or Ctrl-C).
#
# This is an IN-PLACE swap of the single prod `icpc-backend` container's
# config, not a separate deployment: real traffic hitting the backend during
# the test window would see the test database. Only run this against a host
# with no live contest / no real student traffic, and prefer running it
# during a scheduled maintenance window. The preflight check below refuses to
# proceed if it finds an active contest in the *production* database unless
# --force is passed.
#
# What it does, in order:
#   1. Preflight: abort if a contest is currently live in the prod DB (unless --force).
#   2. Snapshot the remote backend/.env verbatim to a local temp file.
#   3. Create the test Postgres database if it doesn't already exist.
#   4. Render a test .env (DATABASE_NAME/REDIS_DB/MINIO_BUCKET_NAME swapped),
#      push it, and recreate the backend + celery containers so they pick it up.
#      MIGRATIONS_ENABLED=false means the app schema-syncs its own tables on
#      startup - an empty test database needs no separate migration step.
#   5. Seed: Keycloak student accounts, the verified DSA question bank, the
#      bulk read-path dataset, one live contest cloned from the bank and
#      published, and pre-registers students into it.
#   6. Run the requested Locust scenario from THIS machine against the public
#      host (never bypass Traefik - that's what production traffic goes through).
#   7. ALWAYS restore the original .env, recreate the containers again, and
#      wait for health - via a trap, so this runs even if any earlier step
#      failed or the script was interrupted.
#
# Recovery if this script itself is killed with SIGKILL (`kill -9`, an
# out-of-band process-supervisor timeout, `docker kill` on the shell it's
# running in, etc.): SIGKILL cannot be trapped by any shell script, so the
# restore step above will NOT run. Every run's env.prod.bak survives under
# loadtest/logs/envswitch_<timestamp>/ - to manually recover, run:
#   scp loadtest/logs/envswitch_<timestamp>/env.prod.bak \
#       amrita@<host>:/home/amrita/Amrita-ICPC/backend/.env
#   ssh amrita@<host> 'cd /home/amrita/Amrita-ICPC/backend && \
#       docker compose up -d --force-recreate backend celery_worker_student \
#       celery_worker_bulk celery_worker_poller celery_beat'
# Then confirm with:
#   ssh amrita@<host> 'docker compose -f /home/amrita/Amrita-ICPC/backend/docker-compose.yml \
#       exec -T backend python -c "from app.core.config import config; print(config.DATABASE_NAME)"'
# A normal Ctrl-C (SIGINT) or a plain `kill` (SIGTERM) IS caught (see the
# trap below) and restores automatically - only an unconditional SIGKILL
# bypasses it.
#
# Usage:
#   loadtest/run_env_switch_test.sh --scenario scenarios/dashboard_locustfile.py \
#       --students 50 --users 50 --spawn-rate 50 --run-time 5m
#
# Env vars (all overridable, see defaults below):
#   SSH_HOST, REMOTE_APP_DIR, HOST, TEST_DB_NAME, TEST_REDIS_DB, TEST_MINIO_BUCKET
#
# Flags:
#   --scenario <path>   Locustfile to run (required)
#   --shape <name>       baseline|load|stress|spike|soak (loadtest/shapes.py) -
#                        when set, overrides --users/--spawn-rate/--run-time
#                        entirely and drives the staged ramp described there
#   --students <N>      Student pool size to seed/register (default 50)
#   --users <N>          Locust --users (default: same as --students; ignored if --shape is set)
#   --spawn-rate <N>     Locust --spawn-rate (default: same as --users; ignored if --shape is set)
#   --run-time <dur>     Locust --run-time (default 5m; ignored if --shape is set)
#   --force              Skip the live-contest preflight guard
#   --skip-seed           Reuse an already-seeded test environment
#   --skip-bulk-seed      Skip the bulk 100-contest/5.7k-question read-path dataset
#   --drop-test-db         Drop the test database at the end of the run
#
set -euo pipefail

# --- Defaults ---------------------------------------------------------------
SSH_HOST="${SSH_HOST:-amrita@10.10.10.23}"
REMOTE_APP_DIR="${REMOTE_APP_DIR:-/home/amrita/Amrita-ICPC}"
HOST="${HOST:-http://10.10.10.23:8000}"
TEST_DB_NAME="${TEST_DB_NAME:-amrita-icpc-test}"
TEST_REDIS_DB="${TEST_REDIS_DB:-1}"
TEST_MINIO_BUCKET="${TEST_MINIO_BUCKET:-icpc-test}"

SCENARIO=""
SHAPE=""
STUDENT_COUNT=50
LOCUST_USERS=""
LOCUST_SPAWN_RATE=""
LOCUST_RUN_TIME="5m"
FORCE=0
SKIP_SEED=0
SKIP_BULK_SEED=0
DROP_TEST_DB=0

while [[ $# -gt 0 ]]; do
    case "$1" in
        --scenario) SCENARIO="$2"; shift 2 ;;
        --shape) SHAPE="$2"; shift 2 ;;
        --students) STUDENT_COUNT="$2"; shift 2 ;;
        --users) LOCUST_USERS="$2"; shift 2 ;;
        --spawn-rate) LOCUST_SPAWN_RATE="$2"; shift 2 ;;
        --run-time) LOCUST_RUN_TIME="$2"; shift 2 ;;
        --force) FORCE=1; shift ;;
        --skip-seed) SKIP_SEED=1; shift ;;
        --skip-bulk-seed) SKIP_BULK_SEED=1; shift ;;
        --drop-test-db) DROP_TEST_DB=1; shift ;;
        *) echo "Unknown argument: $1" >&2; exit 1 ;;
    esac
done

if [[ -z "$SCENARIO" ]]; then
    echo "Usage: $0 --scenario <path-to-locustfile> [--shape baseline|load|stress|spike|soak] [options]" >&2
    exit 1
fi
if [[ -n "$SHAPE" ]]; then
    case "$SHAPE" in
        baseline|load|stress|spike|soak) ;;
        *) echo "--shape must be one of baseline|load|stress|spike|soak (see loadtest/shapes.py), got: $SHAPE" >&2; exit 1 ;;
    esac
fi
LOCUST_USERS="${LOCUST_USERS:-$STUDENT_COUNT}"
LOCUST_SPAWN_RATE="${LOCUST_SPAWN_RATE:-$LOCUST_USERS}"

REPO_ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
COMPOSE="docker compose -f $REMOTE_APP_DIR/backend/docker-compose.yml"
BACKEND_SERVICES="backend celery_worker_student celery_worker_bulk celery_worker_poller celery_beat"
HEALTH_URL="$HOST/api/health"

TS="$(date +%Y%m%d_%H%M%S)"
RUN_DIR="$REPO_ROOT/loadtest/logs/envswitch_${TS}"
mkdir -p "$RUN_DIR"
ENV_BACKUP="$RUN_DIR/env.prod.bak"
ENV_TEST="$RUN_DIR/env.test"

log() { printf '\n=== %s ===\n' "$*"; }

wait_for_health() {
    local label="$1"
    log "Waiting for backend health ($label)"
    # A burst of "Connection reset by peer" right after --force-recreate is
    # expected and not a sign of a crash: Traefik's Docker service discovery
    # takes a few seconds to notice the new container and update its
    # backend pool, and briefly resets in-flight connections to the old one
    # in the meantime. Retrying is the correct response, not Ctrl-C - this
    # loop gives it up to 150s and reports the specific curl failure each
    # attempt so it's clear it's actively retrying, not stuck.
    for i in $(seq 1 30); do
        if curl -fsS -o /dev/null "$HEALTH_URL"; then
            echo "Backend healthy ($label)."
            return 0
        fi
        curl_exit=$?
        echo "  attempt $i/30: not healthy yet (curl exit $curl_exit) - retrying in 5s"
        sleep 5
    done
    echo "Backend did not report healthy within 150s ($label)." >&2
    return 1
}

RESTORED=0
restore_prod_env() {
    if [[ "$RESTORED" -eq 1 ]]; then
        return
    fi
    RESTORED=1
    log "RESTORING production .env"
    if [[ ! -s "$ENV_BACKUP" ]]; then
        echo "No .env backup found at $ENV_BACKUP - refusing to touch the remote .env further. Restore manually from $REMOTE_APP_DIR/backend/.env if it was already swapped." >&2
        return 1
    fi
    scp -q "$ENV_BACKUP" "$SSH_HOST:$REMOTE_APP_DIR/backend/.env"
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "cd $REMOTE_APP_DIR/backend && $COMPOSE up -d --force-recreate $BACKEND_SERVICES"
    if wait_for_health "post-restore"; then
        echo "Restore confirmed: backend is back on the production .env."
    else
        echo "WARNING: backend did not report healthy after restoring the production .env - check it by hand: ssh $SSH_HOST 'docker logs icpc-backend-backend-1'" >&2
    fi
    if [[ "$DROP_TEST_DB" -eq 1 ]]; then
        log "Dropping test database $TEST_DB_NAME"
        # shellcheck disable=SC2029
        ssh "$SSH_HOST" "docker exec icpc-postgres psql -U icpc -d postgres -c \"DROP DATABASE IF EXISTS \\\"$TEST_DB_NAME\\\";\"" || \
            echo "WARNING: failed to drop $TEST_DB_NAME - drop it by hand if needed." >&2
    fi
}
trap restore_prod_env EXIT INT TERM

# --- 1. Preflight: refuse to run over a live contest -------------------------
if [[ "$FORCE" -ne 1 ]]; then
    log "Preflight: checking for a live contest in the production database"
    # Piped as a heredoc over ssh's stdin (docker compose exec -T forwards it
    # through) rather than an inline `python -c "..."` string: nested
    # bash/ssh/python quote-escaping across three layers is fragile and has
    # broken here before (a bare `"` inside an f-string terminated the outer
    # bash string early) - a quoted heredoc passes the script through
    # completely literally, no escaping needed at any layer.
    LIVE_COUNT="$(ssh "$SSH_HOST" "$COMPOSE exec -T backend python -" 2>/dev/null <<'PYEOF' | sed -n 's/.*LIVE_COUNT_RESULT=\([0-9]*\).*/\1/p' | tail -1
import asyncio
from sqlalchemy import text
from sqlalchemy.exc import ProgrammingError
from app.core.clients.database import SessionLocal


async def main():
    async with SessionLocal() as db:
        try:
            result = await db.execute(text(
                "SELECT COUNT(*) FROM contest WHERE status = 'PUBLISHED' "
                "AND start_time <= now() AND end_time >= now() AND deleted_at IS NULL"
            ))
            print(f"LIVE_COUNT_RESULT={result.scalar()}")
        except ProgrammingError:
            # Fresh database, contest table does not exist yet - trivially no live contest.
            print("LIVE_COUNT_RESULT=0")


asyncio.run(main())
PYEOF
)"
    if ! [[ "$LIVE_COUNT" =~ ^[0-9]+$ ]]; then
        echo "Preflight check failed to get a live-contest count (got: '$LIVE_COUNT'). Refusing to proceed - re-run with --force only after checking by hand." >&2
        exit 1
    fi
    if [[ "$LIVE_COUNT" != "0" ]]; then
        echo "Refusing to run: $LIVE_COUNT live contest(s) found in the production database. This script swaps the SAME backend container real students are using. Re-run with --force only if you are certain no one is using the platform right now." >&2
        exit 1
    fi
    echo "No live contest found. Proceeding."
else
    log "Preflight skipped (--force)"
fi

# --- 2. Snapshot the current .env verbatim -----------------------------------
log "Backing up production .env"
ssh "$SSH_HOST" "cat $REMOTE_APP_DIR/backend/.env" > "$ENV_BACKUP"
if [[ ! -s "$ENV_BACKUP" ]]; then
    echo "Failed to read the remote .env - aborting before touching anything." >&2
    exit 1
fi
echo "Backed up to $ENV_BACKUP"

# --- 3. Ensure the test database exists --------------------------------------
log "Ensuring test database $TEST_DB_NAME exists"
# shellcheck disable=SC2029
ssh "$SSH_HOST" "docker exec icpc-postgres psql -U icpc -d postgres -tc \"SELECT 1 FROM pg_database WHERE datname='$TEST_DB_NAME'\" | grep -q 1 || docker exec icpc-postgres psql -U icpc -d postgres -c \"CREATE DATABASE \\\"$TEST_DB_NAME\\\" OWNER icpc;\""

# --- 4. Render + push the test .env, recreate containers ---------------------
log "Rendering test .env (DATABASE_NAME=$TEST_DB_NAME REDIS_DB=$TEST_REDIS_DB MINIO_BUCKET_NAME=$TEST_MINIO_BUCKET)"
sed \
    -e "s/^DATABASE_NAME=.*/DATABASE_NAME=$TEST_DB_NAME/" \
    -e "s/^REDIS_DB=.*/REDIS_DB=$TEST_REDIS_DB/" \
    -e "s/^MINIO_BUCKET_NAME=.*/MINIO_BUCKET_NAME=$TEST_MINIO_BUCKET/" \
    "$ENV_BACKUP" > "$ENV_TEST"
for key in DATABASE_NAME REDIS_DB MINIO_BUCKET_NAME; do
    grep -q "^${key}=" "$ENV_TEST" || { echo "Expected $key in .env, found none - aborting." >&2; exit 1; }
done
scp -q "$ENV_TEST" "$SSH_HOST:$REMOTE_APP_DIR/backend/.env"
# shellcheck disable=SC2029
ssh "$SSH_HOST" "cd $REMOTE_APP_DIR/backend && $COMPOSE up -d --force-recreate $BACKEND_SERVICES"
wait_for_health "test env"

# Hard safety check: confirm the RUNNING container's own config actually
# resolved to the test database, not just that the .env file on disk says
# so. A container that was merely `docker stop`/`docker start`-ed (instead
# of recreated) keeps the environment it was CREATED with - env_file is
# only re-read on create/recreate - so a stale container would silently
# keep serving production the whole time while this script thinks it
# swapped. This happened once during development; never again.
log "Verifying the running container is actually on the test database"
ACTUAL_DB="$(ssh "$SSH_HOST" "$COMPOSE exec -T backend python -" 2>/dev/null <<'PYEOF' | tail -1
from app.core.config import config
print(config.DATABASE_NAME)
PYEOF
)"
if [[ "$ACTUAL_DB" != "$TEST_DB_NAME" ]]; then
    echo "SAFETY ABORT: the backend container reports DATABASE_NAME='$ACTUAL_DB', expected '$TEST_DB_NAME'. It did NOT actually switch to the test database - refusing to seed or run anything against it. This usually means the container was restarted without --force-recreate somewhere. Nothing test-related has been touched yet; restoring the original .env now." >&2
    exit 1
fi
echo "Confirmed: backend is on DATABASE_NAME=$ACTUAL_DB"

# --- 5. Seed -------------------------------------------------------------------
if [[ "$SKIP_SEED" -ne 1 ]]; then
    log "Seeding Keycloak student accounts (student1..student$STUDENT_COUNT)"
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "printf '%s\n' '$STUDENT_COUNT' | $COMPOSE exec -T backend python scripts/create_keycloak_users.py"

    log "Syncing Keycloak accounts into the app database"
    # create_keycloak_users.py only creates the Keycloak-side accounts;
    # authenticated requests resolve the user via a row in the app's own
    # `users` table, populated by this sync. Skipping it here means every
    # student login succeeds (real Keycloak JWT) but every subsequent API
    # call 404s with UserNotFoundError - found and fixed during development.
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "$COMPOSE exec -T backend python -" 2>/dev/null <<'PYEOF'
import asyncio
from app.core.clients.database import SessionLocal
from app.service.user_service import UserService


async def main():
    async with SessionLocal() as db:
        result = await UserService.sync_keycloak_users(db)
        print(f"Synced {result['synced_count']} user(s), skipped {result['skipped_count']} (already existed)")


asyncio.run(main())
PYEOF

    log "Seeding verified DSA question bank"
    # shellcheck disable=SC2029
    ssh "$SSH_HOST" "$COMPOSE exec -T backend python scripts/seed_question_bank.py"

    if [[ "$SKIP_BULK_SEED" -ne 1 ]]; then
        log "Seeding bulk read-path dataset (100 contests / ~5.7k questions)"
        # shellcheck disable=SC2029
        ssh "$SSH_HOST" "$COMPOSE exec -T backend python scripts/seed_contests.py"
    fi

    log "Creating + publishing the live load-test contest from the verified bank"
    # shellcheck disable=SC2029
    CONTEST_ID="$(ssh "$SSH_HOST" "$COMPOSE exec -T backend python loadtest/setup/setup_contest.py" 2>/dev/null | sed -n 's/.*CONTEST_ID_RESULT=\([0-9a-fA-F-]*\).*/\1/p' | tail -1)"
    if [[ -z "$CONTEST_ID" ]]; then
        echo "setup_contest.py did not print a contest id - aborting before load." >&2
        exit 1
    fi
    echo "Live contest: $CONTEST_ID"

    log "Registering $STUDENT_COUNT students into the contest"
    LOAD_TEST_CONTEST_ID="$CONTEST_ID" LOAD_TEST_STUDENT_COUNT="$STUDENT_COUNT" \
        "$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/loadtest/setup/register_students.py" --host "$HOST"
else
    log "Seeding skipped (--skip-seed) - reusing existing test environment"
    CONTEST_ID="${LOAD_TEST_CONTEST_ID:-}"
    if [[ -z "$CONTEST_ID" ]]; then
        echo "NOTE: --skip-seed was passed without LOAD_TEST_CONTEST_ID set - the scenario will run without a target contest id." >&2
    fi
fi

# --- 6. Run the scenario -------------------------------------------------------
LOCUST_FILE_ARG="$REPO_ROOT/$SCENARIO"
LOCUST_EXTRA_ARGS=(--users "$LOCUST_USERS" --spawn-rate "$LOCUST_SPAWN_RATE" --run-time "$LOCUST_RUN_TIME")
if [[ -n "$SHAPE" ]]; then
    log "Running Locust scenario: $SCENARIO (shape: $SHAPE)"
    LOCUST_FILE_ARG="$REPO_ROOT/$SCENARIO,$REPO_ROOT/loadtest/shapes.py"
    # The shape's own tick() sequence controls user count/spawn-rate/duration
    # end to end (it returns None to stop) - --users/--spawn-rate/--run-time
    # are meaningless once a LoadTestShape is active, so they're omitted
    # rather than passed-and-ignored.
    LOCUST_EXTRA_ARGS=()
else
    log "Running Locust scenario: $SCENARIO"
fi
LOAD_TEST_CONTEST_ID="${CONTEST_ID:-}" LOAD_TEST_STUDENT_COUNT="$STUDENT_COUNT" LOAD_TEST_SHAPE="$SHAPE" \
    "$REPO_ROOT/.venv/bin/locust" -f "$LOCUST_FILE_ARG" \
        --host "$HOST" \
        "${LOCUST_EXTRA_ARGS[@]}" --headless \
        --csv "$RUN_DIR/run" --csv-full-history \
        --html "$RUN_DIR/report.html" \
        --json-file "$RUN_DIR/run" || LOCUST_EXIT=$?

ln -sfn "$RUN_DIR" "$REPO_ROOT/loadtest/logs/latest"

{
    echo "scenario=$SCENARIO"
    echo "host=$HOST"
    echo "student_count=$STUDENT_COUNT"
    echo "contest_id=${CONTEST_ID:-}"
    echo "test_db=$TEST_DB_NAME"
    echo "started=$TS"
    echo "finished=$(date +%Y%m%d_%H%M%S)"
} > "$RUN_DIR/meta.txt"

log "Report: $RUN_DIR/report.html"
"$REPO_ROOT/.venv/bin/python" "$REPO_ROOT/loadtest/summarize_report.py" "$RUN_DIR/run.json" || true

# restore_prod_env runs automatically via the EXIT trap from here.
exit "${LOCUST_EXIT:-0}"
