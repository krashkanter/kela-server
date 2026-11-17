#!/system/bin/sh
set -eu
root=/data/local/debian
image=$root/var/lib/kela-storage/primary.ext4
target=/data/local/server/bucket
[ -s "$image" ] || { echo 'Primary image missing; refusing unbounded fallback' >&2; exit 1; }
mkdir -p "$target" "$root/srv/bucket"
chcon u:object_r:shell_data_file:s0 "$image"
if ! mountpoint -q "$target"; then
 mount -t ext4 -o loop,noatime,nosuid,nodev,noexec "$image" "$target"
fi
# A wrong existing bind must fail closed instead of accepting internal F2FS.
chroot "$root" /usr/bin/python3 /opt/kela-storage/check_primary.py || {
 while mountpoint -q "$root/srv/bucket"; do umount "$root/srv/bucket"; done
 mount -o bind "$target" "$root/srv/bucket"
}
chroot "$root" /usr/bin/python3 /opt/kela-storage/check_primary.py
