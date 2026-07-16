#!/usr/bin/env bash
set -euo pipefail

# Install and enable the inas-device-hub systemd service.
# Usage: sudo ./scripts/install_service.sh [--user USER] [--target-dir DIR] [--enable-cloudflare-tunnel|--disable-cloudflare-tunnel] [--production]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVICE_NAME="inas-device-hub"
DEFAULT_USER="inas-usr"
UNIT_TEMPLATE_SRC="$REPO_ROOT/systemd/${SERVICE_NAME}@.service"
TARGET_UNIT="/etc/systemd/system/${SERVICE_NAME}@.service"
CLOUDFLARE_TUNNEL_SERVICE_NAME="inas-cloudflare-tunnel"
CLOUDFLARE_TUNNEL_UNIT_SRC="$REPO_ROOT/systemd/${CLOUDFLARE_TUNNEL_SERVICE_NAME}.service"
CLOUDFLARE_TUNNEL_TARGET_UNIT="/etc/systemd/system/${CLOUDFLARE_TUNNEL_SERVICE_NAME}.service"

# By default use system user 'inas-usr' when not run via sudo; if the script
# is run with sudo, prefer SUDO_USER as the service run-as user.
TARGET_USER="${DEFAULT_USER}"
TARGET_USER_EXPLICIT="false"
TARGET_DIR=""
CLOUDFLARE_TUNNEL_MODE="auto"
PRODUCTION_MODE="false"

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="$2"; TARGET_USER_EXPLICIT="true"; shift 2;;
    --target-dir)
      TARGET_DIR="$2"; shift 2;;
    --enable-cloudflare-tunnel)
      CLOUDFLARE_TUNNEL_MODE="enable"; shift;;
    --disable-cloudflare-tunnel)
      CLOUDFLARE_TUNNEL_MODE="disable"; shift;;
    --production)
      PRODUCTION_MODE="true"; shift;;
    --allow-local-auth)
      echo "--allow-local-auth is no longer necessary; existing .env settings are preserved by default."; shift;;
    -h|--help)
      echo "Usage: sudo $0 [--user USER] [--target-dir DIR] [--enable-cloudflare-tunnel|--disable-cloudflare-tunnel] [--production]"; exit 0;;
    *)
      echo "Unknown option: $1"; exit 1;;
  esac
done


if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (sudo)." >&2
  exit 2
fi

for required_command in awk chown chmod curl getent grep readlink runuser systemctl; do
  if ! command -v "$required_command" >/dev/null 2>&1; then
    echo "Required deployment command is missing: $required_command" >&2
    exit 5
  fi
done

if [[ ! -f "$UNIT_TEMPLATE_SRC" ]]; then
  echo "Unit template not found: $UNIT_TEMPLATE_SRC" >&2
  exit 3
fi

# An explicit --user wins. Otherwise preserve the historical behavior of
# preferring the original sudo user when one is available.
if [[ "$TARGET_USER_EXPLICIT" == "true" ]]; then
  RUN_AS_USER="$TARGET_USER"
else
  RUN_AS_USER="${SUDO_USER:-$TARGET_USER}"
fi

# Determine home directory for RUN_AS_USER
RUN_AS_HOME="$(getent passwd "$RUN_AS_USER" | cut -d: -f6 || true)"
if [[ -z "$RUN_AS_HOME" ]]; then
  echo "Service user does not exist or has no home directory: $RUN_AS_USER" >&2
  echo "Create the user first, or pass --user with an existing account." >&2
  exit 4
fi

# Default target dir if not specified
if [[ -z "$TARGET_DIR" ]]; then
  TARGET_DIR="$RUN_AS_HOME/ina-device-hub"
fi

echo "Installing ${SERVICE_NAME}@ template; instances will run as user='${RUN_AS_USER}', dir='${TARGET_DIR}'"

render_systemd_unit() {
  local src="$1"
  local dest="$2"
  awk -v td="$TARGET_DIR" -v user="$RUN_AS_USER" '
    { gsub("@@INAS_HUB_DIR@@", td) }
    { gsub("@@INAS_HUB_USER@@", user) }
    { print }
  ' "$src" > "$dest"
}

# Create target directory and copy repository contents
echo "Creating target directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

REPO_ROOT_REAL="$(readlink -f "$REPO_ROOT")"
TARGET_DIR_REAL="$(readlink -f "$TARGET_DIR")"
if [[ "$REPO_ROOT_REAL" == "$TARGET_DIR_REAL" ]]; then
  echo "Target directory is the current repository; skipping repository copy."
else
  if ! command -v rsync >/dev/null 2>&1; then
    echo "Required deployment command is missing: rsync" >&2
    exit 5
  fi
  echo "Copying repository files to target directory"
  rsync -a --delete \
    --exclude='.git' \
    --exclude='.env*' \
    --exclude='.venv' \
    --exclude='.data' \
    --exclude='.*.json' \
    --exclude='.*.jsonl' \
    --exclude='data' \
    --exclude='logs' \
    --exclude='node_modules' \
    --exclude='admin-ui/node_modules' \
    --exclude='cloudflare/node_modules' \
    "$REPO_ROOT/" "$TARGET_DIR/"
fi

echo "Setting ownership to ${RUN_AS_USER}:${RUN_AS_USER}"
chown -R "$RUN_AS_USER":"$RUN_AS_USER" "$TARGET_DIR" || true

# Ensure start/serve script is executable if present
if [[ -f "$TARGET_DIR/serve.sh" ]]; then
  chmod +x "$TARGET_DIR/serve.sh"
fi
if [[ -f "$TARGET_DIR/start.sh" ]]; then
  chmod +x "$TARGET_DIR/start.sh"
fi

# Create a .env by copying .default.env if present, otherwise create a template
ENV_FILE="$TARGET_DIR/.env"
DEFAULT_ENV_SRC="$REPO_ROOT/.default.env"
SOURCE_ENV_FILE="$REPO_ROOT/.env"

if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists in target directory, skipping creation."
else
  if [[ "$SOURCE_ENV_FILE" != "$ENV_FILE" ]] && [[ -f "$SOURCE_ENV_FILE" ]]; then
    echo "Installing configured environment from $SOURCE_ENV_FILE"
    cp "$SOURCE_ENV_FILE" "$ENV_FILE"
  elif [[ -f "$DEFAULT_ENV_SRC" ]]; then
    echo "Copying default env from $DEFAULT_ENV_SRC to $ENV_FILE"
    cp "$DEFAULT_ENV_SRC" "$ENV_FILE"
  else
    echo "Creating .env template at $ENV_FILE"
    cat > "$ENV_FILE" <<'EOF'
# .env example - fill these values before starting the service
# TURSO
TURSO_DATABASE_URL="https://example.turso.dev"
TURSO_AUTH_TOKEN="your-turso-token"

# S3 / compatible storage
S3_ENDPOINT_URL="https://s3.example.com"
S3_BUCKET_NAME="your-bucket"
S3_BUCKET_REGION="ap-northeast-1"
S3_ACCESS_KEY="AKIA..."
S3_SECRET_KEY="...."

# MQTT
MQTT_BROKER_URL="mqtt.example.com"
MQTT_BROKER_PORT=1883
MQTT_BROKER_USERNAME="user"
MQTT_BROKER_PASSWORD="pw"

# Other
TIMELAPSE_INTERVAL=3600
SENSOR_SAVE_IMAGE=false
SENSOR_SAVE_AUDIO=false
EOF
  fi
fi
chown "$RUN_AS_USER":"$RUN_AS_USER" "$ENV_FILE"
chmod 600 "$ENV_FILE"

env_file_value() {
  local key="$1"
  awk -F= -v key="$key" '
    $1 == key {
      value = substr($0, index($0, "=") + 1)
      gsub(/^[\047"]|[\047"]$/, "", value)
      print value
      exit
    }
  ' "$ENV_FILE"
}

UV_BIN="$(command -v uv || true)"
if [[ -z "$UV_BIN" ]] && [[ -x "$RUN_AS_HOME/.local/bin/uv" ]]; then
  UV_BIN="$RUN_AS_HOME/.local/bin/uv"
fi
if [[ -z "$UV_BIN" ]]; then
  echo "uv is required. Install uv for the service user before deploying." >&2
  exit 5
fi

echo "Installing locked production dependencies"
runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" UV_CACHE_DIR="$RUN_AS_HOME/.cache/uv" "$UV_BIN" sync --frozen --no-dev --project "$TARGET_DIR"

if [[ "$PRODUCTION_MODE" == "true" ]]; then
  echo "Provisioning Cloudflare Access and Tunnel configuration"
  runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/python" "$TARGET_DIR/scripts/cloudflare_access_setup.py" --env-file "$ENV_FILE" --write-env provision
  runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/python" "$TARGET_DIR/scripts/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" --write-env provision
  chmod 600 "$ENV_FILE"
else
  echo "Upgrade mode: preserving existing .env, MQTT, HTTP, and Cloudflare settings"
fi

MQTT_HOST="$(env_file_value MQTT_BROKER_URL)"
if [[ "$MQTT_HOST" == "localhost" ]] || [[ "$MQTT_HOST" == "127.0.0.1" ]] || [[ "$MQTT_HOST" == "::1" ]]; then
  if systemctl list-unit-files mosquitto.service --no-legend 2>/dev/null | grep -q '^mosquitto.service'; then
    systemctl start mosquitto.service
  fi
fi

check_args=(check --env-file "$ENV_FILE")
if [[ "$PRODUCTION_MODE" == "true" ]]; then
  check_args+=(--production)
fi
echo "Checking Hub configuration and external connections"
runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/ina-hub" "${check_args[@]}"
if [[ "$PRODUCTION_MODE" == "true" ]]; then
  runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/python" "$TARGET_DIR/scripts/cloudflare_access_setup.py" --env-file "$ENV_FILE" audit
  runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/python" "$TARGET_DIR/scripts/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" check
fi

echo "Creating a pre-start state backup"
runuser -u "$RUN_AS_USER" -- env HOME="$RUN_AS_HOME" "$TARGET_DIR/.venv/bin/ina-hub" backup --env-file "$ENV_FILE"

# Install systemd unit (update WorkingDirectory/ExecStart if they refer to different path)

echo "Installing systemd template unit to $TARGET_UNIT"

render_systemd_unit "$UNIT_TEMPLATE_SRC" "$TARGET_UNIT"

chmod 644 "$TARGET_UNIT"
chown root:root "$TARGET_UNIT"

BACKUP_SERVICE_SRC="$REPO_ROOT/systemd/${SERVICE_NAME}-backup@.service"
BACKUP_TIMER_SRC="$REPO_ROOT/systemd/${SERVICE_NAME}-backup@.timer"
BACKUP_SERVICE_TARGET="/etc/systemd/system/${SERVICE_NAME}-backup@.service"
BACKUP_TIMER_TARGET="/etc/systemd/system/${SERVICE_NAME}-backup@.timer"
if [[ -f "$BACKUP_SERVICE_SRC" ]] && [[ -f "$BACKUP_TIMER_SRC" ]]; then
  render_systemd_unit "$BACKUP_SERVICE_SRC" "$BACKUP_SERVICE_TARGET"
  render_systemd_unit "$BACKUP_TIMER_SRC" "$BACKUP_TIMER_TARGET"
  chmod 644 "$BACKUP_SERVICE_TARGET" "$BACKUP_TIMER_TARGET"
  chown root:root "$BACKUP_SERVICE_TARGET" "$BACKUP_TIMER_TARGET"
fi

install_cloudflare_tunnel_unit=false
if [[ -f "$CLOUDFLARE_TUNNEL_UNIT_SRC" ]]; then
  echo "Installing Cloudflare Tunnel systemd unit to $CLOUDFLARE_TUNNEL_TARGET_UNIT"
  render_systemd_unit "$CLOUDFLARE_TUNNEL_UNIT_SRC" "$CLOUDFLARE_TUNNEL_TARGET_UNIT"
  chmod 644 "$CLOUDFLARE_TUNNEL_TARGET_UNIT"
  chown root:root "$CLOUDFLARE_TUNNEL_TARGET_UNIT"
  install_cloudflare_tunnel_unit=true
else
  echo "Cloudflare Tunnel unit not found, skipping: $CLOUDFLARE_TUNNEL_UNIT_SRC"
fi

echo "Reloading systemd daemon"
systemctl daemon-reload

echo "Enabling and restarting ${SERVICE_NAME}@main"
systemctl enable "${SERVICE_NAME}@main.service"
systemctl restart "${SERVICE_NAME}@main.service"
if [[ -f "$BACKUP_TIMER_TARGET" ]]; then
  systemctl enable --now "${SERVICE_NAME}-backup@main.timer"
fi

HUB_PORT="$(env_file_value HUB_HTTP_PORT)"
HUB_PORT="${HUB_PORT:-39151}"
READINESS_TIMEOUT="$(env_file_value HUB_READINESS_TIMEOUT_SECONDS)"
READINESS_TIMEOUT="${READINESS_TIMEOUT:-30}"
if ! [[ "$READINESS_TIMEOUT" =~ ^[0-9]+$ ]]; then
  echo "HUB_READINESS_TIMEOUT_SECONDS must be an integer: $READINESS_TIMEOUT" >&2
  exit 6
fi
echo "Waiting for Hub readiness"
ready="false"
for ((attempt = 0; attempt < READINESS_TIMEOUT; attempt++)); do
  if curl --fail --silent --show-error "http://127.0.0.1:${HUB_PORT}/readyz" >/dev/null; then
    ready="true"
    break
  fi
  sleep 1
done
if [[ "$ready" != "true" ]]; then
  echo "Hub did not become ready within ${READINESS_TIMEOUT}s" >&2
  systemctl status "${SERVICE_NAME}@main" --no-pager || true
  echo "The service was left running so MQTT reconnection and operator diagnosis can continue." >&2
  exit 6
fi

should_enable_cloudflare_tunnel=false
if [[ "$CLOUDFLARE_TUNNEL_MODE" == "enable" ]]; then
  should_enable_cloudflare_tunnel=true
elif [[ "$CLOUDFLARE_TUNNEL_MODE" == "auto" ]]; then
  CLOUDFLARE_TUNNEL_ID="$(env_file_value CLOUDFLARE_TUNNEL_ID)"
  CLOUDFLARE_TUNNEL_TOKEN_FILE="$(env_file_value CLOUDFLARE_TUNNEL_TOKEN_FILE)"
  if [[ -n "$CLOUDFLARE_TUNNEL_ID" ]] && [[ -n "$CLOUDFLARE_TUNNEL_TOKEN_FILE" ]]; then
    should_enable_cloudflare_tunnel=true
  fi
fi

if [[ "$install_cloudflare_tunnel_unit" == "true" ]]; then
  if [[ "$should_enable_cloudflare_tunnel" == "true" ]]; then
    echo "Enabling and starting ${CLOUDFLARE_TUNNEL_SERVICE_NAME}"
    systemctl enable --now "${CLOUDFLARE_TUNNEL_SERVICE_NAME}.service"
  else
    echo "Cloudflare Tunnel service installed but not enabled. Run this after Cloudflare provision:"
    echo "  sudo systemctl enable --now ${CLOUDFLARE_TUNNEL_SERVICE_NAME}.service"
  fi
fi

echo "Installation complete. Service statuses:"
systemctl status "${SERVICE_NAME}@main" --no-pager || true
if [[ "$install_cloudflare_tunnel_unit" == "true" ]] && [[ "$should_enable_cloudflare_tunnel" == "true" ]]; then
  systemctl status "${CLOUDFLARE_TUNNEL_SERVICE_NAME}" --no-pager || true
fi

echo "If the service failed to start, check logs with: journalctl -u ${SERVICE_NAME}@main -f"
echo "If the Cloudflare Tunnel service failed to start, check logs with: journalctl -u ${CLOUDFLARE_TUNNEL_SERVICE_NAME} -f"

exit 0
