# Setup and runtime

Kela Server contains the authenticated Python Docker bridge, Android chroot/Docker scripts, daemon configuration, nginx/Cloudflare templates, native Android init integration, and optional Hermes deployment used on the Redmi Note 9 server. Cloning this repository makes no changes to a device.

The bridge matches the version verified on the phone: SHA-256 `b5c17ed31cb9d48550e4f121889eb47437d747548c86abd318f41fed481075af`. The [Kela app](https://github.com/krashkanter/kela) retains its bundled bridge for compatibility with its existing installer.

## Prerequisites

Provision an ARM64 Debian chroot at `/data/local/debian`, with Python 3, Docker Engine and Compose. The tested versions were Debian 13.7, Docker 26.1.5 and Compose 2.26.1. The chroot shares Android's kernel; the tested container-enabled [merlinx images](https://github.com/krashkanter/merlinx-os-releases/releases/tag/lineage-24-server-20261117) are separate.

Startup expects an existing ext4 Docker backing image at Android `/data/local/server/docker.ext4`, its empty mountpoint `/data/local/debian/var/lib/docker`, a bucket directory `/data/local/server/bucket`, and mountpoint `/data/local/debian/srv/bucket`. The usual chroot `/dev`, `/sys`, `/proc`, `/run`, `/opt`, `/etc` and `/var/log` directories must exist. The tested backing image was a 16 GiB sparse ext4 filesystem. No filesystem image, volumes, backup, private account state or automated storage installer is included here.

## Runtime paths

Debian paths below are inside the chroot; prepend `/data/local/debian` when copying through Android ADB.

| Repository file | Installed path |
| --- | --- |
| `android/debian` | Android `/data/local/server/debian` |
| `android/start.sh`, `android/stop.sh` | Android `/data/local/server/start.sh`, `/data/local/server/stop.sh` |
| `android/quiet-hardware.sh` | Android `/data/local/server/quiet-hardware.sh` (merlinx-specific; review before use) |
| `server/kela_server.py` | Debian `/opt/kela/kela_server.py` |
| `server/start-bridge.sh`, `server/stop-bridge.sh` | Android `/data/local/server/start-kela.sh`, `/data/local/server/stop-kela.sh` |
| `docker/daemon.json` | Debian `/etc/docker/daemon.json` |
| `gateway/` | Debian `/opt/phone-gateway/` |
| `init/phone-services.rc` | Android `/system_ext/etc/init/phone-services.rc`, via a matching ROM/image build |
| `init/phone-services` | Android `/system_ext/bin/phone-services`, via a matching ROM/image build |

Keep Android server scripts and their directory mode `0700`. The bridge creates Debian `/etc/kela/token` mode `0600`; keep its directory `0700`. The bridge listens only on `127.0.0.1:9473` and requires a bearer token. `server/pair.sh` transfers that token directly into the installed debug Kela app's private files using `run-as`, entirely on the phone. Keep the token, Docker socket and Kela/DroidUtils APIs private. The nginx gateway does not proxy these management APIs.

After provisioning the chroot, backing storage and file mapping, manual startup is:

```sh
adb root
adb shell sh /data/local/server/start.sh
```

Use the app repository's existing installation/pairing procedure for the Android client.

## Android behavior and native startup

`start.sh` prepares recursive chroot mounts with slave propagation, labels/mounts the ext4 storage and starts dockerd with `DOCKER_RAMDISK=true`. The daemon config allocates networks from `172.28.0.0/16`; startup adds scoped policy routes for that subnet through Android's named `wlan0` routing table. Change the subnet and route rules together when adapting it. Android's firewall is not flushed. Hybrid cgroups still limit some resource controls.

The script starts the gateway and installed Kela/Hermes hooks. A partial wake lock keeps serving with the screen off. `stop.sh` is the existing gateway/dockerd shutdown helper and releases the wake lock; it is not a complete native-init/optional-service shutdown controller. Stop native init supervisors deliberately before maintenance, or they can restart the stack. `server/stop-bridge.sh` stops the bridge separately.

The native init image starts `phone-hardware`, `phone-stack` and `phone-sysutils` after `sys.boot_completed=1`. It also requires `/data/local/sysutils/bin/sysutilsd` from [DroidUtils](https://github.com/krashkanter/droidutils), started without `-boot`. Create Android `/data/local/server/disable-autostart` through recovery/rooted ADB to hold all startup wrappers during repairs. Logs are in `/data/local/server/boot-logs`.

Android is globally SELinux Enforcing, but root server processes use LineageOS userdebug's existing permissive `su` domain. This is not a confined production service configuration. Magisk is not required. The `.mk` integration is restricted to userdebug/eng; use the matching image/source-build integration rather than assuming a writable system_ext overlay will survive reboot.

`quiet-hardware.sh` disables cellular, retains Wi-Fi/Bluetooth, starts the fingerprint service, and waits for modem GATED state before stopping its retrying loader. It is specific to this merlinx hardware setup. Review it before applying to a phone used for cellular service or a different device. It does not modify IMEI/NVRAM/calibration or stop camera services.

Automatic startup of the original gateway/bridge stack passed two boots. Android's named wlan0 routing table appeared after the first attempt; the init wrapper's 30-second retry recovered. Offline startup was not tested.

## Gateway and Cloudflare

The gateway publishes HTTP on port 8080 and includes nginx homepage/example containers on `phone-edge`. The homepage is a neutral public example. Optional Compose profiles are `quick` and `cloudflare`.

Named-tunnel authentication is read from Debian `/etc/cloudflared/tunnel-token`; provision it privately with restrictive permissions. No tunnel account or hostname is included. Startup selects a named tunnel when that token exists, or a quick tunnel only when Android `/data/local/server/enable-quick-tunnel` exists. cloudflared uses HTTP/2, drops all capabilities, enables no-new-privileges and has a read-only root filesystem. nginx/cloudflared tags follow the original templates; pin digests for repeatable future deployments.

## Optional Hermes

Copy `optional/hermes/compose.yaml` and `config.yaml` to Debian `/opt/hermes` and install `android/start-hermes.sh` as Android `/data/local/server/start-hermes.sh` only if this agent is wanted.

The official NousResearch Hermes v0.23.2 image is pinned by digest. Persistent state is Debian `/opt/hermes/data`, mounted at container `/opt/data`. No host ports, Docker socket or Android system directories are mounted. The official entrypoint remaps the runtime user to UID 2000/GID 3003 for Android networking. The terminal backend runs inside the container; the configured Qwen model runs remotely through OpenRouter.

Initialize the profile using the upstream Hermes setup and enter your own credentials privately. Keep `data/.env` mode `0600`, owner 2000:3003, and preserve generated profile keys. Restrict `TELEGRAM_ALLOWED_USERS` to your own numeric user ID; configure `TELEGRAM_BOT_TOKEN` and `OPENROUTER_API_KEY`. No live bot identity, owner ID, credential or session database is supplied.

After initialization and credential verification, create Debian `/opt/hermes/.configured`; its startup hook skips activation until that marker exists. The deployed agent was verified with a real Telegram reply, but it was added after the two native-init boot tests and has not had a separate phone reboot test.

## Validation

```sh
python3 -m unittest discover -s server
```

These existing tests cover bridge input validation, Docker data handling, authentication and HTTP behavior. They do not provision a device. Some `docker exec` operations can fail with runc working-directory ENOENT on this Android/chroot host even while the running services work.
