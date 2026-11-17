# Primary and secondary storage

This optional deployment uses phone internal storage as a global primary bucket.
Its sparse ext4 image has a hard 90,000,000,000-byte cap (90 decimal GB, about
83.8 GiB). Filesystem metadata reduces usable file space to about 89.3 GB.
This bounds allocated bucket data from every writer, including manual uploads.
It does not reserve physical space against growth by Android or other services.
The downloader also pauses when host free space drops below 4 GiB; manual uploads
remain subject to the primary filesystem's hard cap.

Only `phone-hermes` currently receives Docker volume `kela-primary`. The volume
is global and can be explicitly granted to other containers later. Primary is
mounted at Debian `/srv/bucket`, Android `/data/local/server/bucket`, and Hermes
`/buckets/primary`. No other existing container receives it.

The secondary bucket is currently **offline**. The file server exposes a read-only
placeholder at `/secondary`; no secondary writes fall back to internal storage.
There is no secondary Docker volume or container mount. Future USB attachment
requires manual host mount/configuration, verification of the actual external
device, and file-server restart. Do not change the placeholder to writable or
create internal storage under the external mountpoint. The real USB NAS and
disconnect behavior have not been tested; configure those when it is attached.

## Services and access

- Native aria2 downloads HTTP(S), magnets and uploaded `.torrent` files.
- A small native controller exposes restricted download operations over a Unix
  socket. Only UID 2000 (Hermes) and the device owner/root may call it. Its RPC
  secret is never mounted into Hermes. aria2 RPC listens on loopback port 6800.
- Native copyparty v1.20.26 provides authenticated manual upload/download,
  move and delete on `/primary`, and read access to offline `/secondary`.
- A native supervisor restarts services and handles Wi-Fi address changes.
  Copyparty listens only on loopback HTTPS port 8443. A small native TCP proxy
  running as Android shell UID 2000 forwards encrypted bytes from the Wi-Fi
  address, also port 8443. It accepts only the current Wi-Fi subnet, has a
  16-connection limit and cannot access secondary storage. It reads no file-server
  credentials or TLS keys. There is no tunnel or public gateway route; container
  subnets are denied before TLS forwarding.

Native file service UID 2901 and downloader/controller UID 2902 use GID 41001
and Android networking supplementary GID 3003. They drop all Linux capabilities
and enable no-new-privileges. UIDs 21001/21002 were tested and rejected by
Android's networking permission checks. UIDs 2901/2902 support outbound and
loopback traffic but direct Wi-Fi inbound traffic to UID 2901 also failed; the
UID 2000 TCP proxy fixes that without sharing the secondary owner's identity
with Hermes. Verify unused system-range IDs and inbound behavior when adapting
to another device. Primary ext4 default ACLs explicitly grant UIDs
2000, 2901 and 2902. Secondary's parent permits only UID 2901 to traverse it.
Android's global SELinux mode remains Enforcing, with the existing userdebug
permissive `su` domain for this stack; these are not confined SELinux services.

Hermes has read-only mounts for the CLI and socket directory. It has no manual
file-server password, secondary path, or Docker socket. The owner can always
change Docker/host configuration; isolation is from ordinary containers, not
from the root administrator.

Kela's container creation API accepts named volumes only. Host bind mounts must
be configured explicitly through owner-managed Compose, preventing host-root,
primary-path and secondary-path binds through the app. Reserved `kela-primary`
requires an approved container name. The default grant is `phone-hermes`;
root-only `/etc/kela/storage-grants.json` can override it, for example:

```json
{"kela-primary": ["phone-hermes", "another-approved-container"]}
```

Granting a container also requires an explicit Compose mount and matching primary
ACL for its runtime UID. Never grant secondary. Kela cannot delete reserved
bucket volumes. Existing Compose mounts are unaffected by this API policy.

## Provisioning

These are provisioning instructions for the existing Debian/Android layout,
not a partitioning or backup installer. Stop any bucket writers before changing
mounts. `create-primary.py` refuses an existing image or nonempty old bucket;
migrate existing data deliberately rather than bypassing those checks.

1. In Debian, install `aria2 acl openssl` with apt. Copy the Python files from
   `optional/storage` to `/opt/kela-storage`. Install Android
   `mount-storage.sh`, `start-storage.sh`, `stop-storage.sh` at
   `/data/local/server`, mode 0700, and use the matching `android/start.sh`.
2. Fetch the [official copyparty v1.20.26 SFX](https://github.com/9001/copyparty/releases/download/v1.20.26/copyparty-sfx.py)
   into `/opt/kela-storage/copyparty-sfx.py`. Verify SHA256
   `8f9a0def8a9c15252a06395781ec083372043b60caa80fb33c3d6dafa7f1b40a`.
   `provision.py` also verifies this digest. Do not start copyparty without its
   private configuration: upstream defaults permit anonymous writes.
3. Run Debian `python3 /opt/kela-storage/create-primary.py` once, then Android
   `/data/local/server/mount-storage.sh`. This formats only a new image file;
   it does not format a phone partition. The mount uses nosuid/nodev/noexec.
4. Run Debian `python3 /opt/kela-storage/provision.py`. It creates private service
   state, inherited ACLs, a random file-server password and self-signed TLS cert.
   Save `/etc/kela-storage/file-server-login.txt` privately and distribute
   `/var/lib/kela-files/server.crt` to clients after verifying its fingerprint.
   Private keys/configuration must never enter Git or Hermes. The cert includes
   the Wi-Fi address at provisioning; if DHCP changes, renew its SAN or use a
   stable local hostname/DHCP reservation.
5. Run Android `/data/local/server/start-storage.sh`. Wait for the socket and
   HTTPS listener. In Debian, create the global volume:

   ```sh
   docker volume create --driver local --opt type=none --opt o=bind \
     --opt device=/srv/bucket kela-primary
   ```

6. Put `bucketctl.py` alone in `/opt/kela-storage/tools`, readable by Hermes.
   Copy `SKILL.md` into Hermes `/opt/hermes/data/skills/primary-downloads/SKILL.md`,
   owned by 2000:3003. Apply `hermes-storage.yaml` alongside the Hermes Compose
   file, or merge its volumes into the persistent base file. Ensure the boot
   command uses that same configuration. Recreate only Hermes.
7. After verification, create `/opt/kela-storage/.configured` in Debian. Boot
   startup then requires the bounded primary mount before bringing up the stack,
   starts the native storage supervisor, and starts Hermes. A missing/wrong
   primary fails closed. The visible loop backing file is checked directly
   because this Android chroot can report stacked mounts in `findmnt`.

Use `python3 /opt/bucket-tools/bucketctl.py add 'LINK'` inside Hermes, then `list`
or `status ID`. Downloads continue between conversations. `remove ID` cancels a
job without deleting partial files. Ordinary links are supported; authenticated
sites/cookies and private-tracker workflows are outside the initial API.

Aria2 stores its queue/session in `/var/lib/kela-downloads/session.txt`; unfinished
downloads survive a native service restart. Torrents stop seeding at completion.
The supervisor's logs are owner-only under `/var/log/kela-storage`. Stop with
Android `/data/local/server/stop-storage.sh` before maintenance; phone startup
can restart services, so also stop/gate native init for longer maintenance.

## Validation

```sh
python3 -m unittest discover -s server
python3 -m unittest discover -s optional/storage
```

Live checks on merlinx verified Hermes UID 2000 primary reads/writes and socket
access; no secondary mounts in any container; native downloader denied secondary;
unauthenticated file read denied; authenticated upload/download; read-only offline
secondary; a public Debian HTTP download; and a deterministic BitTorrent transfer
from a temporary local tracker/seeder with content hash verification. A write
exactly beyond the 90 GB loop-device boundary returned ENOSPC without filling the
phone. A saved paused job survived native service shutdown/restart, was resumed
through the Hermes CLI, and completed; uploaded data also survived. Re-running
the Android startup script succeeded without recreating existing containers.
An external PC on Wi-Fi also verified the TLS certificate, authenticated listing,
upload and file readback through the native TCP proxy. Hermes' container network
was denied that LAN endpoint before authentication.
This feature was added after the original ROM boot tests; no new phone reboot
test was performed, and the storage deployment is not in the published OS images.
