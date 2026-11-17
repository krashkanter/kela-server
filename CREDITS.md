# Credits

- Kela's authenticated Docker bridge and integration scripts were developed in [krashkanter/kela](https://github.com/krashkanter/kela). This repository publishes that backend and the existing phone server configuration separately; the app retains its bundled bridge for installer compatibility.
- Device support and the kernel come from [LineageOS](https://lineageos.org/), its merlinx/MT6768 maintainers, and their Linux, Xiaomi, MediaTek and other upstream contributors. The [image release credits](https://github.com/krashkanter/merlinx-os-releases/blob/lineage-24-server/CREDITS.md) record exact source revisions and tools.
- The Linux userspace is [Debian](https://www.debian.org/). Deployment templates reference [Docker](https://github.com/docker), [nginx](https://nginx.org/) and optional [Cloudflare cloudflared](https://github.com/cloudflare/cloudflared) images. Their implementations and authorship remain upstream.
- The optional agent is [NousResearch/hermes-agent](https://github.com/NousResearch/hermes-agent), v0.23.2, pinned by official image digest. This repository contains deployment templates, not a fork of Hermes.
- The Android root-control daemon is [DroidUtils](https://github.com/krashkanter/droidutils); runtime paths retain the historical sysutils name.

Original source notices and licenses remain applicable. These credits do not imply upstream endorsement.
