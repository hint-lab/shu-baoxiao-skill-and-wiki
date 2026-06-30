#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
cd "$ROOT_DIR"

HOST="${HOST:-127.0.0.1}"
PORT="${PORT:-8765}"
URL="http://${HOST}:${PORT}"

echo "Starting Shanghai University reimbursement agent"
echo "Workspace: $ROOT_DIR"

if ! command -v python3 >/dev/null 2>&1; then
  echo "python3 is required."
  exit 1
fi

if command -v lsof >/dev/null 2>&1 && lsof -nP -iTCP:"$PORT" -sTCP:LISTEN >/dev/null 2>&1; then
  echo "Port $PORT is already in use. Stop the old local service first, or run with another port:"
  echo "  PORT=8879 ./start_dev.sh"
  exit 1
fi

if [ -f package.json ]; then
  if [ ! -d node_modules ]; then
    echo "Installing frontend dependencies..."
    npm install
  fi

  echo "Building frontend..."
  npm run build:frontend
fi

echo "Initializing knowledge base..."
python3 tools/knowledge_seed.py --build --import-db

echo "Launching local service at $URL"
python3 -m uvicorn app:app --host "$HOST" --port "$PORT" &
SERVER_PID=$!

cleanup() {
  if kill -0 "$SERVER_PID" >/dev/null 2>&1; then
    kill "$SERVER_PID" >/dev/null 2>&1 || true
  fi
}
trap cleanup EXIT INT TERM

python3 - <<PY
import time
import urllib.request

url = "${URL}/api/settings/status"
for _ in range(80):
    try:
        with urllib.request.urlopen(url, timeout=0.5) as response:
            if 200 <= response.status < 500:
                raise SystemExit(0)
    except Exception:
        time.sleep(0.15)
raise SystemExit("Local service did not become ready.")
PY

echo "Ready: $URL"
if command -v open >/dev/null 2>&1; then
  open "$URL" >/dev/null 2>&1 || true
fi

wait "$SERVER_PID"
