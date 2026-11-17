#!/system/bin/sh
set -eu
/data/local/server/debian docker compose -f /opt/phone-gateway/compose.yaml --profile quick --profile cloudflare stop
pid=$(pidof dockerd || true)
[ -z "$pid" ] || kill -TERM "$pid"
if [ -w /sys/power/wake_unlock ]; then echo phone-server > /sys/power/wake_unlock; fi