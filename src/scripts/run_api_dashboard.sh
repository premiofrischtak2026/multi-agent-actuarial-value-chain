#!/usr/bin/env bash
# Start the FastAPI API and the Vite dashboard. Ctrl+C stops both.
#
#   API_PORT=8000 DASHBOARD_PORT=5173 ./run_api_dashboard.sh
set -euo pipefail
SCRIPT_DIR="$(cd "$(dirname "$0")" && pwd)"
SRC_DIR="$(cd "$SCRIPT_DIR/.." && pwd)"
PROJECT_ROOT="$(cd "$SRC_DIR/.." && pwd)"

API_PORT="${API_PORT:-8000}"
DASHBOARD_PORT="${DASHBOARD_PORT:-5173}"

cd "$SRC_DIR"
uv run --project "$PROJECT_ROOT" python -m main serve --port "$API_PORT" &
API_PID=$!

cleanup() { kill "$API_PID" 2>/dev/null || true; }
trap cleanup EXIT

cd "$SRC_DIR/dashboard"
npm run dev -- --port "$DASHBOARD_PORT" &
DASH_PID=$!
trap 'kill "$API_PID" "$DASH_PID" 2>/dev/null || true' EXIT

wait
