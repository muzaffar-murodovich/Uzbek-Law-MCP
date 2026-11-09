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
# Full dumps are ~1 GB since the full corpus (2026-11-09); embeddings can be recomputed, so
# only 3 days stay here (home keeps 14). Users and OAuth cannot be recomputed: they also get
# a small separate dump that is kept for 30 days.
RETENTION_DAYS=3
AUTH_RETENTION_DAYS=30
AUTH_TABLES=(users user_identities oauth_clients oauth_codes oauth_consents oauth_tokens
    auth_requests usage_events)

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

# Small dump of what cannot be rebuilt from lex.uz: accounts, OAuth, usage.
auth_out="$BACKUP_DIR/qonunshunos-auth_$(date +%Y%m%d_%H%M%S).dump"
auth_tmp="$auth_out.tmp"
trap 'rm -f "$tmp" "$auth_tmp"' EXIT
table_args=()
for table in "${AUTH_TABLES[@]}"; do table_args+=(--table="public.$table"); done
if ! pg_dump --format=custom --no-owner --no-privileges --dbname="$DSN" --file="$auth_tmp" \
    "${table_args[@]}" 2>>"$LOG"; then
    log "FAIL qonunshunos-auth: pg_dump"
    exit 1
fi
grep -q "TABLE DATA public users " <<<"$(pg_restore --list "$auth_tmp")" \
    || { log "FAIL qonunshunos-auth: no users"; exit 1; }
mv "$auth_tmp" "$auth_out"
log "OK   qonunshunos-auth -> $(basename "$auth_out") ($(wc -c < "$auth_out" | tr -d " ") bayt)"

find "$BACKUP_DIR" -name 'qonunshunos_*.dump' -mtime +$RETENTION_DAYS -delete
find "$BACKUP_DIR" -name 'qonunshunos-auth_*.dump' -mtime +$AUTH_RETENTION_DAYS -delete
