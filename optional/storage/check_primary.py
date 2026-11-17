#!/usr/bin/env python3
"""Validate the filesystem actually visible at the bucket, despite stacked binds."""
import os
from pathlib import Path


def primary_ready():
    try:
        device = os.stat('/srv/bucket').st_dev
        backing = Path('/sys/dev/block/%s:%s/loop/backing_file' % (os.major(device), os.minor(device))).read_text().strip()
        return backing in ('/var/lib/kela-storage/primary.ext4',
            '/data/local/debian/var/lib/kela-storage/primary.ext4') and Path('/var/lib/kela-storage/primary.ext4').stat().st_size == 90000000000
    except OSError:
        return False


if __name__ == '__main__':
    raise SystemExit(0 if primary_ready() else 1)
