#!/usr/bin/env bash
# Send stdin (or "$*") to the operator's Telegram chat. Settings: ~/.config/qonunshunos/watch.env
set -euo pipefail
. "${QONUNSHUNOS_WATCH_ENV:-$HOME/.config/qonunshunos/watch.env}"
text=${*:-$(cat)}
# The URL (with the token) goes through stdin, not argv, which other users could see in `ps`.
curl -fsS -m 20 -o /dev/null -K - \
    --data-urlencode "chat_id=$TELEGRAM_CHAT_ID" \
    --data-urlencode "text=$text" \
    --data "disable_web_page_preview=true" \
    <<<"url = \"https://api.telegram.org/bot$TELEGRAM_BOT_TOKEN/sendMessage\""
