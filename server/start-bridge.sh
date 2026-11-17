#!/system/bin/sh
set -eu
root=/data/local/debian
pidfile="$root/run/kela.pid"
if [ -f "$pidfile" ]; then
 pid=$(cat "$pidfile")
 if kill -0 "$pid" 2>/dev/null && tr '\0' ' ' < "/proc/$pid/cmdline" | grep -q '/opt/kela/kela_server.py'; then exit 0; fi
fi
mkdir -p "$root/opt/kela" "$root/etc/kela"
chmod 700 "$root/etc/kela"
nohup /data/local/server/debian python3 /opt/kela/kela_server.py > "$root/var/log/kela.log" 2>&1 < /dev/null &
echo $! > "$pidfile"