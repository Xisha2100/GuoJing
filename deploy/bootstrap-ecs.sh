#!/usr/bin/env bash
# Run as root on a fresh Ubuntu 24.04 x86_64 ECS. Does not purchase or expose a server.
set -euo pipefail
[[ $EUID -eq 0 && $(uname -m) == x86_64 ]]
. /etc/os-release
[[ $ID == ubuntu && $VERSION_ID == 24.04 ]]
apt-get update
apt-get install -y ca-certificates curl gnupg nginx certbot uidmap dbus-user-session slirp4netns git xz-utils
install -m 0755 -d /etc/apt/keyrings
curl --fail --silent --show-error https://download.docker.com/linux/ubuntu/gpg -o /etc/apt/keyrings/docker.asc
chmod a+r /etc/apt/keyrings/docker.asc
cat > /etc/apt/sources.list.d/docker.sources <<'APT'
Types: deb
URIs: https://download.docker.com/linux/ubuntu
Suites: noble
Components: stable
Signed-By: /etc/apt/keyrings/docker.asc
APT
apt-get update
apt-get install -y docker-ce docker-ce-cli containerd.io docker-ce-rootless-extras
systemctl disable --now docker.service docker.socket
id guojing >/dev/null 2>&1 || useradd --create-home --home-dir /var/lib/guojing --shell /bin/bash guojing
install -d -o guojing -g guojing -m 0700 /var/lib/guojing/data
install -d -o root -g guojing -m 0750 /etc/guojing /opt/guojing/releases /opt/guojing/python
install -d -m 0755 /var/www/letsencrypt
uid=$(id -u guojing)
install -d /etc/systemd/system/user@.service.d
cat > /etc/systemd/system/user@.service.d/guojing-delegate.conf <<'UNIT'
[Service]
Delegate=cpu cpuset io memory pids
UNIT
systemctl daemon-reload
loginctl enable-linger guojing
systemctl restart "user@$uid.service"
runuser -l guojing -c "XDG_RUNTIME_DIR=/run/user/$uid dockerd-rootless-setuptool.sh install"
# Fixed installer version; archive is downloaded over HTTPS from the upstream release.
curl --fail --silent --show-error --location https://github.com/astral-sh/uv/releases/download/0.11.19/uv-x86_64-unknown-linux-gnu.tar.gz -o /tmp/guojing-uv.tar.gz
tar -xzf /tmp/guojing-uv.tar.gz -C /tmp
install -m 0755 /tmp/uv-x86_64-unknown-linux-gnu/uv /usr/local/bin/uv
UV_PYTHON_INSTALL_DIR=/opt/guojing/python uv python install 3.12.13
chmod -R a+rX /opt/guojing/python
install -m 0644 "$(dirname "$0")"/systemd/* /etc/systemd/system/
systemctl daemon-reload
printf 'Rootless Docker socket: unix:///run/user/%s/docker.sock\n' "$uid"
printf 'Next: fill /etc/guojing/production.env, pre-pull pinned image, publish release, configure TLS and alerts.\n'
