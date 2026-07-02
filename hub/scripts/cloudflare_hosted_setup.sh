#!/usr/bin/env bash
set -euo pipefail

# One-command Cloudflare hosted setup:
# - provision Cloudflare Access application/group/policy
# - provision Cloudflare Tunnel, remote ingress config, tunnel token, and DNS

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

ENV_FILE="$REPO_ROOT/.env"
INSTALL_CLOUDFLARED="false"
START_TUNNEL="false"

usage() {
  cat <<EOF
Usage: $0 [options]

Options:
  --env-file FILE          .env path. Default: ${ENV_FILE}
  --install-cloudflared    Download cloudflared into hub/.data/bin if missing
  --start-tunnel           Start the tunnel after provisioning
  -h, --help               Show this help
EOF
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
    --start-tunnel)
      START_TUNNEL="true"
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
LOCK_DIR="$LOCK_ROOT/setup.lock"
mkdir -p "$LOCK_ROOT"
if ! mkdir "$LOCK_DIR" 2>/dev/null; then
  echo "Cloudflare hosted setup is already running. Lock: $LOCK_DIR" >&2
  exit 1
fi
echo "$$" > "$LOCK_DIR/pid"
cleanup_lock() {
  rm -rf "$LOCK_DIR"
}
trap cleanup_lock EXIT INT TERM

python3 "$SCRIPT_DIR/cloudflare_access_setup.py" --env-file "$ENV_FILE" check
python3 "$SCRIPT_DIR/cloudflare_access_setup.py" --env-file "$ENV_FILE" --write-env provision

python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" check
python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" --write-env provision

if [[ "$INSTALL_CLOUDFLARED" == "true" ]]; then
  python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" install-cloudflared >/dev/null
fi

if [[ "$START_TUNNEL" == "true" ]]; then
  extra=()
  if [[ "$INSTALL_CLOUDFLARED" == "true" ]]; then
    extra+=(--install-cloudflared)
  fi
  cleanup_lock
  trap - EXIT INT TERM
  exec python3 "$SCRIPT_DIR/cloudflare_tunnel_setup.py" --env-file "$ENV_FILE" start "${extra[@]}"
fi

echo "Cloudflare hosted setup complete."
echo "For systemd-managed tunnel startup, install services with:"
echo "  sudo scripts/install_service.sh --target-dir \"$REPO_ROOT\" --enable-cloudflare-tunnel"
echo "For foreground tunnel startup, run:"
echo "  bash scripts/cloudflare_tunnel_start.sh"
