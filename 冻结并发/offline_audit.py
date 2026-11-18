"""Post-run independent schedule/ledger/real-progress checks."""
import csv,json,math
from pathlib import Path
from independent_plan import sha
from segmented_scheduler import Curve
from offline_plan import search

def audit(root):
    root=Path(root);p=json.loads((root/'planning/offline_plan.json').read_text());s=json.loads((root/'summary.json').read_text())
    cfg=json.loads((root/'offline_execution_config.json').read_text());b=p['budget'];c=p['config'];errors=[]
    result=search(p['models']['foreground_system'],p['models']['xz'],p['alignment']['offsets_s']['xz'],b['memtotal_bytes'],b['early_system_adjustment_bytes'],b['reserve_bytes'],b['waiting_per_task_bytes'],c)
    if result!=p['search']:errors.append('offline grid search cannot reproduce selected plan')
    with (root/'planning/early_budget.csv').open() as f:
        rows=list(csv.DictReader(f))
    for row in rows:
        if int(row['reserved_bytes'])>int(row['budget_bytes']):errors.append('early offline ledger exceeds RAM');break
    q=p['continuation'];release=q['release_after_foreground_exit_s'];native_rows=0
    with (root/'planning/continuation_ledger.tsv').open() as f:
        for row in csv.DictReader(f,delimiter='\t'):
            t=int(row['time_ms']);total=q['base_including_waiting_bytes']+b['reserve_bytes']+q['xz_reserved_peak_bytes']
            for op in ['table','array']:
                age=t/1000-release[op]
                if age>=0:total+=Curve(p['models'][op]).value(age)
            if total!=int(row['reserved_bytes']) or total>b['memtotal_bytes']:errors.append('continuation native ledger arithmetic/capacity mismatch')
            native_rows+=1
    t0=s['T0_monotonic_ns'];fg_end=s['tasks']['foreground_krita']['empty_confirmed_ns'];early=[]
    freezes=json.loads((root/'freeze_events.json').read_text())
    for e in freezes:
        if e['action']!='resume':continue
        stamp=e['requested_monotonic_ns'];elapsed=(stamp-t0)/1e9
        if e['reason']=='offline_planned_early_resume':
            early.append(e)
            if e['operation']!='xz' or not p['search']['selected']['start_s']<=elapsed<=p['search']['selected']['start_s']+cfg['release_max_lateness_s']+.05:errors.append('early thaw outside precomputed window')
            deadline=t0/1e9+p['search']['selected']['freeze_request_s']
            if abs(e['lease_until_monotonic_s']-deadline)>.000001:errors.append('fixed stop deadline differs from offline plan')
            if not e['admission']['allowed'] or e['admission']['plan_sha256']!=sha(root/'planning/offline_plan.json'):errors.append('early admission proof invalid')
        elif e['reason']=='offline_native_continuation':
            if stamp<fg_end+round(release.get(e['operation'],0)*1e9):errors.append('continuation before real foreground exit or native offset')
        else:errors.append('unrecognised thaw source '+str(e.get('reason')))
    if len(early)>1:errors.append('multiple early resumes not present in the offline plan')
    if early:
        after=[e for e in freezes if e['operation']=='xz' and e['action']=='freeze' and e['requested_monotonic_ns']>early[0]['requested_monotonic_ns']]
        deadline=t0+round(p['search']['selected']['freeze_request_s']*1e9)
        if fg_end>deadline and (not after or after[0]['confirmed_monotonic_ns']>deadline+round(c['reaction_s']*1e9)):errors.append('planned freeze not confirmed within reserved reaction window')
    proof_path=root/'progress_at_freeze.json';progress=json.loads(proof_path.read_text()) if proof_path.exists() else None
    io=[]
    if progress:
        for proc in progress['xz_processes']:
            for fd in proc['fds']:
                position=next((int(line.split(':',1)[1]) for line in fd['info'].splitlines() if line.startswith('pos:')),0)
                if fd['target'].endswith(('input.bin','compressed.xz')):io.append(dict(target=fd['target'],position_bytes=position))
    verified_progress=bool(progress and progress['foreground_alive'] and len(io)>=2 and all(x['position_bytes']>0 for x in io))
    with (root/'offline_execution.jsonl').open() as f:guards=[json.loads(line) for line in f if line.strip()]
    if not guards or any(not row['live_guard']['allowed'] for row in guards):errors.append('live reserve guard failed or evidence missing')
    return dict(errors=errors,early_ledger_rows=len(rows),continuation_ledger_rows=native_rows,guard_rows=len(guards),
                early_resume_count=len(early),real_xz_progress_while_foreground_alive=verified_progress,io_receipt=io,
                plan_prediction=p['prediction'],selected=p['search']['selected'],
                role='offline plan replay, native continuation arithmetic, fixed-window execution and real I/O receipt; not a universal OOM guarantee')
