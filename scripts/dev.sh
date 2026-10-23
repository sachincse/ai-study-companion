#!/usr/bin/env bash
# Start backend + frontend dev servers (macOS / Linux).
#   ./scripts/dev.sh
#   ./scripts/dev.sh --setup-only   # setup only, no servers (used for testing)
# Every run repairs the setup: .env (with a random SECRET_KEY), backend/.venv (Python 3.11+) and the
# pip / npm installs, which run again after a failure or when requirements*.txt / package-lock.json change.
set -euo pipefail
ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")/.." && pwd)"
cd "$ROOT"

SETUP_ONLY=0
for arg in "$@"; do
  case "$arg" in
    --setup-only) SETUP_ONLY=1 ;;
    *) echo "Unknown option: $arg (the only option is --setup-only)" >&2; exit 2 ;;
  esac
done

VENV_DIR=backend/.venv
CR=$'\r'
# A SECRET_KEY line in .env, and what a generated key must look like.
SECRET_LINE='^[[:space:]]*(export[[:space:]]+)?SECRET_KEY[[:space:]]*='
SECRET_OK='^[A-Za-z0-9_-]{32,}$'

die() { echo "Error: $*" >&2; exit 1; }

trim() {
  local s=$1
  s=${s#"${s%%[![:space:]]*}"}
  s=${s%"${s##*[![:space:]]}"}
  printf '%s' "$s"
}

# X.Y.Z of an interpreter; fails when it does not run.
py_version() {
  local out
  out=$("$1" -c "import sys; print('%d.%d.%d' % sys.version_info[:3])" 2>/dev/null) || return 1
  printf '%s\n' "${out%"$CR"}"
}

# True for Python 3.11 or newer.
version_ok() {
  local major minor
  IFS=. read -r major minor _ <<< "$1"
  case "$major.$minor" in *[!0-9.]* | .* | *.) return 1 ;; esac
  [ "$major" -gt 3 ] || { [ "$major" -eq 3 ] && [ "$minor" -ge 11 ]; }
}

# The Python that creates backend/.venv: python3, else a versioned python3.1x, else python.
find_python() {
  local candidate version found=""
  for candidate in python3 python3.15 python3.14 python3.13 python3.12 python3.11 python; do
    command -v "$candidate" >/dev/null 2>&1 || continue
    version=$(py_version "$candidate") || continue
    if version_ok "$version"; then
      BASE_PY=$candidate
      BASE_PY_VERSION=$version
      return 0
    fi
    found="${found:+$found, }$candidate is Python $version"
  done
  die "Python 3.11 or newer is required to create backend/.venv, but ${found:-no working python3 was found on PATH}. Install it (python.org, Homebrew, or e.g. sudo apt install python3.11 python3.11-venv) and run this script again."
}

# bin/python on macOS / Linux; Scripts/python.exe when a Windows Python made the venv (Git Bash).
venv_python() {
  if [ -x "$VENV_DIR/bin/python" ]; then printf '%s\n' "$ROOT/$VENV_DIR/bin/python"
  elif [ -x "$VENV_DIR/Scripts/python.exe" ]; then printf '%s\n' "$ROOT/$VENV_DIR/Scripts/python.exe"
  fi
}

# Value of the last SECRET_KEY line (python-dotenv lets the last one win), unquoted, inline comment dropped.
current_secret() {
  local value
  value=$(grep -E "$SECRET_LINE" .env | tail -n 1 | tr -d '\r') || true
  value=$(trim "${value#*=}")
  case "$value" in
    \"*) value=${value#\"}; value=${value%%\"*} ;;
    \'*) value=${value#\'}; value=${value%%\'*} ;;
    *) value=$(printf '%s' "$value" | sed -E 's/[[:space:]]+#.*$//') ;;
  esac
  trim "$value"
}

# Same rule as backend/app/core/config.py: missing, empty, the "change-me" placeholder or under 32 bytes.
secret_is_weak() {
  case "$1" in "" | change-me*) return 0 ;; esac
  [ "$(printf '%s' "$1" | wc -c | tr -d ' ')" -lt 32 ]
}

# SHA-256 of the files' bytes back to back; a missing file counts as empty.
hash_files() {
  local f
  for f in "$@"; do
    if [ -f "$f" ]; then cat "$f"; fi
  done | "${SHA256[@]}" | cut -d ' ' -f 1
}

# An install is current when its stamp file holds the hash of the files it was installed from.
stamp_matches() { [ -f "$1" ] && [ "$(tr -d '\r\n' < "$1")" = "$2" ]; }

# .env: copied from .env.example on the first run.
if [ ! -f .env ]; then
  [ -f .env.example ] || die ".env.example is missing; restore it with: git checkout -- .env.example"
  cp .env.example .env
  echo "Created .env from .env.example - add an API key (or use Ollama) before chatting."
fi

command -v npm >/dev/null 2>&1 || die "npm was not found. Install Node.js 22.12 or newer (https://nodejs.org) and run this script again."
if command -v sha256sum >/dev/null 2>&1; then SHA256=(sha256sum)
elif command -v shasum >/dev/null 2>&1; then SHA256=(shasum -a 256)
else die "Neither sha256sum nor shasum was found; install coreutils (or perl's shasum) and run this script again."
fi

# backend/.venv: created with Python 3.11+; an existing venv is checked as well.
VENV_PY=$(venv_python)
if [ -z "$VENV_PY" ]; then
  find_python
  echo "Creating backend/.venv with $BASE_PY (Python $BASE_PY_VERSION)..."
  if [ -e "$VENV_DIR" ]; then had_venv=1; else had_venv=0; fi
  if ! "$BASE_PY" -m venv "$VENV_DIR"; then
    [ "$had_venv" = 1 ] || rm -rf "$VENV_DIR"
    die "Creating backend/.venv failed (see above). On Debian/Ubuntu install the venv module first (sudo apt install python3-venv, or python3.X-venv for your version) and run this script again."
  fi
  VENV_PY=$(venv_python)
  [ -n "$VENV_PY" ] || die "Creating backend/.venv left no python inside it. Delete backend/.venv and run this script again."
fi
VENV_VERSION=$(py_version "$VENV_PY") \
  || die "backend/.venv is broken: its python does not run (often the Python it was created from was removed or upgraded). Delete it (rm -rf backend/.venv) and run this script again."
version_ok "$VENV_VERSION" \
  || die "backend/.venv uses Python $VENV_VERSION, but 3.11 or newer is required. Delete it (rm -rf backend/.venv) and run this script again with Python 3.11+ installed."

# SECRET_KEY: replaced whenever it is weak, so a .env copied by hand gets one too (generated with the venv's python).
if secret_is_weak "$(current_secret)"; then
  secret=$("$VENV_PY" -c 'import secrets; print(secrets.token_urlsafe(48))') \
    || die "Could not generate a SECRET_KEY with $VENV_PY; .env was not changed. Run this script again."
  secret=${secret%"$CR"}
  [[ $secret =~ $SECRET_OK ]] || die "Could not generate a SECRET_KEY with $VENV_PY; .env was not changed. Run this script again."
  if grep -Eq "$SECRET_LINE" .env; then
    # Write through a temp file (no sed -i): an existing .env.bak is never touched, and a read-only or
    # symlinked .env is not silently replaced. [^CR]* keeps the line ending of a CRLF file, and -b, where
    # sed has it (GNU), stops Git Bash's sed from rewriting CRLF files as LF.
    sed_cmd=(sed)
    if sed -b -e '' < /dev/null > /dev/null 2>&1; then sed_cmd+=(-b); fi
    tmp=$(mktemp .env.devsh.XXXXXX) || die "Could not create a temporary file in $ROOT; .env was not changed."
    if "${sed_cmd[@]}" -E "s/^([[:space:]]*(export[[:space:]]+)?SECRET_KEY[[:space:]]*=)[^$CR]*/\\1$secret/" .env > "$tmp" && cat "$tmp" > .env; then
      rm -f "$tmp"
    else
      rm -f "$tmp"
      die "Could not write SECRET_KEY to .env; check that the file is writable and run this script again."
    fi
  else
    eol=""   # keep CRLF files CRLF (tr, not grep: Git Bash's grep hides CRs)
    if [ -n "$(tr -cd '\r' < .env)" ]; then eol=$CR; fi
    if [ -s .env ] && [ -n "$(tail -c 1 .env)" ]; then printf '%s\n' "$eol" >> .env; fi
    printf 'SECRET_KEY=%s%s\n' "$secret" "$eol" >> .env
  fi
  [ "$(current_secret)" = "$secret" ] || die "Could not write SECRET_KEY to .env; check that the file is writable and run this script again."
  echo "Generated a random SECRET_KEY in .env"
fi

# Backend packages: installed again when the stamp is missing or requirements*.txt changed.
BACKEND_STAMP=$VENV_DIR/.deps-installed
backend_hash=$(hash_files backend/requirements.txt backend/requirements-dev.txt)
if stamp_matches "$BACKEND_STAMP" "$backend_hash"; then
  echo "Backend dependencies are up to date."
else
  echo "Installing backend dependencies (pip install -r backend/requirements-dev.txt)..."
  rm -f "$BACKEND_STAMP"
  "$VENV_PY" -m pip install --disable-pip-version-check -r backend/requirements-dev.txt \
    || die "pip install failed (see above). Fix the cause (network, proxy, disk space) and run this script again; it retries the install."
  printf '%s\n' "$backend_hash" > "$BACKEND_STAMP"
fi

# Frontend packages: installed again when the stamp is missing or package-lock.json changed.
FRONTEND_STAMP=frontend/node_modules/.deps-installed
if stamp_matches "$FRONTEND_STAMP" "$(hash_files frontend/package-lock.json)"; then
  echo "Frontend dependencies are up to date."
else
  echo "Installing frontend dependencies (npm install)..."
  rm -f "$FRONTEND_STAMP"
  (cd frontend && npm install) \
    || die "npm install failed (see above). Fix the cause (network, proxy, Node.js older than 22.12) and run this script again; it retries the install."
  # Hashed after the install because npm may rewrite package-lock.json; an empty project gets no node_modules.
  mkdir -p frontend/node_modules
  frontend_hash=$(hash_files frontend/package-lock.json)
  printf '%s\n' "$frontend_hash" > "$FRONTEND_STAMP"
fi

if [ "$SETUP_ONLY" = 1 ]; then
  echo "Setup complete; servers not started (--setup-only)."
  exit 0
fi

trap 'kill 0' EXIT
(cd backend && "$VENV_PY" -m uvicorn app.main:app --reload --port 8000) &
(cd frontend && npm run dev) &
echo "Backend: http://localhost:8000/api/docs   Frontend: http://localhost:5173"
wait
