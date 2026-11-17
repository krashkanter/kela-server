#!/usr/bin/env python3
"""Native services; no secondary bucket is ever exposed through Docker."""
import fcntl
import ipaddress
import json
import os
import signal
import shutil
import subprocess
import sys
import time
from pathlib import Path

BASE = Path('/opt/kela-storage')
LOG = Path('/var/log/kela-storage')
RUN = Path('/run/kela-downloads')
children = {}
stopping = False


def lan():
    try:
        rows = json.loads(subprocess.check_output(['ip', '-j', '-4', 'addr', 'show', 'dev', 'wlan0']))
        for row in rows:
            for a in row.get('addr_info', []):
                if a.get('scope') == 'global':
                    return a['local'], str(ipaddress.ip_network(a['local']+'/'+str(a['prefixlen']), strict=False))
    except Exception:
        pass
    return None, None


def launch(name, uid, cmd):
    out = LOG / (name+'.log')
    if out.exists() and out.stat().st_size > 2*1024**2:
        out.replace(out.with_suffix('.previous.log'))
    stream = out.open('ab')
    os.chmod(out, 0o600)
    home = '/var/lib/kela-files' if uid == 2901 else ('/var/lib/kela-downloads' if uid == 2902 else '/')
    command = ['setpriv', '--reuid='+str(uid), '--regid=41001', '--groups=3003',
               '--inh-caps=-all', '--ambient-caps=-all', '--bounding-set=-all', '--no-new-privs',
               'env', 'HOME='+home,
               'TMPDIR=/var/lib/kela-files/tmp' if uid == 2901 else 'TMPDIR=/var/lib/kela-downloads/tmp', *cmd]
    child = subprocess.Popen(command, stdin=subprocess.DEVNULL, stdout=stream, stderr=stream,
                             cwd='/', start_new_session=True)
    stream.close()
    children[name] = child
    (LOG / 'supervisor.log').open('a').write('%s started %s pid=%s\n' % (time.time(), name, child.pid))


def stop_child(name):
    child = children.pop(name, None)
    if child and child.poll() is None:
        child.terminate()
        try:
            child.wait(timeout=20)
        except subprocess.TimeoutExpired:
            child.kill(); child.wait()


def signal_stop(*_):
    global stopping
    stopping = True


if __name__ == '__main__':
    os.umask(0o007)
    LOG.mkdir(mode=0o700, exist_ok=True, parents=True)
    lock = (LOG/'supervisor.lock').open('w')
    try:
        fcntl.flock(lock, fcntl.LOCK_EX | fcntl.LOCK_NB)
    except BlockingIOError:
        sys.exit(0)
    from check_primary import primary_ready
    if not primary_ready():
        sys.exit('Refusing to start on missing/wrong primary filesystem')
    RUN.mkdir(exist_ok=True, parents=True)
    os.chown(RUN, 2902, 41001)
    os.chmod(RUN, 0o711)
    (LOG/'supervisor.pid').write_text(str(os.getpid()))
    signal.signal(signal.SIGTERM, signal_stop)
    signal.signal(signal.SIGINT, signal_stop)
    previous_lan = None
    last_guard = 0
    while not stopping:
        for log in LOG.glob('*.log'):
            if not log.name.endswith('.previous.log') and log.stat().st_size > 2*1024**2:
                shutil.copyfile(log, log.with_suffix('.previous.log'))
                with log.open('r+b') as stream:
                    stream.truncate(0)
        for name, uid, cmd in [
            ('aria2', 2902, ['aria2c', '--conf-path=/var/lib/kela-downloads/aria2.conf']),
            ('controller', 2902, ['python3', str(BASE/'download_api.py')])]:
            if name not in children or children[name].poll() is not None:
                if name == 'controller':
                    (RUN/'control.sock').unlink(missing_ok=True)
                launch(name, uid, cmd)
                if name == 'controller':
                    for _ in range(30):
                        if (RUN/'control.sock').exists():
                            os.chown(RUN/'control.sock', 2000, 41001)
                            os.chmod(RUN/'control.sock', 0o600)
                            break
                        time.sleep(.1)
        address, network = lan()
        if (address, network) != previous_lan:
            stop_child('lan-proxy')
            previous_lan = (address, network)
        if 'files' not in children or children['files'].poll() is not None:
            launch('files', 2901, ['python3', str(BASE/'copyparty-sfx.py'),
                '-c', '/var/lib/kela-files/copyparty.conf', '-i', '127.0.0.1', '--ipa', '127.0.0.0/8',
                '-p', '8443', '--https-only', '--no-crt', '--cert', '/var/lib/kela-files/server.pem',
                '--no-thumb', '--no-mtag-ff', '--no-robots', '--no-logues', '--no-readme',
                '--no-voldump', '--no-reload', '-j', '1'])
        if address and ('lan-proxy' not in children or children['lan-proxy'].poll() is not None):
            launch('lan-proxy', 2000, ['python3', str(BASE/'lan_proxy.py'), address, network])
        if time.monotonic() - last_guard > 10:
            last_guard = time.monotonic()
            from download_api import guard_space, rpc
            try:
                guard_space()
            except ValueError:
                try:
                    rpc('pauseAll'); rpc('saveSession')
                except Exception:
                    pass
        time.sleep(2)
    # Save and stop downloads before releasing other services.
    for name in ['lan-proxy', 'controller', 'aria2', 'files']:
        stop_child(name)
    (LOG/'supervisor.pid').unlink(missing_ok=True)
