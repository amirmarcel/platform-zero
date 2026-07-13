#!/usr/bin/env bash
# Steady traffic generator against demo-api's /work endpoint, so there's a
# p99 and an error rate to actually measure on the dashboard
# (observability/dashboards/demo-api.json) while diagnosing an alert from
# docs/runbooks/demo-api.md. Not a chaos tool: it never touches LATENCY_MS
# or ERROR_RATE itself — the incident is a config change through the golden
# path (services/demo-api/service.yaml), this just generates load against it.
#
# Usage:
#   kubectl port-forward -n demo-api svc/demo-api 8080:8080 &
#   scripts/load.sh                        # 10 rps for 60s against localhost:8080
#   scripts/load.sh --rps 50 --duration 300
#   scripts/load.sh --host localhost --port 8080 --path /work
set -euo pipefail

host="localhost"
port="8080"
path="/work"
rps=10
duration=60

usage() {
  echo "Usage: $0 [--host HOST] [--port PORT] [--path PATH] [--rps N] [--duration SECONDS]"
}

while [ $# -gt 0 ]; do
  case "$1" in
    --host) host="$2"; shift 2 ;;
    --port) port="$2"; shift 2 ;;
    --path) path="$2"; shift 2 ;;
    --rps) rps="$2"; shift 2 ;;
    --duration) duration="$2"; shift 2 ;;
    -h|--help) usage; exit 0 ;;
    *) echo "unknown argument: $1" >&2; usage >&2; exit 2 ;;
  esac
done

if ! [[ "$rps" =~ ^[0-9]+$ ]] || [ "$rps" -lt 1 ]; then
  echo "error: --rps must be a positive integer, got '$rps'" >&2
  exit 2
fi
if ! [[ "$duration" =~ ^[0-9]+$ ]] || [ "$duration" -lt 1 ]; then
  echo "error: --duration must be a positive integer, got '$duration'" >&2
  exit 2
fi
if ! command -v curl >/dev/null 2>&1; then
  echo "error: curl not found on PATH" >&2
  exit 2
fi

url="http://${host}:${port}${path}"
echo "load: ${rps} req/s against ${url} for ${duration}s"

# Requests are fired in the background so a slow/timed-out one can't stall
# the RPS cadence; per-request success/failure is deliberately not tracked
# here — the point of this script is to produce traffic, and the actual
# error rate and latency are what Prometheus/Grafana measure (see "Confirm
# impact" in docs/runbooks/demo-api.md), not this script's own counters.
total_issued=0

for ((second = 0; second < duration; second++)); do
  batch_start=$(date +%s.%N)

  for ((i = 0; i < rps; i++)); do
    curl -s -o /dev/null --max-time 5 "$url" &
    total_issued=$((total_issued + 1))
  done

  batch_end=$(date +%s.%N)
  sleep_for=$(awk -v a="$batch_start" -v b="$batch_end" 'BEGIN { s = 1 - (b - a); if (s < 0) s = 0; printf "%.3f", s }')
  sleep "$sleep_for"

  if (( (second + 1) % 10 == 0 )); then
    echo "load: $((second + 1))s elapsed, ${total_issued} requests issued so far"
  fi
done

wait
echo "load: done, ${total_issued} requests issued"
