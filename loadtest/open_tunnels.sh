#!/usr/bin/env bash
# Open/close SSH tunnels to the live server's Traefik entrypoints for local
# load-test runs. This still hits Traefik on the remote host; it only avoids
# flaky direct TCP routing from this laptop to 10.10.10.23:<port>.

set -euo pipefail

SSH_HOST="${SSH_HOST:-icpc}"
BACKEND_LOCAL_PORT="${BACKEND_LOCAL_PORT:-19000}"
KEYCLOAK_LOCAL_PORT="${KEYCLOAK_LOCAL_PORT:-19080}"
BACKEND_REMOTE_PORT="${BACKEND_REMOTE_PORT:-8000}"
KEYCLOAK_REMOTE_PORT="${KEYCLOAK_REMOTE_PORT:-8080}"
PID_DIR="${TMPDIR:-/tmp}/amrita-icpc-loadtest-tunnels"
ACTION="${1:-start}"

mkdir -p "$PID_DIR"

pid_file() {
    printf '%s/%s.pid\n' "$PID_DIR" "$1"
}

is_running() {
    local pid_file_path="$1"
    [[ -s "$pid_file_path" ]] && kill -0 "$(cat "$pid_file_path")" 2>/dev/null
}

start_tunnel() {
    local name="$1"
    local local_port="$2"
    local remote_port="$3"
    local pid_file_path
    pid_file_path="$(pid_file "$name")"

    if is_running "$pid_file_path"; then
        echo "$name tunnel already running (pid $(cat "$pid_file_path")): http://127.0.0.1:$local_port"
        return
    fi

    rm -f "$pid_file_path"
    ssh -f -N \
        -o ExitOnForwardFailure=yes \
        -L "$local_port:127.0.0.1:$remote_port" \
        "$SSH_HOST"

    # Pick the newest matching tunnel process for this exact local forward.
    pgrep -f "ssh .* -L $local_port:127.0.0.1:$remote_port .*${SSH_HOST}" | tail -1 > "$pid_file_path"
    echo "$name tunnel started (pid $(cat "$pid_file_path")): http://127.0.0.1:$local_port -> $SSH_HOST:127.0.0.1:$remote_port"
}

stop_tunnel() {
    local name="$1"
    local pid_file_path
    pid_file_path="$(pid_file "$name")"

    if is_running "$pid_file_path"; then
        kill "$(cat "$pid_file_path")"
        echo "$name tunnel stopped (pid $(cat "$pid_file_path"))"
    else
        echo "$name tunnel not running"
    fi
    rm -f "$pid_file_path"
}

status_tunnel() {
    local name="$1"
    local local_port="$2"
    local pid_file_path
    pid_file_path="$(pid_file "$name")"

    if is_running "$pid_file_path"; then
        echo "$name: running (pid $(cat "$pid_file_path")) http://127.0.0.1:$local_port"
    else
        echo "$name: stopped"
    fi
}

case "$ACTION" in
    start)
        start_tunnel backend "$BACKEND_LOCAL_PORT" "$BACKEND_REMOTE_PORT"
        start_tunnel keycloak "$KEYCLOAK_LOCAL_PORT" "$KEYCLOAK_REMOTE_PORT"
        cat <<EOF

Use these for local runs:
  HOST=http://127.0.0.1:$BACKEND_LOCAL_PORT
  KEYCLOAK_SERVER_URL=http://127.0.0.1:$KEYCLOAK_LOCAL_PORT/

Example:
  HOST=http://127.0.0.1:$BACKEND_LOCAL_PORT \\
  KEYCLOAK_SERVER_URL=http://127.0.0.1:$KEYCLOAK_LOCAL_PORT/ \\
  ./loadtest/run_env_switch_test.sh --scenario loadtest/scenarios/dashboard_locustfile.py --shape baseline
EOF
        ;;
    stop)
        stop_tunnel backend
        stop_tunnel keycloak
        ;;
    restart)
        "$0" stop
        "$0" start
        ;;
    status)
        status_tunnel backend "$BACKEND_LOCAL_PORT"
        status_tunnel keycloak "$KEYCLOAK_LOCAL_PORT"
        ;;
    *)
        echo "Usage: $0 [start|stop|restart|status]" >&2
        exit 1
        ;;
esac
