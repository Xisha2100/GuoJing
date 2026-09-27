#!/usr/bin/env bash
set -euo pipefail
previous=$(readlink -f /opt/guojing/previous)
[[ -n $previous && -d $previous ]]
exec "$(dirname "$0")/release.sh" "$previous" --rollback
