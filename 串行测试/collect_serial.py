"""Download completed serial evidence; retain large task outputs on Ubuntu."""
import argparse
import base64
import hashlib
import io
import json
from pathlib import Path
import sys
import tarfile

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / '实验工具/baseline_b_9000'))
from remote import ssh

SCRIPT = r'''
import base64,hashlib,io,json,tarfile
from pathlib import Path
h=Path.home(); latest=RECEIPT or json.loads((h/'oom_lab/config/SERIAL_LATEST.json').read_text())
root=Path(latest['output']); source=Path(latest['source'])
assert (root/'report.md').exists(), 'post-run review is not complete'
excluded=[]; buf=io.BytesIO()
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
    for path in sorted(root.rglob('*')):
        if not path.is_file():continue
        if path.name in {'compressed.xz','user_category.csv'}:
            digest=hashlib.sha256()
            with path.open('rb') as f:
                for block in iter(lambda:f.read(1048576),b''):digest.update(block)
            excluded.append(dict(path=str(path),size_bytes=path.stat().st_size,
                sha256=digest.hexdigest(),
                reason='large task output retained on Ubuntu; independent output verification is in validation.json'))
            continue
        tar.add(path,arcname='results/'+str(path.relative_to(root)),recursive=False)
    for path in sorted(source.rglob('*.py')):
        if '__pycache__' not in path.parts:
            tar.add(path,arcname='source/'+str(path.relative_to(source)),recursive=False)
    info=json.dumps(dict(remote_run=str(root),remote_source=str(source),excluded=excluded),indent=2).encode()
    member=tarfile.TarInfo('EXPORT.json');member.size=len(info);tar.addfile(member,io.BytesIO(info))
print(base64.b64encode(buf.getvalue()).decode())
'''

if __name__ == '__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.receipt and not args.output:parser.error('--receipt requires an explicit --output')
    receipt=json.loads(args.receipt.read_text(encoding='utf-8')) if args.receipt else None
    reply = ssh('RECEIPT='+repr(receipt)+'\n'+SCRIPT, 180)
    if reply.returncode:
        raise RuntimeError(reply.stderr + reply.stdout[:1000])
    payload = base64.b64decode(reply.stdout.strip(), validate=True)
    target = args.output or ROOT / '实验结果/串行测试_20261109'
    target.mkdir(parents=True, exist_ok=True)
    archive = target / 'serial-evidence.tar.gz'
    with tarfile.open(fileobj=io.BytesIO(payload), mode='r:gz') as tar:
        for member in tar.getmembers():
            dest = (target / member.name).resolve()
            if not dest.is_relative_to(target.resolve()) or not member.isfile():
                raise RuntimeError('unexpected archive member: ' + member.name)
            if args.receipt and dest.exists():
                raise FileExistsError(dest)
        if args.receipt:
            with archive.open('xb') as stream:stream.write(payload)
        else:archive.write_bytes(payload)
        tar.extractall(target)
    digest = hashlib.sha256(payload).hexdigest()
    (target / 'serial-evidence.sha256').write_text(digest + '  serial-evidence.tar.gz\n')
    print(json.dumps(dict(output=str(target),archive_bytes=len(payload),sha256=digest)))
