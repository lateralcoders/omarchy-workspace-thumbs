#!/usr/bin/bash
set -euo pipefail
export PATH="/usr/bin:/bin"

helper="$(cd "$(dirname "$0")" && pwd)/preview-helper.py"
exec /usr/bin/python3 "$helper" stamp-wallpaper
