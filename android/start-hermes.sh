#!/system/bin/sh
set -eu
root=/data/local/debian
if [ ! -f "$root/opt/hermes/.configured" ]; then
 echo 'Hermes activation pending Telegram owner and model credentials.'
 exit 0
fi
/data/local/server/debian docker compose -f /opt/hermes/compose.yaml up -d
