#!/usr/bin/env bash
# Input: unpacked release tree under /opt/guojing/releases/<id>, owned by root.
set -euo pipefail
[[ $EUID -eq 0 ]]
exec 9>/run/lock/guojing-release.lock
flock -n 9
release=$(realpath "${1:?Usage: release.sh /opt/guojing/releases/ID [--rollback]}")
[[ $release =~ ^/opt/guojing/releases/[a-zA-Z0-9._-]+$ ]]
[[ -f "$release/uv.lock" && -f "$release/migrations/versions/20260927_13_add_device_admission.py" ]]
[[ ! -e "$release/.git" ]]
sensitive=$(find "$release" -path "$release/.venv" -prune -o -type f \( \
    -name '.env' -o \( -name '.env.*' ! -name '.env.example' \) \
    -o -name 'local.properties' -o -name '*.jks' -o -name '*.keystore' \
    -o -name '*.apk' -o -name '*.db' \) -print -quit)
[[ -z "$sensitive" ]] || { printf 'Release tree contains local secrets or generated files\n' >&2; exit 1; }
old=$(readlink -f /opt/guojing/current || true)
[[ $old != "$release" ]]
cd "$release"
UV_PYTHON_INSTALL_DIR=/opt/guojing/python uv sync --locked --no-dev --python 3.12.13
# uv's generated entrypoints embed this immutable release path.
chmod -R a+rX "$release"
run_in() {
    local tree=$1
    shift
    (cd "$tree" && runuser -u guojing -- "$tree/.venv/bin/python" "$tree/deploy/with-env.py" "$@")
}
fail_closed() {
    if [[ -L /opt/guojing/current ]]; then
        run_in /opt/guojing/current /opt/guojing/current/.venv/bin/guojing-admin pause || true
    fi
    printf 'Release failed; admission remains paused. Inspect journal and use rollback.sh.\n' >&2
}
trap fail_closed ERR
if [[ -n "$old" && -d "$old" ]]; then
    run_in "$old" "$old/.venv/bin/guojing-admin" drain --timeout 125 || true
    systemctl stop guojing
    run_in "$old" "$old/.venv/bin/guojing-admin" backup
fi
if [[ ${2:-} == --rollback ]]; then
    [[ -n "$old" && -d "$old" ]]
    target=$(run_in "$release" "$release/.venv/bin/alembic" heads | awk '{print $1}')
    [[ $target =~ ^[a-zA-Z0-9_]+$ ]]
    run_in "$old" "$old/.venv/bin/alembic" downgrade "$target"
else
    run_in "$release" "$release/.venv/bin/alembic" upgrade head
fi
run_in "$release" "$release/.venv/bin/guojing-admin" pause
# A real rootless cgroup probe is required for each release, without a model call.
run_in "$release" "$release/.venv/bin/python" -m guojing.operations.sandbox_check
ln -s "$release" /opt/guojing/current.next
mv -Tf /opt/guojing/current.next /opt/guojing/current
if [[ -n "$old" && -d "$old" ]]; then
    ln -sfn "$old" /opt/guojing/previous
fi
systemctl enable guojing
systemctl restart guojing
healthy=0
for attempt in $(seq 1 20); do
    if curl -fsS --max-time 8 http://127.0.0.1:8000/internal/status | "$release/.venv/bin/python" -c 'import json,sys; sys.exit(not json.load(sys.stdin)["dependencies_ready"])'; then
        healthy=1
        break
    fi
    sleep 2
done
[[ $healthy == 1 ]]
curl -fsS --max-time 5 http://127.0.0.1:8000/health >/dev/null
code=$(curl -sS --max-time 5 -o /dev/null -w '%{http_code}' -X POST http://127.0.0.1:8000/api/v1/agent/sessions)
[[ $code == 401 ]]
run_in "$release" "$release/.venv/bin/guojing-admin" resume
curl -fsS --max-time 8 http://127.0.0.1:8000/ready >/dev/null
systemctl enable --now guojing-backup.timer guojing-monitor.timer guojing-prune.timer
systemctl start guojing-backup.service
trap - ERR
printf 'Released %s\n' "$release"
