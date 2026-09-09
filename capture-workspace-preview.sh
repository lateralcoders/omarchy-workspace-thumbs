#!/usr/bin/env bash
set -euo pipefail

workspace_id="${1:-}"
destination="${2:-}"

if [[ -z "$workspace_id" || -z "$destination" ]]; then
  echo "usage: $0 <workspace-id> <destination>" >&2
  exit 2
fi

mkdir -p -m 700 "$(dirname "$destination")"

monitor_name="$(hyprctl -j monitors | jq -r '.[] | select(.focused == true) | .name' | head -n1)"
if [[ -z "$monitor_name" || "$monitor_name" == "null" ]]; then
  exit 1
fi

tmp_file="$(dirname "$destination")/.tmp-ws-${workspace_id}.$$.jpg"
trap 'rm -f "$tmp_file"' EXIT

# Scale ~1/5 of the monitor: enough for the hover card, cheap for bar thumbs.
timeout 2s grim -t jpeg -q 45 -s 0.2 -o "$monitor_name" "$tmp_file"
mv -f "$tmp_file" "$destination"
trap - EXIT
