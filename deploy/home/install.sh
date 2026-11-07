#!/bin/zsh
# Install the home-side jobs (run from the Mac):  deploy/home/install.sh
#   ~/qonunshunos-ops/        scripts            ~/.config/systemd/user/   timers
#   ~/.config/qonunshunos/watch.env   TELEGRAM_BOT_TOKEN, TELEGRAM_CHAT_ID, MYSERVER_SSH=deploy@<ip>
#                                     (created once, by hand)
set -euo pipefail
HOST=${QONUNSHUNOS_HOME_HOST:-home}
cd ${0:A:h}
ssh $HOST 'mkdir -p ~/qonunshunos-ops ~/.config/systemd/user ~/.config/qonunshunos'
# tar, not rsync: macOS openrsync silently skipped some of several source files.
SCRIPTS=(telegram.sh qonunshunos-watch.sh backup-pull.sh)
UNITS=(*.service *.timer)
COPYFILE_DISABLE=1 tar --no-xattrs -cf - $SCRIPTS | ssh $HOST 'tar -xf - -C ~/qonunshunos-ops'
COPYFILE_DISABLE=1 tar --no-xattrs -cf - $UNITS | ssh $HOST 'tar -xf - -C ~/.config/systemd/user'
ssh $HOST "cd ~/qonunshunos-ops && ls ${SCRIPTS[*]} >/dev/null && test -x backup-pull.sh &&
  cd ~/.config/systemd/user && ls ${UNITS[*]} >/dev/null" || { print "copy failed"; exit 1; }
ssh $HOST 'set -e
  [ -f ~/.config/qonunshunos/watch.env ] || {
    printf "TELEGRAM_BOT_TOKEN=\nTELEGRAM_CHAT_ID=\nMYSERVER_SSH=\n" > ~/.config/qonunshunos/watch.env
    echo "fill in ~/.config/qonunshunos/watch.env"; }
  chmod 600 ~/.config/qonunshunos/watch.env
  systemctl --user daemon-reload
  systemctl --user enable --now qonunshunos-watch.timer backup-pull.timer
  systemctl --user list-timers --no-pager | grep -E "qonunshunos|backup-pull"'
