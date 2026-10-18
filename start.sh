#!/usr/bin/env bash
# Linux and macOS (including the system Bash 3.2).
set -euo pipefail

project_dir="$(cd "$(dirname "${BASH_SOURCE[0]}")" && pwd -P)"
port=8189
selected_data_dir="${PICTIDE_DATA_DIR:-${PICTIDE_WEB_DATA_DIR:-"$project_dir/data"}}"
listen_address=127.0.0.1

usage() {
  cat <<'HELP'
Usage: ./start.sh [--port PORT] [--data-dir PATH] [--lan]

  --port PORT      HTTP port (default: 8189)
  --data-dir PATH  Data directory (default: PICTIDE_DATA_DIR or ./data)
  --lan            Allow local-network access (listen on 0.0.0.0)
  -h, --help       Show this help

Requires Python 3.10+ and a built web/dist directory.
Set PICTIDE_PYTHON to select a Python interpreter.
HELP
}
fail() { printf 'Pictide: %s\n' "$*" >&2; exit 1; }

while (($#)); do
  case "$1" in
    --port)
      [[ $# -ge 2 && -n "$2" ]] || fail '--port requires a value.'
      port="$2"; shift 2 ;;
    --data-dir)
      [[ $# -ge 2 && -n "$2" ]] || fail '--data-dir requires a value.'
      selected_data_dir="$2"; shift 2 ;;
    --lan) listen_address=0.0.0.0; shift ;;
    -h|--help) usage; exit 0 ;;
    *) fail "Unknown argument: $1. Use --help." ;;
  esac
done
[[ "$port" =~ ^[0-9]{1,5}$ ]] || fail 'Port must be an integer from 1 to 65535.'
port=$((10#$port))
((port >= 1 && port <= 65535)) || fail 'Port must be an integer from 1 to 65535.'
[[ -f "$project_dir/web/dist/index.html" ]] || fail 'Frontend build missing. Follow docs/development.md to install frontend dependencies and build once.'

mkdir -p "$selected_data_dir"
data_root="$(cd "$selected_data_dir" && pwd -P)"
runtime_path="$data_root/runtime"
cache_path="$data_root/cache"
temp_path="$data_root/tmp"
mkdir -p "$runtime_path" "$cache_path/python" "$cache_path/pip" "$temp_path"
export PICTIDE_DATA_DIR="$data_root" PICTIDE_WEB_DATA_DIR="$data_root"
export PYTHONPYCACHEPREFIX="$cache_path/python" PIP_CACHE_DIR="$cache_path/pip"
export TMPDIR="$temp_path" TEMP="$temp_path" TMP="$temp_path"
venv_path="$runtime_path/venv"
venv_python="$venv_path/bin/python"

check_python() {
  "$1" -c 'import sys; sys.exit(0 if sys.version_info >= (3,10) else 1)'
}
if [[ ! -x "$venv_python" ]]; then
  python_path="${PICTIDE_PYTHON:-${PICTIDE_WEB_PYTHON:-}}"
  if [[ -z "$python_path" ]]; then
    python_path="$(command -v python3 || command -v python || true)"
  fi
  [[ -n "$python_path" ]] && command -v "$python_path" >/dev/null 2>&1 || fail 'Python 3.10+ is required. Set PICTIDE_PYTHON to its executable.'
  check_python "$python_path" || fail 'Python 3.10+ is required. Select it with PICTIDE_PYTHON.'
  "$python_path" -m venv "$venv_path" || fail 'Failed to create the virtual environment. On Debian/Ubuntu, install the matching python3-venv package.'
fi
check_python "$venv_python" || fail 'The virtual environment requires Python 3.10+.'
if ! "$venv_python" -c "import importlib.util,sys; sys.exit(0 if all(importlib.util.find_spec(name) for name in ('aiohttp', 'fastembed', 'numpy')) and __import__('importlib.metadata', fromlist=['version']).version('fastembed') == '0.9.0' and __import__('importlib.metadata', fromlist=['version']).version('numpy') == ('2.5.4' if sys.version_info >= (3,12) else '2.2.6') else 1)"; then
  "$venv_python" -m pip install -r "$project_dir/backend/requirements.txt" || fail 'Dependency installation failed.'
fi

printf 'Pictide: http://127.0.0.1:%s\n' "$port"
if [[ "$listen_address" == 0.0.0.0 ]]; then
  printf 'LAN access: http://<computer-lan-ip>:%s\n' "$port"
fi
printf 'Data directory: %s\nPress Ctrl+C to stop the Web application.\n' "$data_root"
cd "$project_dir"
exec "$venv_python" -m backend.host --host "$listen_address" --port "$port" --data-dir "$data_root"
