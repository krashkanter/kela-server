#!/system/bin/sh
set -eu
/data/local/server/mount-storage.sh
root=/data/local/debian
# Supervisor takes a nonblocking flock, so repeated phone-stack retries are safe.
nohup chroot "$root" /usr/bin/env -i HOME=/root PATH=/usr/local/sbin:/usr/local/bin:/usr/sbin:/usr/bin:/sbin:/bin /usr/bin/python3 /opt/kela-storage/supervise.py >> "$root/var/log/kela-storage/launcher.log" 2>&1 < /dev/null &
