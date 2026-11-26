#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT_DIR"

export PYTHONPATH="$ROOT_DIR"

API_LOG="/tmp/truehire_api.log"
WEB_LOG="/tmp/truehire_web.log"

API_PID=""
WEB_PID=""

cleanup() {
  echo ""
  echo "Shutting down TrueHire dev services..."
  for pid in "${WEB_PID:-}" "${API_PID:-}"; do
    if [ -n "${pid:-}" ] && kill -0 "$pid" 2>/dev/null; then
      # Kill process group if possible so child reloaders/workers exit cleanly
      pkill -TERM -P "$pid" 2>/dev/null || true
      kill -TERM "$pid" 2>/dev/null || true
      wait "$pid" 2>/dev/null || true
    fi
  done
  echo "Stopped cleanly."
}

trap cleanup EXIT INT TERM

echo "Starting FastAPI on http://127.0.0.1:8000 (log: $API_LOG)..."
uvicorn app.api.main:app --host 127.0.0.1 --port 8000 --reload >"$API_LOG" 2>&1 &
API_PID=$!

echo "Starting Next.js dev server in web/ (log: $WEB_LOG)..."
(cd "$ROOT_DIR/web" && npm run dev) >"$WEB_LOG" 2>&1 &
WEB_PID=$!

echo "TrueHire running. Press Ctrl+C to stop both services."
echo "  API : http://127.0.0.1:8000/health"
echo "  Web : http://localhost:3000"

wait "$API_PID" "$WEB_PID"
