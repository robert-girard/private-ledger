#!/usr/bin/env bash
set -euo pipefail

ROOT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
PORT="${SMOKE_TEST_PORT:-8011}"
TMP_DIR="$(mktemp -d "${TMPDIR:-/tmp}/private-ledger-smoke.XXXXXX")"
SERVER_LOG="$TMP_DIR/server.log"
SERVER_PID=""

cleanup() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
  rm -rf "$TMP_DIR"
}

trap cleanup EXIT

require_cmd() {
  if ! command -v "$1" >/dev/null 2>&1; then
    echo "Missing required command: $1" >&2
    exit 1
  fi
}

require_cmd npm
require_cmd uv
require_cmd curl

export PASSWORD_PEPPER="smoke-test-pepper"
export AUTH_SECRET_KEY="smoke-test-auth-secret"
export DATABASE_URL="sqlite:///$TMP_DIR/private-ledger.db"
export IMPORT_STORAGE_DIR="$TMP_DIR/imports"
export APP_HOST="127.0.0.1"
export APP_PORT="$PORT"

cd "$ROOT_DIR"

echo "Building frontend assets..."
npm --prefix frontend run build >/dev/null

echo "Starting backend on http://127.0.0.1:$PORT ..."
uv run --project backend uvicorn app.main:app --app-dir backend --host 127.0.0.1 --port "$PORT" >"$SERVER_LOG" 2>&1 &
SERVER_PID=$!

for _ in {1..30}; do
  if curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null; then
    break
  fi
  sleep 1
done

if ! curl -fsS "http://127.0.0.1:$PORT/api/health" >/dev/null; then
  echo "Backend did not become healthy." >&2
  cat "$SERVER_LOG" >&2
  exit 1
fi

echo "Bootstrapping admin user..."
uv run --project backend python -m app.bootstrap_admin \
  --email admin@example.com \
  --display-name "Smoke Test Admin" \
  --password secret-pass >/dev/null

echo "Checking auth, headers, and SPA serving..."
LOGIN_RESPONSE="$TMP_DIR/login.json"
ROOT_HEADERS="$TMP_DIR/root-headers.txt"
curl -fsS \
  -H "Content-Type: application/json" \
  -d '{"email":"admin@example.com","password":"secret-pass"}' \
  "http://127.0.0.1:$PORT/api/auth/login" >"$LOGIN_RESPONSE"

grep -q '"access_token"' "$LOGIN_RESPONSE"
curl -fsS -D "$ROOT_HEADERS" -o /dev/null "http://127.0.0.1:$PORT/"
grep -qi '^content-security-policy:' "$ROOT_HEADERS"
grep -qi '^strict-transport-security:' "$ROOT_HEADERS"
curl -fsS "http://127.0.0.1:$PORT/" | grep -q '<!doctype html>'

echo "Smoke test passed."
