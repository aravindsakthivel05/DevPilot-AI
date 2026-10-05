#!/usr/bin/env bash
# Bootstrap DevPilot's project-local dependencies and start its local web app.
set -Eeuo pipefail

ROOT="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
VENV="${ROOT}/.venv"
FRONTEND="${ROOT}/frontend"
HOST="${DEVPILOT_HOST:-127.0.0.1}"
PORT="${DEVPILOT_PORT:-8000}"
SETUP_ONLY=0
NO_BROWSER=0
SERVER_PID=""

usage() {
  cat <<'USAGE'
Usage: ./setup_and_run.sh [--setup-only] [--no-browser]

  --setup-only  Install project dependencies and build the UI, then exit.
  --no-browser  Start the server without opening a browser window.

Configuration can be supplied with environment variables. For example:
  DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 \
  DEVPILOT_LLM_MODEL=qwen2.5-coder:14b ./setup_and_run.sh

Set DEVPILOT_PORT to use a port other than 8000.
USAGE
}

while (($#)); do
  case "$1" in
    --setup-only) SETUP_ONLY=1 ;;
    --no-browser) NO_BROWSER=1 ;;
    -h|--help) usage; exit 0 ;;
    *) printf 'Unknown option: %s\n\n' "$1" >&2; usage >&2; exit 2 ;;
  esac
  shift
done

fail() {
  printf 'Setup error: %s\n' "$1" >&2
  exit 1
}

check_prerequisites() {
  command -v git >/dev/null 2>&1 || fail "Git is required to ingest GitHub repositories and check draft diffs. Install Git and retry."
  command -v python3 >/dev/null 2>&1 || fail "Python 3.11 or newer is required. Install it, then run this script again. On macOS with Homebrew: brew install python@3.12."
  command -v node >/dev/null 2>&1 || fail "Node.js 18 or newer is required. Install Node.js from https://nodejs.org/ or with Homebrew: brew install node."
  command -v npm >/dev/null 2>&1 || fail "npm is required (it is normally installed with Node.js). Reinstall Node.js from https://nodejs.org/."

  python3 -c 'import sys; raise SystemExit(0 if sys.version_info >= (3, 11) else 1)' \
    || fail "Python 3.11 or newer is required; found $(python3 --version 2>&1)."
  node -e 'process.exit(Number(process.versions.node.split(".")[0]) >= 18 ? 0 : 1)' \
    || fail "Node.js 18 or newer is required; found $(node --version)."
}

port_is_open() {
  python3 - "$HOST" "$PORT" <<'PY'
import socket
import sys

with socket.socket() as sock:
    sock.settimeout(0.3)
    raise SystemExit(0 if sock.connect_ex((sys.argv[1], int(sys.argv[2]))) == 0 else 1)
PY
}

setup_project() {
  printf '\n==> Preparing Python environment\n'
  if [[ ! -x "${VENV}/bin/python" ]]; then
    python3 -m venv "$VENV" || fail "Could not create .venv. On Debian/Ubuntu, install python3-venv and try again."
  fi
  mkdir -p "${ROOT}/.devpilot"
  "${VENV}/bin/python" - "${ROOT}/pyproject.toml" "${ROOT}/.devpilot/requirements.txt" <<'PY'
import sys
import tomllib
from pathlib import Path

project_file, requirements_file = map(Path, sys.argv[1:])
project = tomllib.loads(project_file.read_text())
requirements = project["project"]["dependencies"]
requirements_file.write_text("\n".join(requirements) + "\n")
PY
  "${VENV}/bin/python" -m pip install -r "${ROOT}/.devpilot/requirements.txt"

  printf '\n==> Installing frontend dependencies\n'
  if [[ ! -d "${FRONTEND}/node_modules" ]]; then
    (cd "$FRONTEND" && npm ci)
  fi

  printf '\n==> Building the web interface\n'
  (cd "$FRONTEND" && npm run build)

}

configure_optional_services() {
  local available_models candidate
  if [[ -z "${DEVPILOT_LLM_BASE_URL:-}" || -z "${DEVPILOT_LLM_MODEL:-}" ]]; then
    if command -v ollama >/dev/null 2>&1; then
      available_models="$(ollama list 2>/dev/null | awk 'NR > 1 { print $1 }' || true)"
      for candidate in qwen2.5-coder:14b qwen2.5-coder:7b; do
        if printf '%s\n' "$available_models" | grep -Fxq "$candidate"; then
          export DEVPILOT_LLM_BASE_URL="${DEVPILOT_LLM_BASE_URL:-http://127.0.0.1:11434/v1}"
          export DEVPILOT_LLM_MODEL="${DEVPILOT_LLM_MODEL:-$candidate}"
          break
        fi
      done
    fi
  fi

  export DEVPILOT_LANGGRAPH_ENABLED="${DEVPILOT_LANGGRAPH_ENABLED:-0}"
  export DEVPILOT_OLLAMA_NUM_CTX="${DEVPILOT_OLLAMA_NUM_CTX:-8192}"
  export DEVPILOT_SOURCE_TOKEN_BUDGET="${DEVPILOT_SOURCE_TOKEN_BUDGET:-4096}"
  export DEVPILOT_MODEL_SOURCE_SELECTION="${DEVPILOT_MODEL_SOURCE_SELECTION:-1}"
  export DEVPILOT_VERIFY_CLAIMS="${DEVPILOT_VERIFY_CLAIMS:-1}"
  export DEVPILOT_REPAIR_REJECTED_CLAIMS="${DEVPILOT_REPAIR_REJECTED_CLAIMS:-1}"
  export DEVPILOT_PROVIDER_TIMEOUT_SECONDS="${DEVPILOT_PROVIDER_TIMEOUT_SECONDS:-180}"

  if [[ -n "${DEVPILOT_LLM_BASE_URL:-}" && -n "${DEVPILOT_LLM_MODEL:-}" ]]; then
    printf 'Chat model: configured (%s)\n' "$DEVPILOT_LLM_MODEL"
  else
    printf 'Chat model: not configured; repository indexing and Evidence only answers still work.\n'
    printf 'To enable local AI answers, install Ollama and a model appropriate for available memory. For the tested configuration: ollama pull qwen2.5-coder:14b\n'
    printf 'Then start this script with DEVPILOT_LLM_BASE_URL=http://127.0.0.1:11434/v1 and DEVPILOT_LLM_MODEL=qwen2.5-coder:14b.\n'
  fi

  export DEVPILOT_LEGACY_EXECUTION="${DEVPILOT_LEGACY_EXECUTION:-0}"
  if [[ "$DEVPILOT_LANGGRAPH_ENABLED" == "1" ]]; then
    "${VENV}/bin/python" -m pip install 'langgraph>=1.2,<2' 'langgraph-checkpoint-sqlite>=3.1,<4'
  fi
  if [[ -n "${DEVPILOT_NEURAL_RERANKER:-}" ]]; then
    "${VENV}/bin/python" -m pip install 'sentence-transformers>=5,<6'
    printf 'Local reranker: %s (weights downloaded on first use)\n' "$DEVPILOT_NEURAL_RERANKER"
  fi
  if [[ -z "${DEVPILOT_EMBEDDING_MODEL:-}" ]] && command -v ollama >/dev/null 2>&1; then
    if ollama list 2>/dev/null | awk 'NR > 1 {print $1}' | grep -Fxq 'nomic-embed-text:latest'; then
      export DEVPILOT_EMBEDDING_MODEL=nomic-embed-text:latest
      export DEVPILOT_EMBEDDING_BASE_URL=http://127.0.0.1:11434/v1
    fi
  fi
  printf 'Core: source analysis, answers and unverified suggestions; Docker is not required.\n'
  printf 'Embeddings: %s\n' "${DEVPILOT_EMBEDDING_MODEL:-not configured; use ollama pull nomic-embed-text to enable semantic search}"

}

stop_server() {
  if [[ -n "$SERVER_PID" ]] && kill -0 "$SERVER_PID" 2>/dev/null; then
    kill "$SERVER_PID" 2>/dev/null || true
    wait "$SERVER_PID" 2>/dev/null || true
  fi
}

wait_for_server() {
  local attempt
  for attempt in {1..40}; do
    if ! kill -0 "$SERVER_PID" 2>/dev/null; then
      wait "$SERVER_PID" || true
      fail "The backend stopped before it became ready. Check the error above."
    fi
    if "${VENV}/bin/python" - "$HOST" "$PORT" <<'PY' >/dev/null 2>&1
import sys
import urllib.request

try:
    urllib.request.urlopen(f"http://{sys.argv[1]}:{sys.argv[2]}/api/health", timeout=1)
except Exception:
    raise SystemExit(1)
PY
    then
      return 0
    fi
    sleep 1
  done
  fail "The backend did not become ready at http://${HOST}:${PORT}. Check the server output above."
}

open_browser() {
  local url="http://${HOST}:${PORT}"
  if [[ "$NO_BROWSER" -eq 1 ]]; then
    return 0
  fi
  case "$(uname -s)" in
    Darwin) open "$url" >/dev/null 2>&1 || true ;;
    Linux)
      if command -v xdg-open >/dev/null 2>&1; then
        xdg-open "$url" >/dev/null 2>&1 || true
      fi
      ;;
  esac
}

check_prerequisites
if [[ "$SETUP_ONLY" -eq 0 ]] && port_is_open; then
  fail "Port ${PORT} is already in use. Stop the other service or choose another port with DEVPILOT_PORT."
fi

setup_project
configure_optional_services

if [[ "$SETUP_ONLY" -eq 1 ]]; then
  printf '\nSetup complete. Run ./setup_and_run.sh to start DevPilot.\n'
  exit 0
fi

printf '\n==> Starting DevPilot at http://%s:%s\n' "$HOST" "$PORT"
printf 'Use “Try the example” to load the included sample, or add a local folder or public GitHub URL.\n'
printf 'Press Ctrl+C here to stop DevPilot.\n\n'
cd "$ROOT"
"${VENV}/bin/uvicorn" backend.main:app --host "$HOST" --port "$PORT" &
SERVER_PID=$!
trap stop_server EXIT INT TERM
wait_for_server
open_browser
wait "$SERVER_PID"
