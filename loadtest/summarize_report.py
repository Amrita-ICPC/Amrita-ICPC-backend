"""
Print a clean summary of a completed load test run from Locust's
--json-file output, and point at the fuller artifacts for everything else.

Locust already produces the full picture per run (via run_contest_burst.sh),
all inside one directory per run - loadtest/logs/contest_burst_<N>students_<timestamp>/:
  run.json                final per-endpoint metrics (this script's input)
  report.html              interactive report: RPS/response-time/user-count
                          charts over the run's whole timeline
  run_stats.csv            same final metrics as run.json, as CSV
  run_stats_history.csv    full time-series snapshot (every stats tick)
  run_failures.csv         failure breakdown
  meta.txt                 host/student_count/contest_id for this run

--json-file's per-endpoint entries carry a raw response-time histogram
(`response_times`: {bucketed_ms: count}) rather than precomputed
percentiles, so percentiles/median here are derived with Locust's own
calculate_response_time_percentile()/median_from_dict() - the same
functions Locust itself uses for the console/HTML report - rather than
reimplemented by hand.

Usage:
    .venv/bin/python loadtest/summarize_report.py loadtest/logs/<run>/run.json
"""

import json
import os
import sys

from locust.stats import calculate_response_time_percentile, median_from_dict


def fmt_ms(value) -> str:
    return f"{value:.0f}ms" if isinstance(value, (int, float)) else "n/a"


def main() -> None:
    if len(sys.argv) != 2:
        sys.exit("Usage: summarize_report.py <path-to-locust-json-file>")

    path = sys.argv[1]
    with open(path) as f:
        entries = json.load(f)

    if not entries:
        print("No requests were recorded (empty stats).")
        return

    total_requests = sum(e["num_requests"] for e in entries)
    total_failures = sum(e["num_failures"] for e in entries)
    fail_rate = (total_failures / total_requests * 100) if total_requests else 0.0

    print("=" * 90)
    print(f"Load test summary - {path}")
    print("=" * 90)
    header = (
        f"{'Endpoint':<38} {'Reqs':>6} {'Fail':>5} {'p50':>6} {'p95':>6} {'p99':>6} "
        f"{'Max':>6} {'Duration':>9} {'Avg RPS':>8}"
    )
    print(header)
    print("-" * len(header))
    for e in sorted(entries, key=lambda e: e["name"]):
        response_times = {int(k): v for k, v in e.get("response_times", {}).items()}
        num_requests = e["num_requests"]

        median = (
            median_from_dict(num_requests, response_times) if response_times else None
        )
        p95 = (
            calculate_response_time_percentile(response_times, num_requests, 0.95)
            if response_times
            else None
        )
        p99 = (
            calculate_response_time_percentile(response_times, num_requests, 0.99)
            if response_times
            else None
        )

        duration = e.get("last_request_timestamp", 0) - e.get("start_time", 0)
        avg_rps = num_requests / duration if duration > 0 else 0.0

        marker = " *" if "BURST" in e["name"] else ""
        print(
            f"{e['name'][:38]:<38} "
            f"{num_requests:>6} "
            f"{e['num_failures']:>5} "
            f"{fmt_ms(median):>6} "
            f"{fmt_ms(p95):>6} "
            f"{fmt_ms(p99):>6} "
            f"{fmt_ms(e.get('max_response_time')):>6} "
            f"{duration:>8.1f}s "
            f"{avg_rps:>7.1f}"
            f"{marker}"
        )
    print("-" * len(header))
    print(
        f"Total: {total_requests} requests, {total_failures} failures ({fail_rate:.2f}% failure rate)"
    )
    print(
        "(* = the synchronized contest-start burst call; Duration/Avg RPS span its first-to-last request)"
    )
    print()
    print("For request-rate-over-time and response-time-over-time charts,")
    run_dir = os.path.dirname(os.path.abspath(path)) or "."
    print(f"open the report: {os.path.join(run_dir, 'report.html')}")


if __name__ == "__main__":
    main()
