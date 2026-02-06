#!/usr/bin/env bash
set -euo pipefail

# Load .env into environment for this process
set -a
source /Users/yan/Dev/my-ddns/.env
set +a

exec python3 /Users/yan/Dev/my-ddns/cloudflare_ddns_updater.py
