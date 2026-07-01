#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

has_command="false"
for arg in "$@"; do
  case "$arg" in
    check|provision|install-cloudflared|start)
      has_command="true"
      break
      ;;
  esac
done

if [[ "$has_command" == "true" ]]; then
  exec python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "$@"
fi

exec python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "$@" provision
