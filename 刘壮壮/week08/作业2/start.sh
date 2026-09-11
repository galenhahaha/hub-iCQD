#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")"
HOST="${BACKEND_HOST:-127.0.0.1}"
PORT="${BACKEND_PORT:-8000}"
if python3 -c "import socket,sys; s=socket.socket(); r=s.connect_ex(('127.0.0.1', int(sys.argv[1]))); s.close(); sys.exit(0 if r==0 else 1)" "$PORT"; then
  echo "[start] :$PORT in use, switching to 8001"
  PORT=8001
fi
echo "[start] http://${HOST}:${PORT}"
exec python3 -m uvicorn backend.app:app --reload --host "$HOST" --port "$PORT"
