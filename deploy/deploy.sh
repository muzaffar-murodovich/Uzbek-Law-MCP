#!/bin/zsh
# Deploy the current working tree to myserver (no root needed once root-setup.sh has run).
#   deploy/deploy.sh            code + dependencies + migrations + restart + health check
# The server's .env (DSN, public URL, Google client) is created once by hand and never synced.
set -euo pipefail

HOST=${QONUNSHUNOS_HOST:-myserver}
APP=/home/deploy/qonunshunos
MODEL=data/models/Xenova__multilingual-e5-small
cd ${0:A:h}/..
# One shared connection: myserver refuses SSH after a burst of new connections.
SSH_OPTS=(-o ControlMaster=auto -o ControlPath=/tmp/qs-ssh-%r@%h -o ControlPersist=10m)
ssh() { command ssh $SSH_OPTS "$@"; }
export RSYNC_RSH="ssh ${SSH_OPTS[*]}"

print "== export locked dependencies"
uv export --frozen --no-dev --no-hashes --no-emit-project -q -o deploy/requirements.txt

print "== sync code"
rsync -az --delete \
    --exclude /.git/ --exclude /.venv/ --exclude /venv/ --exclude /data/ --exclude /.env \
    --exclude __pycache__/ --exclude .pytest_cache/ --exclude .ruff_cache/ \
    --exclude /eval/results/ --exclude /tests/ \
    ./ $HOST:$APP/

print "== sync the int8 embedding model (fp32 file skipped)"
ssh $HOST "mkdir -p $APP/$MODEL"
rsync -az --exclude 'onnx/model.onnx' $MODEL/ $HOST:$APP/$MODEL/

print "== install and migrate"
ssh $HOST "set -e; cd $APP
  [ -d venv ] || python3 -m venv venv
  venv/bin/pip install -q --upgrade pip
  venv/bin/pip install -q -r deploy/requirements.txt
  venv/bin/pip install -q --no-deps --force-reinstall .
  venv/bin/qonunshunos db-migrate"

if ssh $HOST "systemctl cat qonunshunos >/dev/null 2>&1"; then
  print "== restart"
  ssh $HOST "sudo -n systemctl restart qonunshunos"
  for i in {1..30}; do
    ssh $HOST "curl -fsS http://127.0.0.1:8100/healthz" 2>/dev/null && { print; exit 0; }
    sleep 2
  done
  print "health check failed:"; ssh $HOST "journalctl -u qonunshunos -n 30 --no-pager"; exit 1
else
  print "== service not installed yet: run deploy/root-setup.sh with sudo (see its header)"
fi
