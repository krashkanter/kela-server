# Kela Server

Requirements:

- ARM64 LineageOS userdebug with rooted ADB and a container-enabled kernel
- Debian chroot at `/data/local/debian`, Python 3, Docker Engine and Compose
- `/data/local/server/debian` chroot wrapper

```sh
python3 -m unittest discover -s server
```

[Setup and runtime paths](docs/SETUP.md) · [Credits](CREDITS.md) · [Kela Android app](https://github.com/krashkanter/kela) · [DroidUtils](https://github.com/krashkanter/droidutils) · [merlinx images](https://github.com/krashkanter/merlinx-os-releases/tree/lineage-24-server)
