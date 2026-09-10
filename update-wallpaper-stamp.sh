#!/usr/bin/env bash
set -euo pipefail

# Resolve the live wallpaper and write it only when it changes so QML FileView
# (which does not see symlink retargets) can reload empty workspace chips.
link="${HOME}/.local/state/omarchy/current/background"
stamp_dir="${HOME}/.cache/omarchy/workspace-previews"
stamp="${stamp_dir}/wallpaper.path"

mkdir -p -m 700 "$stamp_dir"

path="$(readlink -f "$link" 2>/dev/null || true)"
[[ -n $path && -e $path ]] || exit 0

current=""
[[ -f $stamp ]] && current="$(cat "$stamp" 2>/dev/null || true)"
[[ $path == "$current" ]] && exit 0

tmp="${stamp}.tmp.$$"
printf '%s\n' "$path" >"$tmp"
mv -f "$tmp" "$stamp"
