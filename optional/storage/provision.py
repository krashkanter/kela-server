#!/usr/bin/env python3
"""One-time native storage setup. Requires the mounted kela-primary filesystem."""
import hashlib
import os
import secrets
import shutil
import subprocess
from pathlib import Path

BASE = Path('/opt/kela-storage')
FILES = Path('/var/lib/kela-files')
DOWNLOADS = Path('/var/lib/kela-downloads')


def directory(p, uid, mode=0o700):
    p.mkdir(parents=True, exist_ok=True)
    os.chown(p, uid, 41001)
    os.chmod(p, mode)


def private_file(p, text, uid):
    if not p.exists():
        fd = os.open(p, os.O_WRONLY | os.O_CREAT | os.O_EXCL, 0o600)
        with os.fdopen(fd, 'w') as f:
            f.write(text)
    os.chown(p, uid, 41001)
    os.chmod(p, 0o600)


if __name__ == '__main__':
    from check_primary import primary_ready
    assert primary_ready(), 'Mount the bounded primary first'
    assert hashlib.sha256((BASE/'copyparty-sfx.py').read_bytes()).hexdigest() == '8f9a0def8a9c15252a06395781ec083372043b60caa80fb33c3d6dafa7f1b40a'
    directory(FILES,2901)
    directory(FILES/'tmp',2901)
    directory(DOWNLOADS,2902)
    directory(DOWNLOADS/'tmp',2902)
    directory(Path('/var/log/kela-storage'),0)
    directory(Path('/etc/kela-storage'),0)
    directory(Path('/run/kela-downloads'),2902,0o711)
    directory(Path('/srv/bucket'),0,0o2770)
    acl='u:2000:rwx,u:2901:rwx,u:2902:rwx,g::rwx,m::rwx,o::---'
    subprocess.run(['setfacl','-m',acl,'/srv/bucket'],check=True)
    subprocess.run(['setfacl','-d','-m','u::rwx,'+acl,'/srv/bucket'],check=True)
    Path('/srv/bucket/Downloads').mkdir(exist_ok=True)
    directory(Path('/srv/kela-secondary'),2901)
    directory(Path('/srv/kela-secondary/offline'),2901,0o500)
    private_file(Path('/srv/kela-secondary/offline/SECONDARY-OFFLINE.txt'),
        'Secondary USB NAS is not connected. This is a read-only placeholder.\n'
        'Do not save secondary data into phone internal storage.\n',2901)
    # Make the placeholder readable by its sole native owner.
    os.chmod('/srv/kela-secondary/offline/SECONDARY-OFFLINE.txt',0o400)
    secret=DOWNLOADS/'rpc-secret'
    private_file(secret,secrets.token_urlsafe(48)+'\n',2902)
    private_file(DOWNLOADS/'session.txt','',2902)
    conf='''dir=/srv/bucket/Downloads
enable-rpc=true
rpc-listen-all=false
rpc-listen-port=6800
rpc-allow-origin-all=false
rpc-secret={secret}
input-file=/var/lib/kela-downloads/session.txt
save-session=/var/lib/kela-downloads/session.txt
save-session-interval=15
force-save=true
continue=true
max-concurrent-downloads=2
max-connection-per-server=2
split=2
disk-cache=8M
file-allocation=none
allow-overwrite=false
auto-file-renaming=true
follow-torrent=false
follow-metalink=false
bt-save-metadata=true
bt-load-saved-metadata=true
bt-max-peers=30
seed-time=0
seed-ratio=0
enable-dht=true
dht-file-path=/var/lib/kela-downloads/dht.dat
dht-file-path6=/var/lib/kela-downloads/dht6.dat
bt-enable-lpd=false
enable-peer-exchange=true
listen-port=6888
dht-listen-port=6888
summary-interval=0
show-console-readout=false
console-log-level=warn
max-download-result=100
'''.format(secret=secret.read_text().strip())
    private_file(DOWNLOADS/'aria2.conf',conf,2902)
    creds=Path('/etc/kela-storage/file-server-login.txt')
    if not creds.exists():
        password=secrets.token_urlsafe(24)
        private_file(creds,'Username: admin\nPassword: '+password+'\n'
            'Address: https://PHONE_LAN_IP:8443/primary/\n'
            'Self-signed TLS certificate: verify server.crt before trusting.\n',0)
        private_file(FILES/'copyparty.conf','[global]\n  name: Kela storage\n'
            '  no-ansi\n  no-acode\n  no-dot-mv\n  no-dot-ren\n'
            '\n[accounts]\n  admin: '+password+'\n'
            '\n[/primary]\n  /srv/bucket\n  accs:\n    rwmda: admin\n'
            '\n[/secondary]\n  /srv/kela-secondary/offline\n  accs:\n    r: admin\n',2901)
    assert (FILES/'copyparty.conf').exists(), 'Missing private file-server config'
    if not (FILES/'server.pem').exists():
        from supervise import lan
        address,_=lan()
        san='DNS:kela-phone,DNS:localhost,IP:127.0.0.1'+(',IP:'+address if address else '')
        subprocess.run(['openssl','req','-x509','-newkey','ec','-pkeyopt','ec_paramgen_curve:P-256',
            '-nodes','-days','825','-subj','/CN=kela-phone','-addext','subjectAltName='+san,
            '-keyout',str(FILES/'server.key'),'-out',str(FILES/'server.crt')],check=True,capture_output=True)
        private_file(FILES/'server.pem',(FILES/'server.key').read_text()+(FILES/'server.crt').read_text(),2901)
        os.chmod(FILES/'server.key',0o600)
        (FILES/'server.key').unlink()
    print('Native storage provisioned; credentials remain in root-only /etc/kela-storage/file-server-login.txt')
