#!/usr/bin/env bash
# Start backend + frontend dev servers (macOS / Linux).
#   ./scripts/dev.sh
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

if [ ! -f .env ]; then
  cp .env.example .env
  secret=$(python3 -c "import secrets; print(secrets.token_urlsafe(48))")
  sed -i.bak "s|^SECRET_KEY=.*|SECRET_KEY=$secret|" .env && rm -f .env.bak
  echo "Created .env from .env.example (with a fresh SECRET_KEY) - add an API key (or use Ollama) before chatting."
fi
if [ ! -d backend/.venv ]; then
  python3 -m venv backend/.venv
  backend/.venv/bin/pip install -r backend/requirements-dev.txt
fi
[ -d frontend/node_modules ] || (cd frontend && npm install)

trap 'kill 0' EXIT
(cd backend && .venv/bin/uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
echo "Backend: http://localhost:8000/api/docs   Frontend: http://localhost:5173"
wait
