#!/usr/bin/env python3
"""Hermes client. Unix socket is its only download-service credential."""
import argparse
import json
import socket
import sys

p = argparse.ArgumentParser(description='Manage downloads in the global primary bucket')
s = p.add_subparsers(dest='action', required=True)
for action in ['space', 'list']:
    s.add_parser(action)
for action in ['status', 'pause', 'resume', 'remove']:
    s.add_parser(action).add_argument('gid')
for action, argument in [('add', 'url'), ('torrent', 'path')]:
    cmd = s.add_parser(action)
    cmd.add_argument(argument)
    cmd.add_argument('--folder', default='Downloads', help='Relative folder within primary')
args = vars(p.parse_args())
try:
    with socket.socket(socket.AF_UNIX) as connection:
        connection.settimeout(30)
        connection.connect('/run/kela-downloads/control.sock')
        connection.sendall(json.dumps(args).encode()+b'\n')
        with connection.makefile('rb') as stream:
            result = json.loads(stream.readline(1024*1024))
    print(json.dumps(result, indent=2))
    sys.exit(0 if result.get('ok') else 1)
except Exception as e:
    print('Download service unavailable: '+type(e).__name__, file=sys.stderr)
    sys.exit(1)
