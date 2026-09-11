#!/usr/bin/bash
set -euo pipefail
export PATH="/usr/bin:/bin"

workspace_id="${1:-}"
destination="${2:-}"
helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"

if [[ -z "$workspace_id" || -z "$destination" ]]; then
  echo "usage: $0 <workspace-id> <destination>" >&2
  exit 2
fi

exec /usr/bin/python3 "$helper" capture "$workspace_id" "$destination"
