#!/usr/bin/env bash
set -euo pipefail

SCRIPT_DIR="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd)"
REPO_ROOT="$(cd "$SCRIPT_DIR/.." && pwd)"

REPO_LOCAL_FILES=(
  ".env"
  ".camera_device_list.json"
  ".device_configs.json"
  ".device_list.json"
  ".location_list.json"
  "data"
  "logs"
)

COMMAND="${1:-}"
shift || true

SOURCE_DIR="$REPO_ROOT"
TARGET_DIR="$REPO_ROOT"
WORK_DIR="${WORK_DIR:-$HOME/.ina-device-hub}"
SOURCE_WORK_DIR="$WORK_DIR"
TARGET_WORK_DIR="$WORK_DIR"
INCLUDE_WORK_DIR=false
DRY_RUN=false
OVERWRITE=false

usage() {
  cat <<EOF
Usage:
  $0 list [--source-dir DIR] [--work-dir DIR] [--include-work-dir]
  $0 export ARCHIVE_DIR [--source-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]
  $0 export-zip ZIP_PATH [--source-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]
  $0 import ARCHIVE_DIR [--target-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]
  $0 import-zip ZIP_PATH [--target-dir DIR] [--work-dir DIR] [--include-work-dir] [--dry-run] [--overwrite]
  $0 move-device [--source-dir DIR] [--target-dir DIR] [--source-work-dir DIR] [--target-work-dir DIR] [--dry-run] [--overwrite] [--no-work-dir]

Commands:
  list        Show local files that would be migrated
  export      Copy local files from this repository into ARCHIVE_DIR
  export-zip  Copy local files into a portable zip archive
  import      Copy local files from ARCHIVE_DIR into this repository
  import-zip  Restore local files from a zip archive
  move-device Copy local files directly from one device checkout to another

Options:
  --source-dir DIR       Repository directory to export from
  --target-dir DIR       Repository directory to import into
  --work-dir DIR         Runtime WORK_DIR path; default: \$WORK_DIR or ~/.ina-device-hub
  --source-work-dir DIR  Runtime WORK_DIR path on the source device
  --target-work-dir DIR  Runtime WORK_DIR path on the target device
  --include-work-dir     Also copy the runtime WORK_DIR into archive/work_dir
  --no-work-dir          For move-device, skip copying runtime WORK_DIR
  --dry-run              Print actions without copying
  --overwrite            Replace existing files at the destination
EOF
}

fail() {
  echo "Error: $*" >&2
  exit 2
}

require_arg() {
  local name="$1"
  local value="${2:-}"
  [[ -n "$value" ]] || fail "$name requires a value"
}

require_command() {
  local command_name="$1"
  command -v "$command_name" >/dev/null 2>&1 || fail "missing required command: $command_name"
}

resolve_path() {
  local path="$1"
  if [[ "$path" = /* ]]; then
    printf "%s\n" "$path"
  else
    printf "%s\n" "$(pwd)/$path"
  fi
}

copy_item() {
  local src="$1"
  local dst="$2"

  if [[ ! -e "$src" ]]; then
    echo "skip missing: $src"
    return
  fi

  if [[ -e "$dst" && "$OVERWRITE" != true ]]; then
    echo "skip existing: $dst"
    return
  fi

  echo "copy: $src -> $dst"
  if [[ "$DRY_RUN" == true ]]; then
    return
  fi

  mkdir -p "$(dirname "$dst")"
  if [[ -e "$dst" && "$OVERWRITE" == true ]]; then
    rm -rf "$dst"
  fi
  cp -a "$src" "$dst"
}

print_list() {
  local base_dir="$1"
  local work_dir="$2"
  local path

  echo "Repository local files:"
  for path in "${REPO_LOCAL_FILES[@]}"; do
    if [[ -e "$base_dir/$path" ]]; then
      echo "  $base_dir/$path"
    fi
  done

  if [[ "$INCLUDE_WORK_DIR" == true ]]; then
    echo "Runtime work directory:"
    if [[ -e "$work_dir" ]]; then
      echo "  $work_dir"
    else
      echo "  missing: $work_dir"
    fi
  fi
}

export_to_dir() {
  local archive_dir="$1"
  local path

  echo "Exporting local files to: $archive_dir"
  for path in "${REPO_LOCAL_FILES[@]}"; do
    copy_item "$SOURCE_DIR/$path" "$archive_dir/repo/$path"
  done
  if [[ "$INCLUDE_WORK_DIR" == true ]]; then
    copy_item "$WORK_DIR" "$archive_dir/work_dir"
  fi
}

import_from_dir() {
  local archive_dir="$1"
  local path

  echo "Importing local files from: $archive_dir"
  for path in "${REPO_LOCAL_FILES[@]}"; do
    copy_item "$archive_dir/repo/$path" "$TARGET_DIR/$path"
  done
  if [[ "$INCLUDE_WORK_DIR" == true ]]; then
    copy_item "$archive_dir/work_dir" "$WORK_DIR"
  fi
}

parse_common_options() {
  while [[ $# -gt 0 ]]; do
    case "$1" in
      --source-dir)
        require_arg "$1" "${2:-}"
        SOURCE_DIR="$(resolve_path "$2")"
        shift 2
        ;;
      --target-dir)
        require_arg "$1" "${2:-}"
        TARGET_DIR="$(resolve_path "$2")"
        shift 2
        ;;
      --work-dir)
        require_arg "$1" "${2:-}"
        WORK_DIR="$(resolve_path "$2")"
        SOURCE_WORK_DIR="$WORK_DIR"
        TARGET_WORK_DIR="$WORK_DIR"
        shift 2
        ;;
      --source-work-dir)
        require_arg "$1" "${2:-}"
        SOURCE_WORK_DIR="$(resolve_path "$2")"
        INCLUDE_WORK_DIR=true
        shift 2
        ;;
      --target-work-dir)
        require_arg "$1" "${2:-}"
        TARGET_WORK_DIR="$(resolve_path "$2")"
        INCLUDE_WORK_DIR=true
        shift 2
        ;;
      --include-work-dir)
        INCLUDE_WORK_DIR=true
        shift
        ;;
      --no-work-dir)
        INCLUDE_WORK_DIR=false
        shift
        ;;
      --dry-run)
        DRY_RUN=true
        shift
        ;;
      --overwrite)
        OVERWRITE=true
        shift
        ;;
      -h|--help)
        usage
        exit 0
        ;;
      *)
        fail "unknown option: $1"
        ;;
    esac
  done
}

case "$COMMAND" in
  list)
    parse_common_options "$@"
    print_list "$SOURCE_DIR" "$SOURCE_WORK_DIR"
    ;;
  export)
    ARCHIVE_DIR="${1:-}"
    require_arg "ARCHIVE_DIR" "$ARCHIVE_DIR"
    shift
    ARCHIVE_DIR="$(resolve_path "$ARCHIVE_DIR")"
    parse_common_options "$@"

    WORK_DIR="$SOURCE_WORK_DIR"
    export_to_dir "$ARCHIVE_DIR"
    ;;
  export-zip)
    ZIP_PATH="${1:-}"
    require_arg "ZIP_PATH" "$ZIP_PATH"
    shift
    ZIP_PATH="$(resolve_path "$ZIP_PATH")"
    parse_common_options "$@"

    if [[ -e "$ZIP_PATH" && "$OVERWRITE" != true ]]; then
      fail "zip already exists: $ZIP_PATH (use --overwrite to replace it)"
    fi

    echo "Exporting local files to zip: $ZIP_PATH"
    if [[ "$DRY_RUN" == true ]]; then
      WORK_DIR="$SOURCE_WORK_DIR"
      export_to_dir "$(dirname "$ZIP_PATH")/$(basename "$ZIP_PATH" .zip)"
      echo "zip: $(dirname "$ZIP_PATH")/$(basename "$ZIP_PATH" .zip) -> $ZIP_PATH"
      exit 0
    fi

    require_command zip
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    WORK_DIR="$SOURCE_WORK_DIR"
    export_to_dir "$TMP_DIR/archive"
    mkdir -p "$(dirname "$ZIP_PATH")"
    if [[ -e "$ZIP_PATH" && "$OVERWRITE" == true ]]; then
      rm -f "$ZIP_PATH"
    fi
    (cd "$TMP_DIR/archive" && zip -qr "$ZIP_PATH" .)
    ;;
  import)
    ARCHIVE_DIR="${1:-}"
    require_arg "ARCHIVE_DIR" "$ARCHIVE_DIR"
    shift
    ARCHIVE_DIR="$(resolve_path "$ARCHIVE_DIR")"
    parse_common_options "$@"

    WORK_DIR="$TARGET_WORK_DIR"
    import_from_dir "$ARCHIVE_DIR"
    ;;
  import-zip)
    ZIP_PATH="${1:-}"
    require_arg "ZIP_PATH" "$ZIP_PATH"
    shift
    ZIP_PATH="$(resolve_path "$ZIP_PATH")"
    parse_common_options "$@"

    [[ -f "$ZIP_PATH" ]] || fail "zip not found: $ZIP_PATH"
    echo "Importing local files from zip: $ZIP_PATH"
    if [[ "$DRY_RUN" == true ]]; then
      require_command unzip
      unzip -Z1 "$ZIP_PATH" | sed 's/^/zip entry: /'
      echo "dry-run import target: $TARGET_DIR"
      if [[ "$INCLUDE_WORK_DIR" == true ]]; then
        echo "dry-run work dir target: $TARGET_WORK_DIR"
      fi
      exit 0
    fi

    require_command unzip
    TMP_DIR="$(mktemp -d)"
    trap 'rm -rf "$TMP_DIR"' EXIT
    unzip -q "$ZIP_PATH" -d "$TMP_DIR/archive"
    WORK_DIR="$TARGET_WORK_DIR"
    import_from_dir "$TMP_DIR/archive"
    ;;
  move-device)
    INCLUDE_WORK_DIR=true
    parse_common_options "$@"

    echo "Moving local files directly:"
    echo "  source repo: $SOURCE_DIR"
    echo "  target repo: $TARGET_DIR"
    if [[ "$INCLUDE_WORK_DIR" == true ]]; then
      echo "  source work dir: $SOURCE_WORK_DIR"
      echo "  target work dir: $TARGET_WORK_DIR"
    else
      echo "  runtime work dir: skipped"
    fi

    for path in "${REPO_LOCAL_FILES[@]}"; do
      copy_item "$SOURCE_DIR/$path" "$TARGET_DIR/$path"
    done
    if [[ "$INCLUDE_WORK_DIR" == true ]]; then
      copy_item "$SOURCE_WORK_DIR" "$TARGET_WORK_DIR"
    fi
    ;;
  -h|--help|"")
    usage
    ;;
  *)
    fail "unknown command: $COMMAND"
    ;;
esac
