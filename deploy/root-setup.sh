#!/bin/bash
# One-time root setup of Qonunshunos on myserver. Idempotent: safe to run again.
# Run after deploy/deploy.sh has copied the code and .env:
#   ssh -t myserver 'sudo bash /home/deploy/qonunshunos/deploy/root-setup.sh'
set -euo pipefail

APP=/home/deploy/qonunshunos
DOMAIN=qonunshunos.muzaffar.zip
SERVICE=qonunshunos

step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$APP/.env" ] || { echo "$APP/.env is missing: run deploy/deploy.sh first"; exit 1; }

step "1/5 pgvector >= 0.8 from apt.postgresql.org (only this package comes from there)"
install -d /usr/share/postgresql-common/pgdg
curl -fsS -o /usr/share/postgresql-common/pgdg/apt.postgresql.org.asc \
    https://www.postgresql.org/media/keys/ACCC4CF8.asc
echo "deb [signed-by=/usr/share/postgresql-common/pgdg/apt.postgresql.org.asc]" \
    "https://apt.postgresql.org/pub/repos/apt noble-pgdg main" > /etc/apt/sources.list.d/pgdg.list
# Low priority for everything from PGDG, so PostgreSQL itself keeps coming from Ubuntu
# (no surprise upgrade of the cluster the other apps use); pgvector alone is preferred.
cat > /etc/apt/preferences.d/pgdg-pgvector-only <<'EOF'
Package: *
Pin: origin apt.postgresql.org
Pin-Priority: 100

Package: postgresql-16-pgvector
Pin: origin apt.postgresql.org
Pin-Priority: 600
EOF
apt-get update -qq
apt-get install -y -qq postgresql-16-pgvector
dpkg-query -W -f='installed: ${Package} ${Version}\n' postgresql-16-pgvector postgresql-16

step "2/5 database and role 'qonunshunos'"
DSN=$(grep '^QONUNSHUNOS_DSN=' "$APP/.env" | cut -d= -f2-)
PASS=$(python3 -c 'import sys, urllib.parse as u; print(u.unquote(u.urlparse(sys.argv[1]).password))' "$DSN")
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -v pass="$PASS" <<'SQL'
SELECT 'CREATE ROLE qonunshunos LOGIN'
 WHERE NOT EXISTS (SELECT FROM pg_roles WHERE rolname = 'qonunshunos')\gexec
ALTER ROLE qonunshunos PASSWORD :'pass';
SELECT 'CREATE DATABASE qonunshunos OWNER qonunshunos'
 WHERE NOT EXISTS (SELECT FROM pg_database WHERE datname = 'qonunshunos')\gexec
SQL
sudo -u postgres psql -q -v ON_ERROR_STOP=1 -d qonunshunos \
    -c 'CREATE EXTENSION IF NOT EXISTS vector' -c 'CREATE EXTENSION IF NOT EXISTS pg_trgm' \
    -c "SELECT extname, extversion FROM pg_extension WHERE extname IN ('vector', 'pg_trgm')"

step "3/5 systemd service and sudo rule for restarts"
install -m 644 "$APP/deploy/qonunshunos.service" /etc/systemd/system/$SERVICE.service
systemctl daemon-reload
systemctl enable $SERVICE >/dev/null
RULE="deploy ALL=(root) NOPASSWD: /usr/bin/systemctl start $SERVICE, /usr/bin/systemctl stop $SERVICE, /usr/bin/systemctl restart $SERVICE"
SUDOERS=/etc/sudoers.d/deploy-services
if ! grep -qF "$RULE" "$SUDOERS"; then
    cp "$SUDOERS" /tmp/deploy-services.new
    echo "$RULE" >> /tmp/deploy-services.new
    visudo -cf /tmp/deploy-services.new
    install -m 440 /tmp/deploy-services.new "$SUDOERS"
    rm /tmp/deploy-services.new
fi
echo "sudoers: $(grep -c "$SERVICE" "$SUDOERS") rule(s) for $SERVICE"

step "4/5 Let's Encrypt certificate for $DOMAIN (DNS only, HTTP-01 over port 80)"
install -d /var/www/letsencrypt
if [ ! -d /etc/letsencrypt/live/$DOMAIN ]; then
    cat > /etc/nginx/sites-available/$SERVICE <<EOF
server {
    listen 80;
    listen [::]:80;
    server_name $DOMAIN;
    location /.well-known/acme-challenge/ { root /var/www/letsencrypt; }
    location / { return 404; }
}
EOF
    ln -sf /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE
    nginx -t && systemctl reload nginx
    certbot certonly --webroot -w /var/www/letsencrypt -d $DOMAIN \
        --non-interactive --agree-tos --keep-until-expiring \
        --deploy-hook 'systemctl reload nginx'
fi

step "5/5 nginx site"
install -m 644 "$APP/deploy/nginx-qonunshunos.conf" /etc/nginx/sites-available/$SERVICE
ln -sf /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE
nginx -t && systemctl reload nginx

echo
echo "done. Start the app with: sudo systemctl restart $SERVICE (deploy/deploy.sh does it)"
