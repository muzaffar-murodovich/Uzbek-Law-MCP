#!/bin/zsh
# Install the home-side jobs (run from the Mac):  deploy/home/install.sh
#   ~/qonunshunos-ops/        scripts            ~/.config/systemd/user/   timers
#   ~/.config/qonunshunos/watch.env   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID (created once, by hand)
set -euo pipefail
HOST=${QONUNSHUNOS_HOME_HOST:-home}
cd ${0:A:h}
ssh $HOST 'mkdir -p ~/qonunshunos-ops ~/.config/systemd/user ~/.config/qonunshunos'
rsync -a telegram.sh qonunshunos-watch.sh backup-pull.sh $HOST:qonunshunos-ops/
rsync -a *.service *.timer $HOST:.config/systemd/user/
ssh $HOST 'set -e
  [ -f ~/.config/qonunshunos/watch.env ] || {
    printf "TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\n" > ~/.config/qonunshunos/watch.env
    echo "fill in ~/.config/qonunshunos/watch.env"; }
  chmod 600 ~/.config/qonunshunos/watch.env
  systemctl --user daemon-reload
  systemctl --user enable --now qonunshunos-watch.timer backup-pull.timer
  systemctl --user list-timers --no-pager | grep -E "qonunshunos|backup-pull"'
