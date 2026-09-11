#!/usr/bin/env bash
set -euo pipefail

workspace_id="${1:-}"
destination="${2:-}"
helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"

if [[ -z "$workspace_id" || -z "$destination" ]]; then
  echo "usage: $0 <workspace-id> <destination>" >&2
  exit 2
fi

cache_dir="$(dirname "$destination")"
python3 "$helper" prepare-dir "$cache_dir"

monitor_json="$(python3 "$helper" run 1000 65536 -- hyprctl -j monitors)"
monitor_name="$(
  printf '%s' "$monitor_json" | jq -r '.[] | select(.focused == true) | .name' | head -n1
)"
if [[ -z "$monitor_name" || "$monitor_name" == "null" ]]; then
  exit 1
fi

tmp="$(python3 "$helper" stage "$cache_dir")"
tmp="${tmp%$'\n'}"
cleanup() { python3 "$helper" discard "$tmp" >/dev/null 2>&1 || true; }
trap cleanup EXIT

timeout 2s grim -t jpeg -q 45 -s 0.2 -o "$monitor_name" "$tmp"
python3 "$helper" commit --jpeg "$tmp" "$destination"
trap - EXIT
