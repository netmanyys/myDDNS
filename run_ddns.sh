#!/usr/bin/env bash
set -euo pipefail

# Resolve script directory first so .env can be loaded safely even with `set -u`
SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

# Load .env into environment for this process
set -a
source "$SCRIPT_DIR/.env"
set +a

# Allow MYPATH from .env, fallback to this script directory
MYPATH="${MYPATH:-$SCRIPT_DIR}"

exec python3 "$MYPATH/cloudflare_ddns_updater.py"
