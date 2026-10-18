#!/usr/bin/env bash
# Double-click in Finder, or pass the same options as start.sh in Terminal.
set -euo pipefail
script_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
exec bash "$script_dir/start.sh" "$@"
