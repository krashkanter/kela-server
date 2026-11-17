#!/system/bin/sh
set -eu
root=/data/local/debian
# Make the chroot root a mountpoint, required by Docker's mount setup.
mountpoint -q "$root" || mount --rbind "$root" "$root"
for name in dev sys proc; do
 mountpoint -q "$root/$name" || mount --rbind "/$name" "$root/$name"
done
chroot "$root" /bin/mount --make-rslave /
mountpoint -q "$root/run" || mount -t tmpfs tmpfs "$root/run"
chcon u:object_r:shell_data_file:s0 /data/local/server/docker.ext4
mountpoint -q "$root/var/lib/docker" || mount -t ext4 -o loop,noatime /data/local/server/docker.ext4 "$root/var/lib/docker"
mountpoint -q "$root/srv/bucket" || mount -o bind /data/local/server/bucket "$root/srv/bucket"
ip rule show | grep -q '10000:.*172.28.0.0/16.*main' || ip rule add priority 10000 to 172.28.0.0/16 lookup main
ip rule show | grep -q '10010:.*172.28.0.0/16.*wlan0' || ip rule add priority 10010 from 172.28.0.0/16 lookup wlan0
# A partial wake lock keeps serving with the screen off; stop.sh releases it.
if [ -w /sys/power/wake_lock ]; then echo phone-server > /sys/power/wake_lock; fi
if ! pidof dockerd >/dev/null; then
 nohup chroot "$root" /usr/bin/env -i DOCKER_RAMDISK=true HOME=/root PATH=/usr/sbin:/usr/bin:/sbin:/bin /usr/sbin/dockerd > "$root/var/log/dockerd.log" 2>&1 < /dev/null &
fi
n=0
while ! /data/local/server/debian docker info >/dev/null 2>&1; do
 n=$((n+1)); [ "$n" -lt 30 ] || exit 1; sleep 1
done
/data/local/server/debian docker compose -f /opt/phone-gateway/compose.yaml up -d
if [ -s "$root/etc/cloudflared/tunnel-token" ]; then
 /data/local/server/debian docker compose -f /opt/phone-gateway/compose.yaml --profile cloudflare up -d cloudflare
elif [ -f /data/local/server/enable-quick-tunnel ]; then
 /data/local/server/debian docker compose -f /opt/phone-gateway/compose.yaml --profile quick up -d quick-tunnel
fi
[ ! -x /data/local/server/start-kela.sh ] || /data/local/server/start-kela.sh

[ ! -x /data/local/server/start-hermes.sh ] || /data/local/server/start-hermes.sh
