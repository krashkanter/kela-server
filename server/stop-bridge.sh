#!/system/bin/sh
set -eu
pidfile=/data/local/debian/run/kela.pid
if [ -f "$pidfile" ]; then
 pid=$(cat "$pidfile")
 if kill -0 "$pid" 2>/dev/null && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q '/opt/kela/kela_server.py'; then
  kill -TERM "$pid"
  n=0
  while kill -0 "$pid" 2>/dev/null; do n=$((n+1)); [ "$n" -lt 10 ] || exit 1; sleep 1; done
 fi
 rm -f "$pidfile"
fi