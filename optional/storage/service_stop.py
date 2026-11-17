#!/usr/bin/env python3
import fcntl
import os
import signal
import time
from pathlib import Path

base = Path('/var/log/kela-storage')
p = base/'supervisor.pid'
if p.exists():
    pid = int(p.read_text())
    cmd = Path('/proc/%s/cmdline' % pid)
    if cmd.exists() and b'/opt/kela-storage/supervise.py' in cmd.read_bytes():
        os.kill(pid, signal.SIGTERM)
        with (base/'supervisor.lock').open('a') as lock:
            for _ in range(300):
                try:
                    fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
                    break
                except BlockingIOError:
                    time.sleep(.1)
            else:
                raise SystemExit('Storage services did not stop within 30 seconds')
