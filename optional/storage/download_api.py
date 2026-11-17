#!/usr/bin/env python3
"""Small capability API: socket access grants downloads into the primary bucket."""
import base64
import json
import os
import re
import socket
import socketserver
import struct
from pathlib import Path
from urllib.parse import urlsplit
from urllib.request import Request, urlopen

ROOT = Path('/srv/bucket')
STATE = Path('/var/lib/kela-downloads')
SOCKET = '/run/kela-downloads/control.sock'
MAX_REQUEST = 16384
MIN_HOST_FREE = 4 * 1024**3
FIELDS = ['gid', 'status', 'totalLength', 'completedLength', 'downloadSpeed',
          'uploadSpeed', 'errorCode', 'files']


def rpc(method, *params):
    secret = (STATE / 'rpc-secret').read_text().strip()
    body = json.dumps({'jsonrpc': '2.0', 'id': 'bucket', 'method': 'aria2.' + method,
                       'params': ['token:' + secret, *params]}).encode()
    with urlopen(Request('http://127.0.0.1:6800/jsonrpc', data=body,
                         headers={'Content-Type': 'application/json'}), timeout=15) as response:
        value = json.load(response)
    if 'error' in value:
        raise ValueError('Downloader rejected request (code %s)' % value['error'].get('code'))
    return value['result']


def primary_path(value):
    if not isinstance(value, str) or len(value) > 512:
        raise ValueError('Invalid primary path')
    rel = Path(value)
    if rel.is_absolute() or '..' in rel.parts or any(p.startswith('.') for p in rel.parts):
        raise ValueError('Use a relative path without hidden components or parent traversal')
    path = (ROOT / rel).resolve()
    if path != ROOT and ROOT not in path.parents:
        raise ValueError('Path escapes primary bucket')
    return path


def guard_space():
    host = os.statvfs('/var/lib/kela-storage')
    primary = os.statvfs(ROOT)
    if host.f_bavail * host.f_frsize < MIN_HOST_FREE:
        raise ValueError('Android storage reserve reached; free space before resuming')
    if primary.f_bavail * primary.f_frsize < 64 * 1024**2:
        raise ValueError('Primary bucket is full')


def safe_status(item):
    out = {k: item[k] for k in FIELDS if k in item and k != 'files'}
    out['files'] = []
    for f in item.get('files', []):
        p = Path(f.get('path', ''))
        try:
            name = str(p.relative_to(ROOT))
        except ValueError:
            name = '(pending metadata)'
        out['files'].append({'path': name, 'length': f.get('length'),
                             'completedLength': f.get('completedLength')})
    return out


def dispatch(q):
    if not isinstance(q, dict):
        raise ValueError('Expected an object')
    action = q.get('action')
    if action == 'space':
        s = os.statvfs(ROOT)
        h = os.statvfs('/var/lib/kela-storage')
        return {'bucket': 'primary', 'image_limit_bytes': 90000000000,
                'filesystem_bytes': s.f_blocks*s.f_frsize, 'available_bytes': s.f_bavail*s.f_frsize,
                'host_available_bytes': h.f_bavail*h.f_frsize, 'secondary': 'not available to containers'}
    if action in ('add', 'torrent'):
        guard_space()
        dest = primary_path(q.get('folder', 'Downloads'))
        dest.mkdir(parents=True, exist_ok=True)
        options = {'dir': str(dest)}
        if action == 'add':
            url = q.get('url', '')
            if not isinstance(url, str) or len(url) > 12000 or any(c in url for c in '\r\n\x00'):
                raise ValueError('Invalid link')
            parsed = urlsplit(url)
            if parsed.scheme not in ('http', 'https', 'magnet'):
                raise ValueError('Only HTTP(S) and magnet links are accepted')
            if parsed.scheme != 'magnet' and (not parsed.hostname or parsed.username or parsed.password):
                raise ValueError('Use an HTTP(S) URL without embedded credentials')
            gid = rpc('addUri', [url], options)
        else:
            torrent = primary_path(q.get('path', ''))
            if not torrent.is_file() or torrent.stat().st_size > 4*1024**2 or torrent.suffix != '.torrent':
                raise ValueError('Choose a .torrent file in primary, at most 4 MiB')
            gid = rpc('addTorrent', base64.b64encode(torrent.read_bytes()).decode(), [], options)
        rpc('saveSession')
        return {'gid': gid, 'folder': str(dest.relative_to(ROOT))}
    if action == 'list':
        return [safe_status(x) for x in rpc('tellActive', FIELDS) +
                rpc('tellWaiting', 0, 100, FIELDS) + rpc('tellStopped', 0, 100, FIELDS)]
    gid = q.get('gid', '')
    if not isinstance(gid, str) or not re.fullmatch('[0-9a-f]{16}', gid):
        raise ValueError('A 16-character download ID is required')
    if action == 'status':
        return safe_status(rpc('tellStatus', gid, FIELDS))
    if action in ('pause', 'resume', 'remove'):
        if action == 'resume':
            guard_space()
        result = rpc({'pause': 'pause', 'resume': 'unpause', 'remove': 'remove'}[action], gid)
        rpc('saveSession')
        return {'gid': result, 'action': action, 'files_deleted': False}
    raise ValueError('Unknown action')


class Handler(socketserver.StreamRequestHandler):
    def handle(self):
        self.connection.settimeout(20)
        _, uid, _ = struct.unpack('3i', self.connection.getsockopt(socket.SOL_SOCKET, socket.SO_PEERCRED, 12))
        if uid not in (0, 2000):
            return
        try:
            data = self.rfile.readline(MAX_REQUEST+1)
            if len(data) > MAX_REQUEST or not data.endswith(b'\n'):
                raise ValueError('Request too large or incomplete')
            result = {'ok': True, 'result': dispatch(json.loads(data))}
        except ValueError as e:
            result = {'ok': False, 'error': str(e)}
        except Exception:
            result = {'ok': False, 'error': 'Download service unavailable; retry later'}
        self.wfile.write(json.dumps(result).encode()+b'\n')


if __name__ == '__main__':
    Path(SOCKET).unlink(missing_ok=True)
    with socketserver.UnixStreamServer(SOCKET, Handler) as server:
        os.chmod(SOCKET, 0o660)
        server.serve_forever(poll_interval=1)
