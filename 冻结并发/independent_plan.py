"""Explicit independent-prior mode. Never labels these curves concurrent data."""
import bisect,csv,hashlib,json,math,subprocess
from pathlib import Path

OPS=('xz','table','array')
GIB=2**30

def save(path,value):Path(path).write_text(json.dumps(value,indent=2,ensure_ascii=False))
def sha(path):return hashlib.sha256(Path(path).read_bytes()).hexdigest()

def value(curve,t):
    if t<curve[0][0]-1e-7 or t>curve[-1][0]+1e-7:return None
    t=min(curve[-1][0],max(curve[0][0],t))
    at=bisect.bisect_right(curve,(t,float('inf')))-1
    if at==len(curve)-1:return curve[at][1]
    a,b=curve[at:at+2]
    return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0])

def envelope(curve,duration,terminal,tail_bound=None,factor=1.05):
    """500 ms upper envelope; unobserved tail is a labelled conservative bound."""
    bins={}
    for t,b in curve:
        if t>=0:bins.setdefault(int(t*2),[]).append(b)
    result=[];last=curve[0][1]
    end=math.ceil(duration*2)*500
    for ms in range(0,end,500):
        vals=bins.get(ms//500,[])
        # Include both interval endpoints; observed samples bound sampled data only.
        vals+= [v for v in [value(curve,ms/1000),value(curve,(ms+500)/1000)] if v is not None]
        if ms/1000>curve[-1][0]:vals=[tail_bound if tail_bound is not None else last]
        v=math.ceil(max(vals or [last])*factor);last=v/factor
        if not result or v!=result[-1][1]:result.append([ms,v])
    result.append([end,math.ceil(terminal*factor)])
    return dict(duration_ms=end,curve=result,peak_bytes=max(v for _,v in result),terminal_bytes=result[-1][1],reference_level_scale=factor)

def load_profiles(folder):
    folder=Path(folder);meta=json.loads((folder/'provenance.json').read_text());curves={};models={}
    for name,d in meta['files'].items():
        if sha(folder/name)!=d['sha256']:raise ValueError('profile changed: '+name)
    shift=(meta['foreground']['import_ns']-meta['foreground']['homepage_ns'])/1e9
    with (folder/'foreground.csv').open() as f:
        rows=list(csv.DictReader(f))
    raw=sorted((float(r['t_since_import_s'])+shift,float(r['memory_current_bytes'])) for r in rows)
    curves['foreground_krita']=[(0,value(raw,0)),*[(t,v) for t,v in raw if t>0]]
    fg=curves['foreground_krita'];models['foreground_krita']=envelope(fg,fg[-1][0],fg[-1][1])
    residuals=sorted(max(0,meta['foreground']['memtotal_bytes']-int(r['system_available_bytes'])-int(r['memory_current_bytes'])) for r in rows if r['system_available_bytes'])
    meta['base_pressure_p95_bytes']=residuals[int(.95*(len(residuals)-1))]
    for op in OPS:
        info=meta['backgrounds'][op]
        with (folder/(op+'.csv')).open() as f:
            rows=[r for r in csv.DictReader(f) if r['memory_current_mean'] and int(r['memory_current_n'])==info['valid_rounds']]
        curve=sorted((float(r['relative_s']),float(r['memory_current_mean'])) for r in rows)
        curves[op]=curve
        models[op]=envelope(curve,max(info['durations_s']),max(info['terminal_observed_bytes']),tail_bound=info['max_observed_peak_bytes'])
        models[op]['tail_policy']='after all-round common coverage, observed per-round maximum bounds unknown shape until latest observed finish; terminal is maximum observed final charge'
    return curves,models,meta

def align(curves,meta):
    fg=curves['foreground_krita'];target=max(fg,key=lambda p:p[1])[0]
    offsets={op:round(target-max(c,key=lambda p:p[1])[0],2) for op,c in curves.items()};offsets['foreground_krita']=0
    # Keep the previous measured short XZ lifetime as an explicit alignment guard.
    age_limit=min(687.446845,*meta['backgrounds']['xz']['durations_s'])-30
    age=max((p for p in curves['xz'] if p[0]<=age_limit),key=lambda p:p[1])[0]
    offsets['xz']=round(target-age,2)
    lo=max(curves[op][0][0]+offsets[op] for op in curves);hi=min(curves[op][-1][0]+offsets[op] for op in curves)
    knots=sorted({t+offsets[op] for op,c in curves.items() for t,_ in c if lo<=t+offsets[op]<=hi}|{lo,hi})
    peak=max((dict(t_s=t,contributions_bytes={op:value(c,t-offsets[op]) for op,c in curves.items()}) for t in knots),key=lambda r:sum(r['contributions_bytes'].values()))
    peak['total_bytes']=sum(peak['contributions_bytes'].values())
    return dict(offsets_s=offsets,target_s=target,theoretical_peak=peak,theoretical_peak_GiB=peak['total_bytes']/GIB,
        xz_guard=dict(short_previous_actual_duration_s=687.446845,selected_age_s=age,guard_s=687.446845-age),
        caveat='Independent sampled charge superposition, not measured physical RAM and not a new OOM baseline.')

def plan(folder,out,binary,memtotal,live_pressure,reserve_fraction=.116):
    out=Path(out);out.mkdir(parents=True,exist_ok=True)
    curves,models,meta=load_profiles(folder);alignment=align(curves,meta)
    reserve=math.ceil(memtotal*reserve_fraction);base=max(live_pressure,meta['base_pressure_p95_bytes']);waiting=16*1024**2
    lines=['memshift-oracle-v1','slot_ms 500','safe_bytes '+str(memtotal),'budget_semantics available_headroom_proxy',
        'max_wall_ms 10000','max_nodes 1000000','base 0 '+str(base),'error 0 '+str(reserve)]
    lines+=['foreground %d %d'%tuple(p) for p in models['foreground_krita']['curve']]
    for op in OPS:
        m=models[op];not_before=math.ceil(alignment['offsets_s'][op]*2)*500
        lines.append('job %s %d %d 1800000 1 100 0 %d incremental'%(op,m['duration_ms'],not_before,waiting))
        lines+=['point %s %d %d'%(op,t,v) for t,v in m['curve']]
    input_path=out/'native_input.tsv';input_path.write_text('\n'.join(lines)+'\n')
    p=subprocess.run([str(binary),'--input',str(input_path),'--ledger',str(out/'native_ledger.tsv')],capture_output=True,text=True)
    if p.returncode not in (0,2):raise RuntimeError('native planner: '+p.stderr)
    native=json.loads(p.stdout);save(out/'native_plan.json',native)
    record=dict(schema='oomlab-independent-freezer-v1',source_kind='MEASURED_INDEPENDENT_PRIOR',formal_concurrent_profile=False,
        alignment=alignment,models=models,provenance=meta,native=native,native_binary_sha256=sha(binary),
        budget=dict(memtotal_bytes=memtotal,base_pressure_bytes=base,reserve_bytes=reserve,waiting_per_task_bytes=waiting,profile_multiplier=1.05,
                    semantics='available-headroom proxy with conservative charge demand; not a physical-memory guarantee'),
        planned_release_s={j['id']:j['release_after_ms']/1000 for j in native['jobs']},
        planned_freeze_s={j['id']:j['release_after_ms']/1000-alignment['offsets_s'][j['id']] for j in native['jobs']},
        runtime_policy='earliest native release plus live reserve/future-growth admission; frozen charge remains counted; bounded waiting')
    save(out/'plan.json',record)
    if not native['feasible']:raise RuntimeError('native independent prior plan '+native['status'])
    return record
