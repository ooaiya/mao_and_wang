"""Archive measured evidence after review; large generated outputs stay on VM."""
import argparse,base64,hashlib,io,json,sys,tarfile
from pathlib import Path
ROOT=Path(__file__).resolve().parents[1];sys.path.insert(0,str(ROOT/'实验工具/baseline_b_9000'))
from remote import ssh
SCRIPT='''import base64,hashlib,io,json,tarfile
from pathlib import Path
h=Path.home();v=RECEIPT or json.loads((h/'oom_lab/config/FREEZER_LATEST.json').read_text());root=Path(v['output']);source=Path(v['source'])
assert (root/'validation.json').exists() and (root/'report.md').exists(), 'review not complete'
buf=io.BytesIO();excluded=[]
with tarfile.open(fileobj=buf,mode='w:gz') as tar:
 for p in sorted(root.rglob('*')):
  if not p.is_file():continue
  if p.name in {'compressed.xz','user_category.csv'}:
   d=hashlib.sha256()
   with p.open('rb') as f:
    for block in iter(lambda:f.read(1048576),b''):d.update(block)
   excluded.append(dict(path=str(p),bytes=p.stat().st_size,sha256=d.hexdigest(),reason='verified output retained on Ubuntu'))
   continue
  tar.add(p,arcname='results/'+str(p.relative_to(root)),recursive=False)
 for p in sorted(source.rglob('*')):
  if p.is_file() and '__pycache__' not in p.parts:tar.add(p,arcname='source/'+str(p.relative_to(source)),recursive=False)
 fg=Path(v['foreground_source']) if v.get('foreground_source') else Path((h/'oom_lab/src/KRITA_TIMED_SOURCE.txt').read_text().strip())
 original=json.loads((root/'source_provenance.json').read_text())['foreground']['files']
 for rel in original:
  tar.add(fg/rel,arcname='foreground_source/'+rel,recursive=False)
 for p in (h/'bg/oomlab').glob('*.py'):tar.add(p,arcname='background_source/oomlab/'+p.name,recursive=False)
 info=json.dumps(dict(remote_run=str(root),remote_source=str(source),excluded=excluded),indent=2).encode();item=tarfile.TarInfo('EXPORT.json');item.size=len(info);tar.addfile(item,io.BytesIO(info))
print(base64.b64encode(buf.getvalue()).decode())
'''
if __name__=='__main__':
    parser=argparse.ArgumentParser()
    parser.add_argument('--receipt',type=Path)
    parser.add_argument('--output',type=Path)
    args=parser.parse_args()
    if args.receipt and not args.output:parser.error('--receipt requires --output')
    receipt=json.loads(args.receipt.read_text(encoding='utf-8')) if args.receipt else None
    reply=ssh('RECEIPT='+repr(receipt)+'\n'+SCRIPT,180)
    if reply.returncode:raise RuntimeError(reply.stderr+reply.stdout[:1000])
    data=base64.b64decode(reply.stdout.strip(),validate=True)
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:export=json.load(tar.extractfile('EXPORT.json'))
    run_name=Path(export['remote_run']).name
    if not run_name.startswith(('freezer-independent-','freezer-segmented-','freezer-curve-','freezer-serial-curve-','freezer-priority-','freezer-realtime-','baseline-raster-')) or any(c in run_name for c in ['/', '\\', ':']):raise RuntimeError('unexpected run identity')
    baseline=run_name.startswith('baseline-raster-')
    prefix='基线并发_' if baseline else '曲线规划冻结_' if run_name.startswith('freezer-curve-') else '分段冻结_' if run_name.startswith('freezer-segmented-') else '冻结并发_'
    target=args.output or ROOT/'实验结果'/(prefix+run_name)
    target.mkdir(parents=True,exist_ok=True)
    archive=target/('baseline-evidence.tar.gz' if baseline else 'freezer-evidence.tar.gz')
    with tarfile.open(fileobj=io.BytesIO(data),mode='r:gz') as tar:
        for item in tar.getmembers():
            if not item.isfile() or not (target/item.name).resolve().is_relative_to(target.resolve()):raise RuntimeError('unexpected archive member')
            if args.receipt and (target/item.name).exists():raise FileExistsError(target/item.name)
        if args.receipt:
            with archive.open('xb') as stream:stream.write(data)
        else:archive.write_bytes(data)
        tar.extractall(target)
    digest=hashlib.sha256(data).hexdigest();(target/archive.with_suffix('').with_suffix('.sha256').name).write_text(digest+'  '+archive.name+'\n')
    print(json.dumps(dict(output=str(target),bytes=len(data),sha256=digest)))
