#!/usr/bin/env bash
set -euo pipefail

# Configure this host as an INA irrigation config server.
# - installs and configures chrony as a local NTP server
# - writes default device-config values into .env
# - optionally installs the ina-device-hub systemd services
#
# Usage:
#   sudo ./scripts/setup_config_server.sh \
#     --target-dir /opt/ina-device-hub \
#     --user pi \
#     --ntp-server-name my_device.local \
#     --allow-cidr 192.168.0.0/24

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

TARGET_USER="${SUDO_USER:-inas-usr}"
TARGET_DIR=""
ALLOW_CIDR="192.168.0.0/24"
NTP_SERVER_NAME=""
TIMEZONE_OFFSET_SEC="32400"
MOISTURE_THRESHOLD="35"
INSTALL_APP_SERVICE="true"
CONFIGURE_FIREWALL="true"
CHRONY_DROPIN="/etc/chrony/conf.d/ina-device-hub.conf"

usage() {
  cat <<EOF
Usage: sudo $0 [options]

Options:
  --user USER                         App service user. Default: ${TARGET_USER}
  --target-dir DIR                    Install directory for ina-device-hub
  --allow-cidr CIDR                   LAN CIDR allowed to use NTP. Default: ${ALLOW_CIDR}
  --ntp-server-name HOST              Value published as ntp_server. Default: local hostname
  --timezone-offset-sec SECONDS       Default timezone offset. Default: ${TIMEZONE_OFFSET_SEC}
  --moisture-threshold VALUE          Default moisture threshold. Default: ${MOISTURE_THRESHOLD}
  --skip-app-install                  Do not invoke scripts/install_service.sh
  --skip-firewall                     Do not modify ufw/firewalld rules
  -h, --help                          Show this help
EOF
}

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="$2"
      shift 2
      ;;
    --target-dir)
      TARGET_DIR="$2"
      shift 2
      ;;
    --allow-cidr)
      ALLOW_CIDR="$2"
      shift 2
      ;;
    --ntp-server-name)
      NTP_SERVER_NAME="$2"
      shift 2
      ;;
    --timezone-offset-sec)
      TIMEZONE_OFFSET_SEC="$2"
      shift 2
      ;;
    --moisture-threshold)
      MOISTURE_THRESHOLD="$2"
      shift 2
      ;;
    --skip-app-install)
      INSTALL_APP_SERVICE="false"
      shift
      ;;
    --skip-firewall)
      CONFIGURE_FIREWALL="false"
      shift
      ;;
    -h|--help)
      usage
      exit 0
      ;;
    *)
      echo "Unknown option: $1" >&2
      usage
      exit 1
      ;;
  esac
done

if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root." >&2
  exit 2
fi

if [[ -z "$NTP_SERVER_NAME" ]]; then
  NTP_SERVER_NAME="$(hostname -f 2>/dev/null || hostname)"
fi

if ! [[ "$TIMEZONE_OFFSET_SEC" =~ ^-?[0-9]+$ ]]; then
  echo "--timezone-offset-sec must be an integer" >&2
  exit 1
fi

if ! [[ "$MOISTURE_THRESHOLD" =~ ^[0-9]+$ ]] || (( MOISTURE_THRESHOLD < 0 || MOISTURE_THRESHOLD > 100 )); then
  echo "--moisture-threshold must be between 0 and 100" >&2
  exit 1
fi

if [[ -z "$TARGET_DIR" ]]; then
  TARGET_HOME="$(getent passwd "$TARGET_USER" | cut -d: -f6 || true)"
  if [[ -z "$TARGET_HOME" ]]; then
    TARGET_HOME="/home/$TARGET_USER"
  fi
  TARGET_DIR="$TARGET_HOME/ina-device-hub"
fi

ensure_pkg() {
  local pkg="$1"
  if command -v apt-get >/dev/null 2>&1; then
    export DEBIAN_FRONTEND=noninteractive
    apt-get update
    apt-get install -y "$pkg"
    return 0
  fi

  if command -v dnf >/dev/null 2>&1; then
    dnf install -y "$pkg"
    return 0
  fi

  if command -v yum >/dev/null 2>&1; then
    yum install -y "$pkg"
    return 0
  fi

  echo "Unsupported package manager. Install '$pkg' manually." >&2
  return 1
}

upsert_env_var() {
  local env_file="$1"
  local key="$2"
  local value="$3"

  if [[ ! -f "$env_file" ]]; then
    touch "$env_file"
  fi

  if grep -qE "^${key}=" "$env_file"; then
    sed -i "s|^${key}=.*|${key}=\"${value}\"|" "$env_file"
  else
    printf '%s="%s"\n' "$key" "$value" >> "$env_file"
  fi
}

install_app_service() {
  if [[ "$INSTALL_APP_SERVICE" != "true" ]]; then
    echo "Skipping app service install"
    return 0
  fi

  echo "Installing ina-device-hub services into ${TARGET_DIR}"
  "$REPO_ROOT/scripts/install_service.sh" --user "$TARGET_USER" --target-dir "$TARGET_DIR"
}

configure_device_config_defaults() {
  local env_file="$TARGET_DIR/.env"

  echo "Writing device-config defaults to ${env_file}"
  upsert_env_var "$env_file" "DEVICE_CONFIG_DEFAULT_NTP_SERVER" "$NTP_SERVER_NAME"
  upsert_env_var "$env_file" "DEVICE_CONFIG_DEFAULT_TIMEZONE_OFFSET_SEC" "$TIMEZONE_OFFSET_SEC"
  upsert_env_var "$env_file" "DEVICE_CONFIG_DEFAULT_MOISTURE_THRESHOLD" "$MOISTURE_THRESHOLD"
  chown "$TARGET_USER":"$TARGET_USER" "$env_file" || true
  chmod 600 "$env_file" || true
}

configure_chrony() {
  echo "Installing chrony"
  ensure_pkg chrony

  mkdir -p "$(dirname "$CHRONY_DROPIN")"
  cat > "$CHRONY_DROPIN" <<EOF
# Managed by setup_config_server.sh
allow ${ALLOW_CIDR}
local stratum 10
bindaddress 0.0.0.0
EOF

  if systemctl list-unit-files | grep -q '^chronyd\.service'; then
    systemctl enable --now chronyd.service
    systemctl restart chronyd.service
    return 0
  fi

  systemctl enable --now chrony.service
  systemctl restart chrony.service
}

configure_firewall() {
  if [[ "$CONFIGURE_FIREWALL" != "true" ]]; then
    echo "Skipping firewall configuration"
    return 0
  fi

  if command -v ufw >/dev/null 2>&1; then
    ufw allow from "$ALLOW_CIDR" to any port 123 proto udp
    return 0
  fi

  if command -v firewall-cmd >/dev/null 2>&1; then
    firewall-cmd --permanent --add-rich-rule="rule family=\"ipv4\" source address=\"${ALLOW_CIDR}\" port protocol=\"udp\" port=\"123\" accept"
    firewall-cmd --reload
    return 0
  fi

  echo "No supported firewall tool found. Open UDP/123 manually if needed."
}

show_summary() {
  echo
  echo "Setup complete."
  echo "App directory: ${TARGET_DIR}"
  echo "Published ntp_server: ${NTP_SERVER_NAME}"
  echo "Allowed NTP clients: ${ALLOW_CIDR}"
  echo
  echo "Recommended checks:"
  echo "  timedatectl status"
  echo "  chronyc tracking || chronyc sources"
  echo "  systemctl status chrony.service || systemctl status chronyd.service"
  echo "  journalctl -u inas-device-hub@frontend -n 100 --no-pager"
  echo "  journalctl -u inas-device-hub@backend -n 100 --no-pager"
}

install_app_service
configure_device_config_defaults
configure_chrony
configure_firewall
show_summary
