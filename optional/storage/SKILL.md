---
name: primary-downloads
description: Download HTTP links, magnets, and torrent files into the phone primary bucket and check their progress.
---

Use the terminal tool to run `python3 /opt/bucket-tools/bucketctl.py`.

Commands:

```
python3 /opt/bucket-tools/bucketctl.py space
python3 /opt/bucket-tools/bucketctl.py add 'https://example.org/file.zip'
python3 /opt/bucket-tools/bucketctl.py add 'magnet:?xt=urn:btih:...' --folder Downloads/example
python3 /opt/bucket-tools/bucketctl.py torrent 'Downloads/example.torrent'
python3 /opt/bucket-tools/bucketctl.py list
python3 /opt/bucket-tools/bucketctl.py status DOWNLOAD_ID
python3 /opt/bucket-tools/bucketctl.py pause DOWNLOAD_ID
python3 /opt/bucket-tools/bucketctl.py resume DOWNLOAD_ID
python3 /opt/bucket-tools/bucketctl.py remove DOWNLOAD_ID
```

The primary bucket is mounted at `/buckets/primary`. Folder and torrent arguments
are relative to that bucket. Downloads continue without an active conversation.
The hard image cap is 90 GB (decimal); usable file space is slightly smaller.
Check space before large jobs and report failures accurately. `remove` cancels a
job and retains partial files; ask before deleting files. Never promise completion
until status reports complete. For gated links, cookies, or private trackers,
explain that this initial API supports ordinary public HTTP(S), magnets and torrents.

The authenticated manual file server exposes `/primary` over the LAN. Credentials
are held by the owner, not by Hermes. Secondary USB storage is for manual use only
and is never available to this container. Do not try to bypass this restriction.
