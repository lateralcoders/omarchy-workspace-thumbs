#!/usr/bin/bash
set -euo pipefail

helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"
exec /usr/bin/env -i \
  PATH="/usr/bin:/bin" \
  HOME="${HOME}" \
  XDG_RUNTIME_DIR="${XDG_RUNTIME_DIR-}" \
  WAYLAND_DISPLAY="${WAYLAND_DISPLAY-}" \
  HYPRLAND_INSTANCE_SIGNATURE="${HYPRLAND_INSTANCE_SIGNATURE-}" \
  XDG_SESSION_TYPE="${XDG_SESSION_TYPE-}" \
  /usr/bin/python3 -I "$helper" stamp-wallpaper
