#!/usr/bin/env bash
set -euo pipefail
release=/opt/guojing/current
exec runuser -u guojing -- "$release/.venv/bin/python" "$release/deploy/with-env.py" "$release/.venv/bin/guojing-admin" "$@"
