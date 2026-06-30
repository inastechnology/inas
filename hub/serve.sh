#!/usr/bin/env bash
set -euo pipefail

# load rye env
if [[ -f "$HOME/.rye/env" ]]; then
  # shellcheck disable=SC1090
  source "$HOME/.rye/env"
fi

# start rye server
exec rye run serve
