#!/system/bin/sh
set -eu
settings put global airplane_mode_radios cell
cmd connectivity airplane-mode enable
cmd wifi set-wifi-enabled enabled
cmd bluetooth_manager enable
# Fingerprint reader has been reattached; leave its vendor service enabled.
start vendor.fingerprint-default
# Wait for the existing modem shutdown before stopping its retrying loader.
n=0
while [ "$n" -lt 90 ]; do
 case "$(cat /sys/kernel/ccci/boot)" in
  'md1:1 |'*) stop ccci_mdinit; break ;;
 esac
 n=$((n+1)); sleep 1
done
[ "$n" -lt 90 ] || { echo 'Modem did not reach GATED; loader left unchanged'; exit 2; }
cat /sys/kernel/ccci/boot
getprop init.svc.ccci_mdinit
getprop init.svc.vendor.fingerprint-default
