#!/usr/bin/env bash
set -euo pipefail

helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"
link="${HOME}/.local/state/omarchy/current/background"
stamp_dir="${HOME}/.cache/omarchy/workspace-previews"
stamp="${stamp_dir}/wallpaper.path"

python3 "$helper" prepare-dir "$stamp_dir"

path="$(readlink -f "$link" 2>/dev/null || true)"
[[ -n $path && -e $path ]] || exit 0

current=""
if [[ -f $stamp ]]; then
  current="$(python3 "$helper" run 500 4096 -- cat "$stamp" 2>/dev/null || true)"
fi
current="${current%$'\n'}"
[[ $path == "$current" ]] && exit 0

printf '%s\n' "$path" | python3 "$helper" publish "$stamp"
