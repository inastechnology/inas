#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"

env_args=()
start_args=()

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      env_args+=(--env-file "$2")
      shift 2
      ;;
    --dry-run|--write-env|--name|--hostname|--origin-url)
      if [[ "$1" == "--dry-run" || "$1" == "--write-env" ]]; then
        env_args+=("$1")
        shift
      else
        env_args+=("$1" "$2")
        shift 2
      fi
      ;;
    *)
      start_args+=("$1")
      shift
      ;;
  esac
done

exec python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "${env_args[@]}" start "${start_args[@]}"
