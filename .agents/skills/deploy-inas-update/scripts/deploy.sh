#!/usr/bin/env bash
set -Eeuo pipefail

REMOTE="${INAS_DEPLOY_REMOTE:-origin}"
BRANCH="${INAS_DEPLOY_BRANCH:-main}"
PREFLIGHT_ONLY=false
FORCE_DEPLOY=false
POST_INSTALL_READY_TIMEOUT="${INAS_DEPLOY_READINESS_SECONDS:-120}"

usage() {
  cat <<'EOF'
Usage: deploy.sh [--preflight] [--force]

Fetch, test, and deploy the latest INA Hub origin/main revision.

  --preflight  Validate prerequisites without changing or deploying anything.
  --force      Redeploy even when the remote branch has no new commit.
EOF
}

log() {
  printf '[deploy-inas-update] %s\n' "$*"
}

fail() {
  printf '[deploy-inas-update] ERROR: %s\n' "$*" >&2
  exit 1
}

while (($#)); do
  case "$1" in
    --preflight)
      PREFLIGHT_ONLY=true
      ;;
    --force)
      FORCE_DEPLOY=true
      ;;
    -h | --help)
      usage
      exit 0
      ;;
    *)
      usage >&2
      fail "unknown argument: $1"
      ;;
  esac
  shift
done

if ((EUID == 0)); then
  fail "run this command as the repository owner; the script invokes sudo only for installation"
fi

for command_name in bash curl flock git sudo systemctl; do
  command -v "$command_name" >/dev/null 2>&1 || fail "required command is missing: $command_name"
done

SCRIPT_DIR="$(cd -- "$(dirname -- "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(git -C "$SCRIPT_DIR" rev-parse --show-toplevel 2>/dev/null)" || fail "the skill is not inside a Git repository"
HUB_DIR="$REPO_ROOT/hub"
INSTALLER="$HUB_DIR/scripts/install_service.sh"

[[ -d "$HUB_DIR/src/ina_device_hub" ]] || fail "Hub source directory not found: $HUB_DIR"
[[ -f "$INSTALLER" ]] || fail "Hub installer not found: $INSTALLER"
[[ -f "$HUB_DIR/uv.lock" ]] || fail "locked Hub dependency file not found: $HUB_DIR/uv.lock"
git -C "$REPO_ROOT" remote get-url "$REMOTE" >/dev/null 2>&1 || fail "Git remote not found: $REMOTE"

current_branch="$(git -C "$REPO_ROOT" branch --show-current)"
[[ "$current_branch" == "$BRANCH" ]] || fail "expected branch '$BRANCH', found '${current_branch:-detached HEAD}'"

find_uv() {
  local candidate
  if command -v uv >/dev/null 2>&1; then
    command -v uv
    return
  fi
  for candidate in "$HOME/.local/bin/uv" "$HOME"/.rye/uv/*/uv; do
    if [[ -x "$candidate" ]]; then
      printf '%s\n' "$candidate"
      return
    fi
  done
  return 1
}

UV_BIN="$(find_uv)" || fail "uv was not found in PATH, ~/.local/bin, or ~/.rye/uv"
UV_DIR="$(dirname -- "$UV_BIN")"
SUDO_PATH="$UV_DIR:/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin"

[[ "$POST_INSTALL_READY_TIMEOUT" =~ ^[0-9]+$ ]] || fail "INAS_DEPLOY_READINESS_SECONDS must be a non-negative integer"

lock_key="$(printf '%s' "$REPO_ROOT" | cksum | awk '{print $1}')"
LOCK_FILE="${TMPDIR:-/tmp}/deploy-inas-update-${UID}-${lock_key}.lock"
exec 9>"$LOCK_FILE"
flock -n 9 || fail "another INA deployment is already running"

initial_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
log "repository: $REPO_ROOT"
log "hub: $HUB_DIR"
log "branch: $current_branch"
log "current revision: $initial_revision"
log "uv: $UV_BIN"

if [[ "$PREFLIGHT_ONLY" == "true" ]]; then
  log "preflight passed; no repository or service changes were made"
  exit 0
fi

log "fetching $REMOTE/$BRANCH"
git -C "$REPO_ROOT" fetch --prune "$REMOTE" "$BRANCH"
remote_ref="$REMOTE/$BRANCH"
remote_revision="$(git -C "$REPO_ROOT" rev-parse "$remote_ref")"
read -r local_only remote_only < <(git -C "$REPO_ROOT" rev-list --left-right --count "HEAD...$remote_ref")

if ((local_only > 0)); then
  fail "local branch contains $local_only commit(s) not present on $remote_ref; publish or reconcile them before deployment"
fi

if ((remote_only == 0)) && [[ "$FORCE_DEPLOY" != "true" ]]; then
  log "already at $remote_revision; no deployment needed (use --force to redeploy)"
  exit 0
fi

stash_created=false
stash_restored=false

restore_tracked_changes() {
  if [[ "$stash_created" != "true" || "$stash_restored" == "true" ]]; then
    return 0
  fi
  log "restoring pre-existing tracked workspace changes"
  if git -C "$REPO_ROOT" stash pop --index; then
    stash_restored=true
    return 0
  fi
  printf '%s\n' \
    '[deploy-inas-update] ERROR: tracked changes could not be restored cleanly.' \
    '[deploy-inas-update] The stash was preserved. Resolve the conflict before deploying.' >&2
  return 1
}

cleanup() {
  local exit_code=$?
  trap - EXIT INT TERM
  if [[ "$stash_created" == "true" && "$stash_restored" != "true" ]]; then
    restore_tracked_changes || exit_code=1
  fi
  exit "$exit_code"
}
trap cleanup EXIT INT TERM

if ! git -C "$REPO_ROOT" diff --quiet || ! git -C "$REPO_ROOT" diff --cached --quiet; then
  log "temporarily preserving tracked workspace changes; untracked runtime files remain in place"
  git -C "$REPO_ROOT" stash push -m "deploy-inas-update-before-${remote_revision:0:12}"
  stash_created=true
fi

log "fast-forwarding to $remote_revision"
git -C "$REPO_ROOT" merge --ff-only "$remote_ref"
restore_tracked_changes

deployed_revision="$(git -C "$REPO_ROOT" rev-parse HEAD)"
[[ "$deployed_revision" == "$remote_revision" ]] || fail "HEAD does not match the fetched remote revision"
git -C "$REPO_ROOT" diff --check

log "synchronizing locked development dependencies"
"$UV_BIN" sync --frozen --project "$HUB_DIR"

log "running the complete Hub unittest suite"
(
  cd "$HUB_DIR"
  PYTHON_DOTENV_DISABLED=1 .venv/bin/python -m unittest discover -s tests
)

log "deploying in normal upgrade mode; existing environment and external settings are preserved"
installer_exit=0
sudo env "PATH=$SUDO_PATH" bash "$INSTALLER" --target-dir "$HUB_DIR" || installer_exit=$?
if ((installer_exit != 0 && installer_exit != 6)); then
  fail "Hub installer failed with exit code $installer_exit"
fi
if ((installer_exit == 6)); then
  log "installer readiness window elapsed; continuing bounded post-install verification"
fi

hub_port="$(awk -F= '$1 == "HUB_HTTP_PORT" { value = substr($0, index($0, "=") + 1); gsub(/^[\047\"]|[\047\"]$/, "", value); print value; exit }' "$HUB_DIR/.env")"
hub_port="${hub_port:-39151}"

log "verifying service and health endpoints"
[[ "$(systemctl is-active inas-device-hub@main.service)" == "active" ]] || fail "Hub systemd service is not active"
health_result=""
ready_result=""
for ((attempt = 0; attempt <= POST_INSTALL_READY_TIMEOUT; attempt++)); do
  health_result="$(curl --fail --silent "http://127.0.0.1:${hub_port}/healthz" 2>/dev/null || true)"
  ready_result="$(curl --fail --silent "http://127.0.0.1:${hub_port}/readyz" 2>/dev/null || true)"
  if [[ -n "$health_result" && -n "$ready_result" ]]; then
    break
  fi
  if ((attempt < POST_INSTALL_READY_TIMEOUT)); then
    sleep 1
  fi
done
[[ -n "$health_result" ]] || fail "Hub health check did not pass within ${POST_INSTALL_READY_TIMEOUT}s after installation"
[[ -n "$ready_result" ]] || fail "Hub readiness check did not pass within ${POST_INSTALL_READY_TIMEOUT}s after installation"

trap - EXIT INT TERM
log "deployment complete"
log "previous revision: $initial_revision"
log "deployed revision: $deployed_revision"
log "healthz: $health_result"
log "readyz: $ready_result"
