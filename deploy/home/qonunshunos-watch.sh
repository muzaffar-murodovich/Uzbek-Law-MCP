#!/usr/bin/env bash
# Every 5 minutes (qonunshunos-watch.timer): is the public site up? Alerts on the 2nd failure
# in a row and again when it recovers. Runs on home, so it also notices myserver being down.
set -uo pipefail
URL=${NIZOM_HEALTH_URL:-https://nizom.org/healthz}
STATE=${XDG_STATE_HOME:-$HOME/.local/state}/qonunshunos-watch
DIR=$(dirname "$0")
mkdir -p "$STATE"
failures=$(cat "$STATE/failures" 2>/dev/null || echo 0)

if body=$(curl -fsS -m 15 "$URL" 2>&1) && [[ $body == *'"ok":true'* ]]; then
    if [ "$failures" -ge 2 ]; then
        "$DIR/telegram.sh" "✅ nizom.org yana ishlayapti ($failures marta xatodan keyin)"
    fi
    echo 0 > "$STATE/failures"
    exit 0
fi

failures=$((failures + 1))
echo "$failures" > "$STATE/failures"
echo "health check failed ($failures): $body"
if [ "$failures" -eq 2 ]; then
    "$DIR/telegram.sh" "🔴 nizom.org ishlamayapti: ${body:0:300}"
elif [ $((failures % 36)) -eq 0 ]; then  # remind every 3 hours
    "$DIR/telegram.sh" "🔴 nizom.org hali ham ishlamayapti ($((failures * 5)) daqiqa)"
fi
