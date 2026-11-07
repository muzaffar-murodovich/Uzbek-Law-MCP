#!/usr/bin/env bash
# Nightly dump of the qonunshunos database into ~/backups (qonunshunos-backup.timer).
# home pulls the whole folder afterwards (deploy/home/backup-pull.sh). Restore steps:
# docs/stage5-ops.md, "Zaxiradan tiklash".
set -euo pipefail
umask 077
export LC_ALL=C.UTF-8

APP=${QONUNSHUNOS_APP:-/home/deploy/qonunshunos}
BACKUP_DIR=${QONUNSHUNOS_BACKUPS_DIR:-/home/deploy/backups}
LOG="$BACKUP_DIR/backup.log"
RETENTION_DAYS=14

log() { echo "$(date '+%Y-%m-%d %H:%M:%S') $*" | tee -a "$LOG"; }

DSN=$(grep '^QONUNSHUNOS_DSN=' "$APP/.env" | cut -d= -f2-)
[ -n "$DSN" ] || { log "FAIL qonunshunos: QONUNSHUNOS_DSN is empty"; exit 1; }
# The password goes through the environment, not argv (argv is visible in `ps`).
read -r PGPASSWORD DSN < <(python3 - "$DSN" <<'PY'
import sys, urllib.parse as u
p = u.urlparse(sys.argv[1])
host = p.hostname + (f":{p.port}" if p.port else "")
print(u.unquote(p.password or ""), p._replace(netloc=f"{p.username}@{host}").geturl())
PY
)
export PGPASSWORD

mkdir -p "$BACKUP_DIR"
out="$BACKUP_DIR/qonunshunos_$(date +%Y%m%d_%H%M%S).dump"
tmp="$out.tmp"
trap 'rm -f "$tmp"' EXIT

# Custom format: compressed, and pg_restore can restore single tables.
if ! pg_dump --format=custom --no-owner --no-privileges --dbname="$DSN" --file="$tmp" 2>>"$LOG"; then
    log "FAIL qonunshunos: pg_dump"
    exit 1
fi
# A readable table of contents with the main tables means the dump is usable.
toc=$(pg_restore --list "$tmp")
for table in documents chunks users usage_events; do
    grep -q "TABLE DATA public $table " <<<"$toc" || { log "FAIL qonunshunos: no $table"; exit 1; }
done
mv "$tmp" "$out"
log "OK   qonunshunos -> $(basename "$out") ($(wc -c < "$out" | tr -d " ") bayt)"

find "$BACKUP_DIR" -name 'qonunshunos_*.dump' -mtime +$RETENTION_DAYS -delete
