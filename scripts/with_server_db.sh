#!/usr/bin/env bash
# Run a command against the server database through an SSH tunnel.
#
#   bash scripts/with_server_db.sh uv run qonunshunos eval --questions eval/questions_llm_full.yaml \
#       --alt-file eval/alt_llm_questions_llm_full.json --workers 4 --save <label>
#
# Opens 127.0.0.1:15432 -> server 127.0.0.1:5432, sets QONUNSHUNOS_DSN from the server .env
# (never printed) and closes the tunnel on exit. Meant for read-only evaluation scripts; the
# user runs it in a plain terminal (auto mode refuses to open the tunnel itself).
# Host: $QONUNSHUNOS_HOST, else MYSERVER_SSH from home's watch.env (home has no "myserver" alias).
set -euo pipefail
cd "$(dirname "$0")/.."
[ $# -gt 0 ] || { echo "usage: $0 <command> [args...]" >&2; exit 2; }

WATCH_ENV=~/.config/qonunshunos/watch.env
if [ -z "${QONUNSHUNOS_HOST:-}" ] && [ -f "$WATCH_ENV" ]; then
    QONUNSHUNOS_HOST=$(sed -n 's/^MYSERVER_SSH=//p' "$WATCH_ENV" | tr -d "\"'")
fi
HOST=${QONUNSHUNOS_HOST:-myserver}
FORWARD="ssh -f -N -o ExitOnForwardFailure=yes -L 15432:127.0.0.1:5432"

ss -ltn | grep -q ":15432 " || $FORWARD "$HOST"
trap 'pkill -f "$FORWARD" || true' EXIT

dsn=$(ssh "$HOST" "grep '^QONUNSHUNOS_DSN=' /home/deploy/qonunshunos/.env" | cut -d= -f2- | tr -d "'\"")
[ -n "$dsn" ] || { echo "could not read the server DSN" >&2; exit 1; }
export QONUNSHUNOS_DSN
QONUNSHUNOS_DSN=$(printf '%s' "$dsn" | sed -E 's#@[^/]+/#@127.0.0.1:15432/#')
unset dsn

"$@"
