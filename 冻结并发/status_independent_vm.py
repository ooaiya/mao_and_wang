import csv,io,json,time
from pathlib import Path
h=Path.home();latest=json.loads((h/'oom_lab/config/FREEZER_LATEST.json').read_text());r=Path(latest['output'])
if (r/'validation.json').exists():
    d=json.loads((r/'validation.json').read_text())
    keys=['success','total_from_homepage_s','total_from_first_launch_s','global_oom_kill_delta','swap_zero_all_formal_samples','system_min_available_GiB','system_pressure_peak_GiB','freezer_proofs','independent_ledger_recheck','sampling']
    result={k:d[k] for k in keys};result['tasks']={op:{k:v.get(k) for k in ['success','state','submitted_homepage_s','release_homepage_s','frozen_s','execution_wall_s','unfrozen_wall_s','effective_model_age_s','sampled_peak_GiB','actual_to_prior_peak_ratio']} for op,v in d['tasks'].items()}
    print('FINAL',json.dumps(result));raise SystemExit()
if not r.exists():print('starting');raise SystemExit()
if (r/'summary.json').exists():print('SUMMARY',(r/'summary.json').read_text()[:700])
p=r/'events.jsonl';events=[json.loads(x) for x in p.read_text().splitlines()] if p.exists() else []
ready=next((e for e in events if e['event_type']=='homepage_ready'),None)
print('elapsed_homepage_s',round((time.monotonic_ns()-ready['actual_monotonic_ns'])/1e9,1) if ready else None)
print('ended',[(e['operation'],json.loads(e['details']).get('returncode')) for e in events if e['event_type']=='task_end'])
print('freezer',[(e['event_type'],e['operation']) for e in events if e['event_type'] in ['task_submitted','freeze_confirmed','resume_confirmed']])
if events:print('last_event',events[-1]['event_type'],events[-1]['operation'],events[-1]['details'][:500])
p=r/'task_memory.csv'
if p.exists():
    with p.open() as f:header=f.readline()
    with p.open('rb') as f:f.seek(max(0,p.stat().st_size-20000));tail=f.read().decode(errors='replace').splitlines()[1:]
    rows=list(csv.DictReader(io.StringIO(header+'\n'.join(tail))))
    for op in ['foreground_krita','xz','table','array']:
        row=next((x for x in reversed(rows) if x.get('operation')==op and x.get('memory_current_bytes')),None)
        if row:print(op,round(int(row['memory_current_bytes'])/2**30,3),'GiB','frozen',row['frozen'],'populated',row['populated'])
mem={a.rstrip(':'):int(b) for a,b,*_ in (line.split() for line in Path('/proc/meminfo').read_text().splitlines())}
print('available_GiB',round(mem['MemAvailable']/1024**2,3),'swap_total_GiB',mem['SwapTotal']/1024**2)
