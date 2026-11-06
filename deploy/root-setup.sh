#!/bin/bash
# One-time root setup of Qonunshunos on myserver. Idempotent: safe to run again.
# Run after deploy/deploy.sh has copied the code and .env:
#   ssh -t myserver 'sudo bash /home/deploy/qonunshunos/deploy/root-setup.sh'
set -euo pipefail

APP=/home/deploy/qonunshunos
DOMAIN=qonunshunos.muzaffar.zip
SERVICE=qonunshunos
PGVECTOR=0.8.7
PGVECTOR_SHA256=cac0b10c360f05b2d521200105ba3697e773d4cd3731f5a915a7e37ebe0bea85

step() { printf '\n== %s\n' "$*"; }

[ "$(id -u)" -eq 0 ] || { echo "run with sudo"; exit 1; }
[ -f "$APP/.env" ] || { echo "$APP/.env is missing: run deploy/deploy.sh first"; exit 1; }

step "1/5 pgvector $PGVECTOR built from source against Ubuntu's PostgreSQL 16"
# PGDG's pgvector package requires PGDG's PostgreSQL build (it breaks Ubuntu's
# postgresql-16-jit-llvm), which would upgrade and restart the cluster the other apps use.
# Building the extension against the installed server touches nothing else.
rm -f /etc/apt/sources.list.d/pgdg.list /etc/apt/preferences.d/pgdg-pgvector-only
rm -rf /usr/share/postgresql-common/pgdg
if [ "$(cat /usr/share/postgresql/16/extension/vector.control 2>/dev/null \
        | sed -n "s/^default_version = '\(.*\)'/\1/p")" != "$PGVECTOR" ]; then
    apt-get update -qq
    apt-get install -y -qq postgresql-server-dev-16 build-essential
    BUILD=$(mktemp -d)
    curl -fsSL -o "$BUILD/src.tar.gz" \
        "https://github.com/pgvector/pgvector/archive/refs/tags/v$PGVECTOR.tar.gz"
    echo "$PGVECTOR_SHA256  $BUILD/src.tar.gz" | sha256sum -c -
    tar -xzf "$BUILD/src.tar.gz" -C "$BUILD"
    make -s -C "$BUILD/pgvector-$PGVECTOR" OPTFLAGS="" PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config
    make -s -C "$BUILD/pgvector-$PGVECTOR" install PG_CONFIG=/usr/lib/postgresql/16/bin/pg_config
    rm -rf "$BUILD"
fi
grep default_version /usr/share/postgresql/16/extension/vector.control

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

step "4/5 certificate: the existing *.muzaffar.zip Cloudflare Origin CA (proxied site)"
# 80/443 are open to Cloudflare only, so Let's Encrypt HTTP-01 cannot reach us; the site
# runs behind the Cloudflare proxy like muzaffar.zip and xorazmcha.muzaffar.zip.
openssl x509 -in /etc/ssl/certs/muzaffar.crt -noout -subject -enddate
rm -rf /var/www/letsencrypt

step "5/5 nginx site (replaces the temporary ACME-only one)"
install -m 644 "$APP/deploy/nginx-qonunshunos.conf" /etc/nginx/sites-available/$SERVICE
ln -sf /etc/nginx/sites-available/$SERVICE /etc/nginx/sites-enabled/$SERVICE
nginx -t && systemctl reload nginx

echo
echo "done. Start the app with: sudo systemctl restart $SERVICE (deploy/deploy.sh does it)"
