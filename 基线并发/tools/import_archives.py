#!/usr/bin/env python3
"""Safely import the provided archive layout for offline analysis, never execute it."""
import argparse
import hashlib
import io
import json
from pathlib import Path
import stat
import tarfile
import zipfile
from analysis_paths import external_output

SELECTED={'raw.csv','samples.csv','metadata.json','phase_trace.jsonl','phase-events.jsonl','started.json','finished.json','summary.json','session.json','report.md','collector.json','kernel_start.json','kernel_oom.json','kernel_oom_raw.jsonl','mean.csv','environment.json','memory-events.jsonl','cgroup-end.json','cleanup.json'}


def put(root,name,data):
    path=(root/name).resolve()
    if not path.is_relative_to(root.resolve()):raise ValueError('unsafe archive member: '+name)
    if path.exists():
        if hashlib.sha256(path.read_bytes()).digest()!=hashlib.sha256(data).digest():raise ValueError('conflicting duplicate: '+str(path))
        return
    path.parent.mkdir(parents=True,exist_ok=True);path.write_bytes(data)


def tar_extract(raw,root):
    with tarfile.open(fileobj=io.BytesIO(raw),mode='r:*') as archive:
        for item in archive:
            if item.issym() or item.islnk():raise ValueError('archive links are not allowed')
            if not item.isfile() or Path(item.name).name not in SELECTED:continue
            if item.size>1024**3:raise ValueError('oversized raw member')
            put(root,item.name,archive.extractfile(item).read())


def main():
    a=argparse.ArgumentParser();a.add_argument('--archives',type=Path,required=True);a.add_argument('--out',type=Path,required=True);args=a.parse_args();root=external_output(args.out);inventory=[]
    for path in sorted(args.archives.rglob('*.zip')):
        name=path.name
        if name.startswith('OOM_'):
            target=root/'new_data'
        elif name=='Array_Large_10Rounds.zip':target=root/'Array_Large_10Rounds'
        elif name=='Krita_Manual_1Round.zip':target=root/'Krita_Manual_1Round'
        else:continue
        inventory.append(dict(archive=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest()))
        with zipfile.ZipFile(path) as archive:
            for item in archive.infolist():
                if stat.S_ISLNK(item.external_attr>>16):raise ValueError('archive links are not allowed')
                member=Path(item.filename)
                if member.is_absolute() or '..' in member.parts:raise ValueError('unsafe archive path')
                if item.is_dir():continue
                if item.file_size>1024**3:continue
                if item.filename.endswith('.tar.gz') and name in {'Array_Large_10Rounds.zip','Krita_Manual_1Round.zip'}:
                    put(target,item.filename,archive.read(item))
                    tar_extract(archive.read(item),target/member.parent/'extracted')
                elif member.name in SELECTED:
                    filename=item.filename
                    if 'results' in member.parts:filename=str(Path(*member.parts[member.parts.index('results'):]))
                    put(target,filename,archive.read(item))
    (root/'archive_import_manifest.json').write_text(json.dumps(inventory,ensure_ascii=False,indent=2))
    print('Imported selected data from',len(inventory),'archives into',root)


if __name__=='__main__':main()
