#!/usr/bin/env bash
set -euo pipefail

# Install and enable the inas-device-hub systemd service.
# Usage: sudo ./scripts/install_service.sh [--user USER] [--target-dir DIR]

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

SERVICE_NAME="inas-device-hub"
DEFAULT_USER="inas-usr"
UNIT_TEMPLATE_SRC="$REPO_ROOT/systemd/${SERVICE_NAME}@.service"
TARGET_UNIT="/etc/systemd/system/${SERVICE_NAME}@.service"

# By default use system user 'inas-usr' when not run via sudo; if the script
# is run with sudo, prefer SUDO_USER as the service run-as user.
TARGET_USER="${DEFAULT_USER}"
TARGET_DIR=""

while [[ $# -gt 0 ]]; do
  case "$1" in
    --user)
      TARGET_USER="$2"; shift 2;;
    --target-dir)
      TARGET_DIR="$2"; shift 2;;
    -h|--help)
      echo "Usage: sudo $0 [--user USER] [--target-dir DIR]"; exit 0;;
    *)
      echo "Unknown option: $1"; exit 1;;
  esac
done


if [[ $(id -u) -ne 0 ]]; then
  echo "This script must be run as root (sudo)." >&2
  exit 2
fi

if [[ ! -f "$UNIT_TEMPLATE_SRC" ]]; then
  echo "Unit template not found: $UNIT_TEMPLATE_SRC" >&2
  exit 3
fi

# Determine the user to run the service as. Prefer the original sudo user
# (SUDO_USER) when available; otherwise use provided TARGET_USER.
RUN_AS_USER="${SUDO_USER:-}" 
if [[ -z "$RUN_AS_USER" ]]; then
  RUN_AS_USER="$TARGET_USER"
fi

# Determine home directory for RUN_AS_USER
RUN_AS_HOME="$(getent passwd "$RUN_AS_USER" | cut -d: -f6 || true)"
if [[ -z "$RUN_AS_HOME" ]]; then
  RUN_AS_HOME="/home/$RUN_AS_USER"
fi

# Default target dir if not specified
if [[ -z "$TARGET_DIR" ]]; then
  TARGET_DIR="$RUN_AS_HOME/ina-device-hub"
fi

echo "Installing ${SERVICE_NAME}@ template; instances will run as user='${RUN_AS_USER}', dir='${TARGET_DIR}'"

# Create target directory and copy repository contents
echo "Creating target directory: $TARGET_DIR"
mkdir -p "$TARGET_DIR"

echo "Copying repository files to target directory (excludes .git)"
rsync -a --delete --exclude='.git' "$REPO_ROOT/" "$TARGET_DIR/"

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

if [[ -f "$ENV_FILE" ]]; then
  echo ".env already exists in target directory, skipping creation."
else
  if [[ -f "$DEFAULT_ENV_SRC" ]]; then
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
  chown "$RUN_AS_USER":"$RUN_AS_USER" "$ENV_FILE" || true
  chmod 600 "$ENV_FILE" || true
fi

# Install systemd unit (update WorkingDirectory/ExecStart if they refer to different path)

echo "Installing systemd template unit to $TARGET_UNIT"

# Read source unit template and replace occurrences of /home/pi/... and User=pi
awk -v td="$TARGET_DIR" -v user="$RUN_AS_USER" '
  { gsub("/home/pi", td) }
  { gsub("User=pi", "User=" user) }
  { print }
' "$UNIT_TEMPLATE_SRC" > "$TARGET_UNIT"

chmod 644 "$TARGET_UNIT"
chown root:root "$TARGET_UNIT"

echo "Reloading systemd daemon"
systemctl daemon-reload

echo "Enabling and starting ${SERVICE_NAME}@main"
systemctl enable --now "${SERVICE_NAME}@main.service"

echo "Installation complete. Service statuses:"
systemctl status "${SERVICE_NAME}@main" --no-pager || true

echo "If the service failed to start, check logs with: journalctl -u ${SERVICE_NAME}@main -f"

exit 0
