#!/usr/bin/env bash
# Nightly (backup-pull.timer): copy myserver:~/backups (all apps' dumps) to home, keep 30 days,
# and leave a marker on myserver so its morning report shows when the last copy left.
set -euo pipefail
DEST=${BACKUP_PULL_DEST:-$HOME/backups/myserver}
DIR=$(dirname "$0")
# MYSERVER_SSH (e.g. deploy@<ip>) lives in watch.env: home's ~/.ssh/config has no "myserver".
. "${QONUNSHUNOS_WATCH_ENV:-$HOME/.config/qonunshunos/watch.env}"
SERVER=${MYSERVER_SSH:-myserver}
export RSYNC_RSH="ssh -o BatchMode=yes -o ConnectTimeout=20"
mkdir -p "$DEST"
fail() { "$DIR/telegram.sh" "❌ home: myserver zaxirasini ko'chirib bo'lmadi: $1" || true; exit 1; }

# No --delete: myserver keeps 14 days, home keeps 30.
rsync -a --timeout=300 --exclude '.pulled' --exclude '*.tmp' "$SERVER:backups/" "$DEST/" \
    || fail "rsync $?"
newest=$(find "$DEST" -name 'qonunshunos_*.dump' -mtime -1 | head -1)
[ -n "$newest" ] || fail "oxirgi 24 soatda qonunshunos dump'i yo'q"
$RSYNC_RSH "$SERVER" 'touch ~/backups/.pulled' || fail "marker"
find "$DEST" -type f \( -name '*.dump' -o -name '*.sql.gz' -o -name '*.tar.gz' \) -mtime +30 -delete
echo "pulled to $DEST: $(du -sh "$DEST" | cut -f1)"
