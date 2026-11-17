import os,subprocess
from pathlib import Path
p=Path('/var/lib/kela-storage'); p.mkdir(mode=0o700,parents=True,exist_ok=True)
f=p/'primary.ext4'
assert not f.exists(), 'Image already exists; refusing to recreate'
assert not list(Path('/srv/bucket').iterdir()), 'Existing bucket data needs migration'
with f.open('xb') as stream: stream.truncate(90000000000)
os.chmod(f,0o600)
subprocess.run(['mkfs.ext4','-q','-F','-L','kela-primary','-m','0','-i','262144','-E','lazy_itable_init=1,lazy_journal_init=1',str(f)],check=True)
print('Created sparse primary filesystem; image bytes:',f.stat().st_size,'allocated bytes:',f.stat().st_blocks*512)
