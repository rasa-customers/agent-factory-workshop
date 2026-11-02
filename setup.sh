#!/usr/bin/env bash
# One-command local setup for the Agent Factory workshop.
#   ./setup.sh [--llm-key KEY] [--base-url URL] [--license LICENSE]
# Safe to re-run. Values you pass are written to .env; values already in .env are kept.
set -euo pipefail
cd "$(dirname "$0")"

LLM_KEY="" BASE_URL="" LICENSE=""
while [[ $# -gt 0 ]]; do
  case "$1" in
    --llm-key) LLM_KEY="$2"; shift 2 ;;
    --base-url) BASE_URL="$2"; shift 2 ;;
    --license) LICENSE="$2"; shift 2 ;;
    -h|--help) sed -n '2,4p' "$0"; exit 0 ;;
    *) echo "Unknown option: $1"; exit 2 ;;
  esac
done

say() { printf '\n\033[1;36m==> %s\033[0m\n' "$1"; }

say "Checking for uv"
if ! command -v uv >/dev/null 2>&1; then
  curl -LsSf https://astral.sh/uv/install.sh | sh
  export PATH="$HOME/.local/bin:$PATH"
fi

say "Checking Python (3.11–3.13)"
if ! uv python find '>=3.11,<3.14' >/dev/null 2>&1; then
  echo "Installing Python 3.12 with uv..."
  uv python install 3.12 || {
    echo "Could not get Python 3.11–3.13. On Windows, run this inside WSL (https://learn.microsoft.com/windows/wsl/install)."
    exit 1
  }
fi

say "Installing dependencies (this takes a minute or two)"
uv sync --python '>=3.11,<3.14'

say "Installing the headless browser the factory uses to check its work"
if [[ "$(uname)" == "Linux" ]]; then
  uv run playwright install --with-deps chromium || uv run playwright install chromium
else
  uv run playwright install chromium
fi

say "Writing .env"
touch .env
set_env() {  # set_env NAME VALUE — replace or append, only if VALUE is non-empty
  local name="$1" value="$2"
  [[ -z "$value" ]] && return 0
  if grep -q "^${name}=" .env; then
    grep -v "^${name}=" .env > .env.tmp && mv .env.tmp .env
  fi
  echo "${name}=${value}" >> .env
}
grep -q "^OPENAI_BASE_URL=" .env || set_env OPENAI_BASE_URL "${BASE_URL:-https://api.openai.com/v1}"
set_env OPENAI_API_KEY "$LLM_KEY"
set_env OPENAI_BASE_URL "$BASE_URL"
set_env RASA_LICENSE "$LICENSE"
chmod 600 .env

say "Downloading the Mantle docs the factory reads while building agents"
(set -a; source ./.env; set +a; cd templates/mantle_agent && uv run rasa tools init docs mantle </dev/null >/dev/null 2>&1) \
  || echo "  (skipped — needs RASA_LICENSE; re-run ./setup.sh once you have it. The factory still works from BUILDING.md.)"

say "Checking your setup"
uv run workshop doctor || {
  echo
  echo "Fix the items above (edit .env), then run: uv run workshop doctor"
  exit 0
}
echo
echo "Done. Start everything with:  uv run workshop up"
