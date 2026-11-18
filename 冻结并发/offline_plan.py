"""Offline, curve-driven XZ interruption plan. No live admission controller.

Historical charge envelopes are predictions, not hard allocation guarantees.
Frozen charge persists and foreground release requires a real exit at runtime.
"""
import argparse,bisect,csv,hashlib,json,math,subprocess
from pathlib import Path
from independent_plan import load_profiles,align,envelope,save,sha
from segmented_scheduler import Curve

GIB=2**30
DEFAULT=dict(step_s=.5,start_step_s=2.,foreground_jitter_s=60.,background_jitter_s=2.,
             background_speed_upper=1.25,reaction_s=2.5,minimum_early_s=2.,
             maximum_early_s=300.,early_finish_lead_s=60.,profile_multiplier=1.05,
             admission_headroom_bytes=64*1024**2,model_error_bytes=32*1024**2)

def calibration(root):
    root=Path(root);s=json.loads((root/'summary.json').read_text());v=json.loads((root/'validation.json').read_text())
    if not v['success'] or s['status']!='EXECUTED':raise ValueError('calibration must be a completed successful run')
    rows={op:[] for op in ['foreground_krita','xz']}
    with (root/'task_memory.csv').open() as f:
        for row in csv.DictReader(f):
            op=row['operation']
            if op not in rows:continue
            r=s['tasks'][op];origin=s['T0_monotonic_ns'] if op=='foreground_krita' else r['actual_start_ns']
            stamp=int(row['monotonic_ns'])
            if origin<=stamp<=r['empty_confirmed_ns']:rows[op].append(((stamp-origin)/1e9,int(row['memory_current_bytes'])))
    models={}
    for op,points in rows.items():
        if not points:raise ValueError('empty calibration '+op)
        models[op]=envelope(points,points[-1][0],points[-1][1])
    # Match the system sample to the following foreground field group within
    # the recorded 20ms bracket; retain correlation with desktop/cache pressure.
    fg=rows['foreground_krita'];times=[t for t,v in fg];pressure=[]
    with (root/'system_memory.csv').open() as f:
        for row in csv.DictReader(f):
            t=(int(row['monotonic_ns'])-s['T0_monotonic_ns'])/1e9;i=bisect.bisect_left(times,t)
            if i>=len(fg) or abs(times[i]-t)>.02:continue
            used=int(row['mem_total_bytes'])-int(row['mem_available_bytes'])
            pressure.append((t,used+math.ceil(fg[i][1]*.05)))
    if not pressure:raise ValueError('missing aligned foreground/system calibration')
    models['foreground_system']=envelope(pressure,pressure[-1][0],pressure[-1][1],factor=1.)
    return dict(schema='oomlab-offline-calibration-v1',source=str(root),models=models,
                original_run_total_s=v['total_from_first_launch_s'],
                foreground_homepage_end_s=(s['tasks']['foreground_krita']['empty_confirmed_ns']-s['T0_monotonic_ns'])/1e9,
                xz_duration_s=s['tasks']['xz']['execution_wall_s'],
                hashes={name:sha(root/name) for name in ['summary.json','validation.json','task_memory.csv','system_memory.csv']})

def independent_system(profiles,meta):
    shift=(meta['foreground']['import_ns']-meta['foreground']['homepage_ns'])/1e9;points=[]
    with (Path(profiles)/'foreground.csv').open() as f:
        for r in csv.DictReader(f):
            if not r['system_available_bytes']:continue
            t=float(r['t_since_import_s'])+shift
            if t>=0:points.append((t,meta['foreground']['memtotal_bytes']-int(r['system_available_bytes'])+math.ceil(int(r['memory_current_bytes'])*.05)))
    return envelope(points,points[-1][0],points[-1][1],factor=1.)

def combine(models,extra,foreground=False,step=.5):
    curves=[Curve(m) for m in [models,extra]];duration=max(c.duration for c in curves)
    # A profile endpoint containing zero does not release a living foreground.
    tails=[c.maximum(max(0,c.duration-60),c.duration) if foreground else c.peak for c in curves]
    points=[]
    for i in range(math.ceil(duration/step)+1):
        t=i*step;value=max(c.value(t) if t<c.duration else tails[k] for k,c in enumerate(curves))
        if not points or value!=points[-1][1]:points.append([round(t*1000),value])
    end=math.ceil(duration/step)*step
    if points[-1][0]!=round(end*1000):points.append([round(end*1000),points[-1][1]])
    return dict(curve=points,duration_ms=round(end*1000),peak_bytes=max(v for _,v in points),terminal_bytes=points[-1][1])

def vectors(fg,xz,c):
    step=c['step_s'];end=fg.duration+c['foreground_jitter_s'];n=math.ceil(end/step)+1
    f=[fg.maximum(max(0,i*step-c['foreground_jitter_s']),min(fg.duration,i*step+c['foreground_jitter_s'])) for i in range(n)]
    suffix=f[:]
    for i in range(len(suffix)-2,-1,-1):suffix[i]=max(suffix[i],suffix[i+1])
    return f,suffix

def held_bound(xz,active,c):
    upper=(active+c['reaction_s'])*c['background_speed_upper']+c['background_jitter_s']
    return xz.maximum(0,min(xz.duration,upper))+c['model_error_bytes']

def candidate(fg,xz,start,duration,capacity,c,arrays=None):
    f,suffix=arrays or vectors(fg,xz,c);step=c['step_s'];held=held_bound(xz,duration,c)
    stop=start+duration;index=min(len(f)-1,math.floor(stop/step));peak=held+suffix[index]
    if peak>capacity:return None
    for i in range(math.ceil(duration/step)+1):
        age=min(duration,i*step);j=min(len(f)-1,math.floor((start+age)/step))
        peak=max(peak,f[j]+held_bound(xz,age,c))
        if peak>capacity:return None
    return dict(start_s=start,freeze_request_s=stop,active_s=duration,held_upper_bytes=held,
                max_foreground_plus_xz_bytes=peak,minimum_model_headroom_bytes=capacity-peak)

def search(fg_model,xz_model,not_before,memtotal,base,reserve,waiting,c):
    fg=Curve(fg_model);xz=Curve(xz_model);arrays=vectors(fg,xz,c)
    # Extra admission headroom only applies while early XZ pages are resident.
    overhead=base+reserve+3*waiting+c['admission_headroom_bytes']+c['model_error_bytes']
    capacity=memtotal-overhead;cutoff=fg.duration-c['early_finish_lead_s']
    first=math.ceil(not_before/c['start_step_s'])*c['start_step_s'];best=None;checked=0
    for k in range(max(0,math.floor((cutoff-first)/c['start_step_s'])+1)):
        start=first+k*c['start_step_s'];lo=0;hi=math.floor(min(c['maximum_early_s'],cutoff-start)/c['step_s'])
        while lo<hi:
            mid=(lo+hi+1)//2;checked+=1
            if candidate(fg,xz,start,mid*c['step_s'],capacity,c,arrays):lo=mid
            else:hi=mid-1
        if lo*c['step_s']<c['minimum_early_s']:continue
        row=candidate(fg,xz,start,lo*c['step_s'],capacity,c,arrays)
        if best is None or (row['active_s'],-row['start_s'])>(best['active_s'],-best['start_s']):best=row
    return dict(selected=best,candidates_checked=checked,capacity_bytes=capacity,overhead_bytes=overhead,
                foreground_alone_peak_reserved_bytes=base+reserve+3*waiting+max(arrays[0]),
                search_scope='one early execution interval, then hold until real foreground exit; finite grid, not global optimality')

def continuation(models,memtotal,base,reserve,waiting,binary,out):
    # Actual foreground exit is a symbolic barrier, not a guessed wall time.
    # Reserve the entire calibrated XZ peak while Oracle places Table/Array.
    xz_peak=models['xz']['peak_bytes'];lines=['memshift-oracle-v1','slot_ms 500','safe_bytes '+str(memtotal),
        'budget_semantics available_headroom_proxy','max_wall_ms 10000','max_nodes 1000000',
        'base 0 '+str(base+3*waiting),'error 0 '+str(reserve),'foreground 0 '+str(xz_peak)]
    for op in ['table','array']:
        m=models[op];lines.append('job %s %d 0 1800000 1 100 0 0 incremental'%(op,m['duration_ms']))
        lines+=['point %s %d %d'%(op,t,v) for t,v in m['curve']]
    p=Path(out);p.mkdir(parents=True,exist_ok=True);(p/'continuation_input.tsv').write_text('\n'.join(lines)+'\n')
    result=subprocess.run([str(binary),'--input',str(p/'continuation_input.tsv'),'--ledger',str(p/'continuation_ledger.tsv')],capture_output=True,text=True)
    if result.returncode not in [0,2]:raise RuntimeError(result.stderr)
    native=json.loads(result.stdout)
    if not native['feasible']:raise ValueError('continuation infeasible '+native['status'])
    save(p/'continuation_native.json',native)
    return dict(native=native,release_after_foreground_exit_s={r['id']:r['release_after_ms']/1000 for r in native['jobs']},
                xz_reserved_peak_bytes=xz_peak,base_including_waiting_bytes=base+3*waiting,
                native_binary_sha256=sha(binary),anchor='actual foreground cgroup empty confirmation')

def make_plan(profiles,bundle,out,memtotal,live_pressure=0,binary=None,config=None):
    c=dict(DEFAULT,**(config or {}));raw,original,meta=load_profiles(profiles);alignment=align(raw,meta)
    bundle=json.loads(Path(bundle).read_text()) if isinstance(bundle,(str,Path)) else bundle
    models=dict(original)
    for op in ['foreground_krita','xz']:models[op]=combine(original[op],bundle['models'][op],op=='foreground_krita',c['step_s'])
    models['foreground_system']=combine(independent_system(profiles,meta),bundle['models']['foreground_system'],True,c['step_s'])
    base=max(live_pressure,meta['base_pressure_p95_bytes']);reserve=math.ceil(memtotal*.116);waiting=16*1024**2
    system_adjustment=max(0,live_pressure-models['foreground_system']['curve'][0][1])
    result=search(models['foreground_system'],models['xz'],alignment['offsets_s']['xz'],memtotal,system_adjustment,reserve,waiting,c)
    if not result['selected']:raise ValueError('No safe early interval on configured conservative curve grid')
    row=result['selected'];early=row['active_s'];old=bundle['original_run_total_s']
    plan=dict(schema='oomlab-curve-offline-v1',policy='offline_curve_plan_with_runtime_veto_only',config=c,
        alignment=alignment,models=models,original_models=original,calibration=bundle,search=result,
        budget=dict(memtotal_bytes=memtotal,base_pressure_bytes=base,reserve_bytes=reserve,waiting_per_task_bytes=waiting,
                    early_system_adjustment_bytes=system_adjustment,
                    early_accounting='historical foreground-alone system pressure + 5% foreground charge + XZ retained charge; system base is already included, not added twice'),
        schedule=[dict(operation='xz',action='submit_frozen',homepage_s=alignment['offsets_s']['xz']),
                  dict(operation='xz',action='resume',homepage_s=row['start_s']),
                  dict(operation='xz',action='freeze',homepage_s=row['freeze_request_s']),
                  dict(operation='xz',action='resume',barrier='actual_foreground_exit')],
        prediction=dict(early_active_s=early,reference_total_s=old,estimated_total_s=old-early+.5,
                        estimated_saving_s=early-.5,assumptions='same task execution rates and one extra freeze/resume overhead estimated at 0.5s; not a measured speedup'),
        limitations=['Historical envelopes are not hard allocation bounds','One successful calibration run; no cache causality claim',
                     'No foreground release credit before confirmed exit','Frozen XZ held charge persists throughout the remaining foreground',
                     'No periodic lease selection, pressure classification or fairness rotation'])
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    if binary:plan['continuation']=continuation(models,memtotal,base,reserve,waiting,binary,out)
    save(out/'offline_plan.json',plan)
    with (out/'early_budget.csv').open('w',newline='') as f:
        w=csv.writer(f);w.writerow(['homepage_s','foreground_system_upper_bytes','xz_upper_bytes','reserved_bytes','budget_bytes'])
        fg=Curve(models['foreground_system']);xz=Curve(models['xz']);fv,_=vectors(fg,xz,c)
        for i,fg_bytes in enumerate(fv):
            t=i*c['step_s'];xz_bytes=0 if t<row['start_s'] else held_bound(xz,min(early,max(0,t-row['start_s'])),c)
            overhead=system_adjustment+reserve+3*waiting+(c['admission_headroom_bytes']+c['model_error_bytes'] if t>=row['start_s'] else 0)
            w.writerow([t,fg_bytes,xz_bytes,overhead+fg_bytes+xz_bytes,memtotal])
    return plan

if __name__=='__main__':
    p=argparse.ArgumentParser();p.add_argument('--profiles',required=True);p.add_argument('--calibration');p.add_argument('--make-calibration');p.add_argument('--output',required=True);p.add_argument('--memtotal',type=int);p.add_argument('--planner');a=p.parse_args()
    if a.make_calibration:save(a.output,calibration(a.make_calibration))
    else:
        x=make_plan(a.profiles,a.calibration,a.output,a.memtotal,binary=a.planner)
        print(json.dumps(dict(selected=x['search']['selected'],prediction=x['prediction'],budget=x['budget']),indent=2))
