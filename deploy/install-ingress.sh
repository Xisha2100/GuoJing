#!/usr/bin/env bash
set -euo pipefail
[[ $EUID -eq 0 ]]
domain=${1:?Usage: install-ingress.sh DOMAIN CERTIFICATE_EMAIL}
email=${2:?Certificate renewal contact required}
[[ $domain =~ ^[a-zA-Z0-9][a-zA-Z0-9.-]+\.[a-zA-Z]{2,}$ ]]
# Bootstrap HTTP challenge configuration before the certificate exists.
cat > /etc/nginx/sites-available/guojing <<NGINX
server {
 listen 80;
 server_name $domain;
 location ^~ /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
 location / { return 503; }
}
NGINX
ln -sfn /etc/nginx/sites-available/guojing /etc/nginx/sites-enabled/guojing
nginx -t
systemctl reload nginx
certbot certonly --webroot -w /var/www/letsencrypt -d "$domain" --email "$email" --agree-tos --non-interactive
sed "s/API_DOMAIN/$domain/g" "$(dirname "$0")/nginx.conf.template" > /etc/nginx/sites-available/guojing
install -d /etc/letsencrypt/renewal-hooks/deploy
cat > /etc/letsencrypt/renewal-hooks/deploy/guojing-nginx <<'HOOK'
#!/bin/sh
nginx -t && systemctl reload nginx
HOOK
chmod 0755 /etc/letsencrypt/renewal-hooks/deploy/guojing-nginx
nginx -t
systemctl reload nginx
systemctl enable --now certbot.timer
