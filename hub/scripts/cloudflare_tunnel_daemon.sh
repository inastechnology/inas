#!/usr/bin/env bash
set -euo pipefail

# Run the provisioned Cloudflare Tunnel in the background.

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="$REPO_ROOT/.env"
RUN_DIR="$REPO_ROOT/.data/cloudflare"
PID_FILE="$RUN_DIR/cloudflared.pid"
LOG_FILE="$RUN_DIR/cloudflared.log"
INSTALL_CLOUDFLARED="false"
LOGLEVEL="info"

usage() {
  cat <<EOF
Usage: $0 [options] <start|stop|restart|status|logs>

Options:
  --env-file FILE          .env path. Default: ${ENV_FILE}
  --install-cloudflared    Download cloudflared into hub/.data/bin if missing
  --loglevel LEVEL         cloudflared log level. Default: ${LOGLEVEL}
  -h, --help               Show this help
EOF
}

command=""
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
    --loglevel)
      LOGLEVEL="$2"
      shift 2
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    start|stop|restart|status|logs)
      command="$1"
      shift
      ;;
    *)
      echo "Unknown option or command: $1" >&2
      usage >&2
      exit 1
      ;;
  esac
done

if [[ -z "$command" ]]; then
  usage >&2
  exit 1
fi

pid_from_file() {
  if [[ -f "$PID_FILE" ]]; then
    tr -d '[:space:]' < "$PID_FILE"
  fi
}

pid_is_running() {
  local pid="$1"
  [[ -n "$pid" ]] && kill -0 "$pid" >/dev/null 2>&1
}

status_command() {
  local pid
  pid="$(pid_from_file)"
  if pid_is_running "$pid"; then
    echo "cloudflared is running: pid=${pid}"
    echo "log: ${LOG_FILE}"
    return 0
  fi
  if [[ -n "$pid" ]]; then
    echo "cloudflared is not running; stale pid=${pid}" >&2
    return 1
  fi
  echo "cloudflared is not running"
  return 1
}

start_command() {
  mkdir -p "$RUN_DIR"
  local pid
  pid="$(pid_from_file)"
  if pid_is_running "$pid"; then
    echo "cloudflared is already running: pid=${pid}"
    return 0
  fi
  if [[ -n "$pid" ]]; then
    rm -f "$PID_FILE"
  fi

  local start_args=(--env-file "$ENV_FILE" start --loglevel "$LOGLEVEL")
  if [[ "$INSTALL_CLOUDFLARED" == "true" ]]; then
    start_args+=(--install-cloudflared)
  fi

  echo "Starting cloudflared daemon. Log: ${LOG_FILE}"
  (
    cd "$REPO_ROOT"
    nohup python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" "${start_args[@]}" >> "$LOG_FILE" 2>&1 < /dev/null &
    echo "$!" > "$PID_FILE"
  )
  pid="$(pid_from_file)"

  sleep 3
  if ! pid_is_running "$pid"; then
    echo "cloudflared exited during startup. Last log lines:" >&2
    tail -n 40 "$LOG_FILE" >&2 || true
    rm -f "$PID_FILE"
    return 1
  fi

  echo "cloudflared started: pid=${pid}"
}

stop_command() {
  local pid
  pid="$(pid_from_file)"
  if ! pid_is_running "$pid"; then
    rm -f "$PID_FILE"
    echo "cloudflared is not running"
    return 0
  fi

  echo "Stopping cloudflared: pid=${pid}"
  kill "$pid"
  for _ in {1..20}; do
    if ! pid_is_running "$pid"; then
      rm -f "$PID_FILE"
      echo "cloudflared stopped"
      return 0
    fi
    sleep 0.5
  done
  echo "cloudflared did not stop after SIGTERM: pid=${pid}" >&2
  return 1
}

case "$command" in
  start)
    start_command
    ;;
  stop)
    stop_command
    ;;
  restart)
    stop_command
    start_command
    ;;
  status)
    status_command
    ;;
  logs)
    mkdir -p "$RUN_DIR"
    touch "$LOG_FILE"
    tail -n 120 "$LOG_FILE"
    ;;
esac
