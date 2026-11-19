"""Read only measured independent profiles; preserve means' common coverage."""
import csv,hashlib,json,time
from pathlib import Path
import numpy as np

home=Path.home();out=home/'TeamOOM/inputs/plans'/('noswap-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));out.mkdir(parents=True,exist_ok=False)
curves={};sources={};details={}
def sha(p):return hashlib.sha256(p.read_bytes()).hexdigest()
fp=home/'TeamOOM/results/foregroundB-9000-45-20261108T232216Z/foreground_curve.csv'
with fp.open() as f:
 rows=list(csv.DictReader(f))
curves['foreground_krita']=np.array([[float(r['t_s']),float(r['memory_current_bytes'])] for r in rows])
sources['foreground_krita']=dict(path=str(fp),sha256=sha(fp),n=1)
for op,name in [('xz','xz_large'),('table','table_large_v2'),('array','array_large')]:
 folder=sorted((home/'oom_results'/name).glob('*/summary.json'))[-1].parent
 meta=json.loads((folder/'summary.json').read_text());n=meta['valid_rounds'];p=folder/'mean.csv'
 with p.open() as f:
  rows=[r for r in csv.DictReader(f) if r['memory_current_mean'] and int(r['memory_current_n'])==n]
 curves[op]=np.array([[float(r['relative_s']),float(r['memory_current_mean'])] for r in rows])
 sources[op]=dict(path=str(p),sha256=sha(p),n=n,summary=str(folder/'summary.json'))
 details[op]=dict(durations=[r['duration_s'] for r in meta['runs'] if r['success']])
for op,c in curves.items():
 at=int(c[:,1].argmax());threshold=.95*c[at,1];high=c[c[:,1]>=threshold,0]
 details.setdefault(op,{}).update(peak_bytes=c[at,1],peak_t_s=c[at,0],start_s=c[0,0],end_s=c[-1,0],high95_start_s=high[0],high95_end_s=high[-1])
target=float(curves['foreground_krita'][curves['foreground_krita'][:,1].argmax(),0])
exact={op:float(target-c[c[:,1].argmax(),0]) for op,c in curves.items()};exact['foreground_krita']=0
# Guard against XZ's previously observed early completion in this same VM.
# Select the best measured charge before that actual lifetime minus 30s.
fast_xz_duration=687.446845
max_age=min(fast_xz_duration,min(details['xz']['durations']))-30
c=curves['xz'];eligible=c[c[:,0]<=max_age];xz_age=float(eligible[eligible[:,1].argmax(),0])
chosen=dict(exact);chosen['xz']=round(target-xz_age,2)
chosen={op:round(v,2) for op,v in chosen.items()}
def sample(op,t):
 c=curves[op]
 if t<c[0,0] or t>c[-1,0]:return None
 return float(np.interp(t,c[:,0],c[:,1]))
ages={op:target-chosen[op] for op in curves}
contributions={op:sample(op,age) for op,age in ages.items()}
fractions={op:contributions[op]/details[op]['peak_bytes'] for op in curves}
timeline=[]
for t in np.arange(0,float(curves['foreground_krita'][-1,0]),.05):
 vals={op:sample(op,t-chosen[op]) for op in curves}
 if all(v is not None for v in vals.values()):timeline.append(dict(t_s=float(t),**vals,total_bytes=sum(vals.values())))
lo=max(curves[op][0,0]+chosen[op] for op in curves)
hi=min(curves[op][-1,0]+chosen[op] for op in curves)
# The interpolated sum is piecewise linear, so its maximum occurs at a knot.
knots=np.unique(np.concatenate([c[:,0]+chosen[op] for op,c in curves.items()]+[np.array([target,lo,hi])]))
candidates=[]
for t in knots[(knots>=lo)&(knots<=hi)]:
 vals={op:sample(op,float(t)-chosen[op]) for op in curves}
 if all(v is not None for v in vals.values()):candidates.append(dict(t_s=float(t),**vals,total_bytes=sum(vals.values())))
peak=max(candidates,key=lambda r:r['total_bytes'])
all95=[r['t_s'] for r in timeline if all(r[op]>=.95*details[op]['peak_bytes'] for op in curves)]
record=dict(schema='independent-four-curve-overlap-v1',sources=sources,curve_details=details,
 T0='observed homepage_ready as in the new foreground independent run',
 exact_maximum_alignment_offsets_s=exact,offsets_s=chosen,target_s=target,ages_at_target_s=ages,
 contributions_at_target_bytes=contributions,fractions_at_target=fractions,
 theoretical_peak=peak,theoretical_peak_GB=peak['total_bytes']/1e9,theoretical_peak_GiB=peak['total_bytes']/2**30,
 all_four_95pct_sample_count=len(all95),all_four_95pct_first_s=min(all95) if all95 else None,all_four_95pct_last_s=max(all95) if all95 else None,
 xz_lifetime_guard=dict(previous_actual_duration_s=fast_xz_duration,chosen_age_s=xz_age,completion_guard_s=fast_xz_duration-xz_age),
 caveats=['Independent cgroup-charge superposition, not measured simultaneous physical RAM; no desktop baseline added.',
 'No extrapolation outside measured common curve coverage. Mean profiles preserve all selected rounds.',
 'No-swap runtime pressure may alter actual durations and residency. Kernel OOM evidence is required.'])
(out/'plan.json').write_text(json.dumps(record,indent=2))
with (out/'theoretical_overlap.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(peak));w.writeheader();w.writerows(timeline)
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
fig,ax=plt.subplots(figsize=(11,5.5))
for op,c in curves.items():ax.plot(c[:,0]+chosen[op],c[:,1]/2**30,label=op,lw=1.1)
ax.plot([r['t_s'] for r in timeline],[r['total_bytes']/2**30 for r in timeline],label='sum where all four are measured',color='black',lw=1.5)
ax.axvline(peak['t_s'],ls='--',color='gray');ax.set(xlabel='Seconds from homepage T0',ylabel='GiB',title=f"Independent-curve superposition: {record['theoretical_peak_GiB']:.3f} GiB (no system baseline)")
ax.legend();ax.grid(alpha=.2);fig.tight_layout();fig.savefig(out/'theoretical_overlap.png',dpi=160)
print(json.dumps(dict(output=str(out),**{k:v for k,v in record.items() if k not in ['sources','caveats']}),indent=2))
