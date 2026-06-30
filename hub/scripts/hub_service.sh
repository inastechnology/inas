#!/usr/bin/env bash
set -euo pipefail

SERVICE_NAME="inas-device-hub@main"
MQTT_SERVICE_NAME="mosquitto"

usage() {
  cat <<EOF
Usage: $0 <command>

Commands:
  start       Enable and start MQTT broker and INA Device Hub
  stop        Stop INA Device Hub
  restart     Restart INA Device Hub
  status      Show MQTT broker and INA Device Hub status
  logs        Follow INA Device Hub logs
EOF
}

require_root_for_systemctl_write() {
  if [[ "$(id -u)" -ne 0 ]]; then
    exec sudo "$0" "$@"
  fi
}

command="${1:-start}"

case "$command" in
  start)
    require_root_for_systemctl_write "$@"
    systemctl enable --now "$MQTT_SERVICE_NAME"
    systemctl enable --now "$SERVICE_NAME"
    systemctl status "$SERVICE_NAME" --no-pager
    ;;
  stop)
    require_root_for_systemctl_write "$@"
    systemctl stop "$SERVICE_NAME"
    ;;
  restart)
    require_root_for_systemctl_write "$@"
    systemctl restart "$SERVICE_NAME"
    systemctl status "$SERVICE_NAME" --no-pager
    ;;
  status)
    systemctl status "$MQTT_SERVICE_NAME" --no-pager
    systemctl status "$SERVICE_NAME" --no-pager
    ;;
  logs)
    journalctl -u "$SERVICE_NAME" -f
    ;;
  -h|--help|help)
    usage
    ;;
  *)
    usage >&2
    exit 2
    ;;
esac
