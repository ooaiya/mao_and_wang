import json,time,csv,io
from pathlib import Path
h=Path.home();r=Path(json.loads((h/'TeamOOM/runtime/config/SERIAL_LATEST.json').read_text())['output'])
if (r/'validation.json').exists():
    d=json.loads((r/'validation.json').read_text());print('FINAL',json.dumps(d));raise SystemExit()
es=[json.loads(x) for x in (r/'events.jsonl').read_text().splitlines()];starts=[e for e in es if e['event_type']=='task_start'];ends=[e for e in es if e['event_type']=='task_end']
current=starts[-1] if starts else None
print('completed',[(e['operation'],json.loads(e['details']).get('duration_s')) for e in ends])
if current:print('active',current['operation'],'elapsed_s',round((time.monotonic_ns()-current['actual_monotonic_ns'])/1e9,1))
if (r/'summary.json').exists():print('SUMMARY',(r/'summary.json').read_text()[:500])
p=r/'task_memory.csv'
if p.exists():
    with p.open() as f:header=f.readline()
    with p.open('rb') as f:f.seek(max(0,p.stat().st_size-24000));lines=f.read().decode(errors='replace').splitlines()[1:]
    rows=list(csv.DictReader(io.StringIO(header+'\n'.join(lines))))
    row=next((x for x in reversed(rows) if current and x['operation']==current['operation'] and x['memory_current_bytes']),None)
    if row:print('task_GiB',round(int(row['memory_current_bytes'])/2**30,3))
print('MemAvailable_GiB',round(next(int(x.split()[1])*1024/2**30 for x in Path('/proc/meminfo').read_text().splitlines() if x.startswith('MemAvailable:')),3))
if current and current['operation']=='foreground_krita':
    p=r/'foreground_krita/process.log';items=[x for x in p.read_text().splitlines() if x.startswith('@@OOM_EVENT ')]
    if items:
        e=json.loads(items[-1][len('@@OOM_EVENT '):]);print('GUI',e.get('kind'),e.get('phase'),e.get('status'))
