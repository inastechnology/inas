#!/usr/bin/env bash
set -euo pipefail

# Provision Cloudflare hosted resources, then run the local hub and tunnel
# together. This is intended for foreground use during setup/operation.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="$REPO_ROOT/.env"
INSTALL_CLOUDFLARED="false"
NO_HUB="false"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --env-file FILE          .env path. Default: ${ENV_FILE}
  --install-cloudflared    Download cloudflared into hub/.data/bin if missing
  --no-hub                 Do not start the local hub process; only start tunnel
  -h, --help               Show this help
EOF
}

env_file_value() {
  local key="$1"
  local line
  local value
  while IFS= read -r line || [[ -n "$line" ]]; do
    line="${line#"${line%%[![:space:]]*}"}"
    [[ "$line" == "$key="* ]] || continue
    value="${line#*=}"
    value="${value%$'\r'}"
    value="${value#\"}"
    value="${value%\"}"
    value="${value#\'}"
    value="${value%\'}"
    printf '%s' "$value"
    return 0
  done < "$ENV_FILE"
  return 1
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --env-file)
      ENV_FILE="$2"
      shift 2
      ;;
    --install-cloudflared)
      INSTALL_CLOUDFLARED="true"
      shift
      ;;
    --no-hub)
      NO_HUB="true"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

LOCK_ROOT="$REPO_ROOT/.data/cloudflare"
LOCK_DIR="$LOCK_ROOT/hosted-up.lock"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Cloudflare hosted up is already running. Lock: $LOCK_DIR" >&2
  exit 1
fi
echo "$$" > "$LOCK_DIR/pid"
cleanup_run_lock() {
  rm -rf "$LOCK_DIR"
}
trap cleanup_run_lock EXIT INT TERM

setup_args=(--env-file "$ENV_FILE")
if [[ "$INSTALL_CLOUDFLARED" == "true" ]]; then
  setup_args+=(--install-cloudflared)
fi
"$SCRIPT_DIR/cloudflare_hosted_setup.sh" "${setup_args[@]}"

hub_pid=""
tunnel_pid=""
cleanup() {
  if [[ -n "$hub_pid" ]] && kill -0 "$hub_pid" >/dev/null 2>&1; then
    kill "$hub_pid" >/dev/null 2>&1 || true
    wait "$hub_pid" >/dev/null 2>&1 || true
  fi
  if [[ -n "$tunnel_pid" ]] && kill -0 "$tunnel_pid" >/dev/null 2>&1; then
    kill "$tunnel_pid" >/dev/null 2>&1 || true
    wait "$tunnel_pid" >/dev/null 2>&1 || true
  fi
  cleanup_run_lock
}
trap cleanup EXIT INT TERM

if [[ "$NO_HUB" != "true" ]]; then
  echo "Starting local hub..."
  (
    cd "$REPO_ROOT"
    ./serve.sh
  ) &
  hub_pid="$!"
  hub_startup_wait_seconds="${CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS:-}"
  if [[ -z "$hub_startup_wait_seconds" ]]; then
    hub_startup_wait_seconds="$(env_file_value CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS || true)"
  fi
  hub_startup_wait_seconds="${hub_startup_wait_seconds:-3}"
  if ! [[ "$hub_startup_wait_seconds" =~ ^[0-9]+([.][0-9]+)?$ ]]; then
    echo "CLOUDFLARE_HOSTED_HUB_STARTUP_WAIT_SECONDS must be a number: ${hub_startup_wait_seconds}" >&2
    exit 1
  fi
  sleep "$hub_startup_wait_seconds"
  if ! kill -0 "$hub_pid" >/dev/null 2>&1; then
    hub_status=1
    wait "$hub_pid" || hub_status="$?"
    echo "Local hub exited during startup with status ${hub_status}. Tunnel was not started." >&2
    exit "$hub_status"
  fi
fi

start_args=(--env-file "$ENV_FILE" start)
if [[ "$INSTALL_CLOUDFLARED" == "true" ]]; then
  start_args+=(--install-cloudflared)
fi
if [[ "$NO_HUB" == "true" ]]; then
  python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "${start_args[@]}"
else
  python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "${start_args[@]}" &
  tunnel_pid="$!"
  set +e
  wait -n "$hub_pid" "$tunnel_pid"
  exit_status="$?"
  set -e
  if ! kill -0 "$hub_pid" >/dev/null 2>&1; then
    echo "Local hub process exited; stopping Cloudflare Tunnel." >&2
  elif ! kill -0 "$tunnel_pid" >/dev/null 2>&1; then
    echo "Cloudflare Tunnel process exited; stopping local hub." >&2
  fi
  exit "$exit_status"
fi
