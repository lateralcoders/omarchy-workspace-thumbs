#!/usr/bin/bash
set -euo pipefail

workspace_id="${1:-}"
destination="${2:-}"
helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"

if [[ -z "$workspace_id" || -z "$destination" ]]; then
  echo "usage: $0 <workspace-id> <destination>" >&2
  exit 2
fi

exec /usr/bin/env -i \
  PATH="/usr/bin:/bin" \
  HOME="${HOME}" \
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR-}" \
  WAYLAND_DISPLAY="${WAYLAND_DISPLAY-}" \
  HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE-}" \
  XDG_SESSION_TYPE="${XDG_SESSION_TYPE-}" \
  /usr/bin/python3 -I "$helper" capture "$workspace_id" "$destination"
