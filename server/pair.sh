#!/system/bin/sh
set -eu
n=0
while [ ! -s /data/local/debian/etc/kela/token ]; do
 n=$((n+1)); [ "$n" -lt 20 ] || exit 1; sleep 1
done
run-as com.krashkanter.kela sh -c 'umask 077; mkdir -p files; cat > files/token' < /data/local/debian/etc/kela/token