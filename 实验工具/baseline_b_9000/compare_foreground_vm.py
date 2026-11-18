"""Read-only source profiles; write comparison to a new review directory."""
import bisect,csv,hashlib,json,time
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

h=Path.home();manual=h/'oom_lab/results/foregroundB-9000-45-20261108T232216Z/foreground_curve.csv'
automatic=h/'oom_lab/reviews/timed-74747b98aa7148bbbe299f316c2a7b43/foreground_curve.csv'
shift=14.399224989;duration=1350.;curves={};sources={}
out=h/'oom_lab/reviews'/('foreground-comparison-'+time.strftime('%Y%m%dT%H%M%SZ',time.gmtime()));out.mkdir()
for key,path,tcol,offset in [('manual',manual,'t_s',shift),('auto',automatic,'t_since_import_s',0)]:
    with path.open() as f:
        rows=[]
        for r in csv.DictReader(f):
            rss=r.get('rss_bytes') or r.get('krita_rss_bytes')
            rows.append([float(r[tcol])-offset,int(r['memory_current_bytes']),int(r['anon_bytes']),int(r['file_bytes']),float(rss) if rss else np.nan])
    curves[key]=np.array(rows);sources[key]=dict(path=str(path),sha256=hashlib.sha256(path.read_bytes()).hexdigest())

def high_segments(c,threshold):
    spans=[]
    for a,b in zip(c[:-1],c[1:]):
        x=max(0.,a[0]);y=min(duration,b[0])
        if y<=x:continue
        u=np.interp(x,[a[0],b[0]],[a[1],b[1]]);v=np.interp(y,[a[0],b[0]],[a[1],b[1]])
        if u<threshold and v<threshold:continue
        if u<threshold:x=x+(threshold-u)/(v-u)*(y-x)
        elif v<threshold:y=x+(threshold-u)/(v-u)*(y-x)
        if spans and abs(spans[-1][1]-x)<1e-6:spans[-1][1]=y
        else:spans.append([float(x),float(y)])
    return dict(total_s=float(sum(b-a for a,b in spans)),longest_s=float(max((b-a for a,b in spans),default=0)),segments_s=spans)

reference_peak=max(curves['manual'][(curves['manual'][:,0]>=0)&(curves['manual'][:,0]<=duration),1]);threshold=.95*reference_peak
metrics={}
for key,c in curves.items():
    w=c[(c[:,0]>=0)&(c[:,0]<=duration)];p=w[w[:,1].argmax()];rss=w[np.isfinite(w[:,4])]
    metrics[key]=dict(charge_peak_GiB=float(p[1]/2**30),peak_t_s=float(p[0]),anon_peak_GiB=float(w[:,2].max()/2**30),
        anon_at_charge_peak_GiB=float(p[2]/2**30),file_at_charge_peak_GiB=float(p[3]/2**30),
        sampled_RSS_peak_GiB=float(rss[:,4].max()/2**30),rss_sampling_note='manual RSS is sampled about once per second; auto RSS about every 50 ms',
        last_observed_after_submit_s=float(c[-1,0]),high10=high_segments(c,10*2**30),
        high_common95=high_segments(c,threshold),high_own95=high_segments(c,.95*p[1]),high_own99=high_segments(c,.99*p[1]))
delta=dict(peak_pct=(metrics['auto']['charge_peak_GiB']/metrics['manual']['charge_peak_GiB']-1)*100,
    peak_time_s=metrics['auto']['peak_t_s']-metrics['manual']['peak_t_s'],
    high10_s=metrics['auto']['high10']['total_s']-metrics['manual']['high10']['total_s'],
    high_common95_s=metrics['auto']['high_common95']['total_s']-metrics['manual']['high_common95']['total_s'])

# Candidate releases use the same measured background profiles and guarded XZ
# age as the prior plan. This is a prediction, not a new concurrency run.
oldplan=json.loads((h/'oom_lab/plans/noswap-20261109T002744Z/plan.json').read_text());bg={}
for op in ['xz','table','array']:
    p=Path(oldplan['sources'][op]['path']);n=oldplan['sources'][op]['n']
    with p.open() as f:bg[op]=np.array([[float(r['relative_s']),float(r['memory_current_mean'])] for r in csv.DictReader(f) if r['memory_current_mean'] and int(r['memory_current_n'])==n])
target=metrics['auto']['peak_t_s'];ages={'xz':629.5,'table':3.15,'array':5.25};offsets={op:round(target-age,2) for op,age in ages.items()}
lo=max([0]+[float(c[0,0]+offsets[op]) for op,c in bg.items()]);hi=min([duration]+[float(c[-1,0]+offsets[op]) for op,c in bg.items()])
knots=np.unique(np.concatenate([curves['auto'][:,0]]+[c[:,0]+offsets[op] for op,c in bg.items()]+[np.array([target,lo,hi])]))
best=None
for t in knots[(knots>=lo)&(knots<=hi)]:
    vals={'foreground':float(np.interp(t,curves['auto'][:,0],curves['auto'][:,1]))}
    vals.update({op:float(np.interp(t-offsets[op],c[:,0],c[:,1])) for op,c in bg.items()})
    row=dict(t_s=float(t),values_bytes=vals,total_GiB=sum(vals.values())/2**30)
    if best is None or row['total_GiB']>best['total_GiB']:best=row
candidate=dict(time_origin='automatic LAYER_IMPORT_SUBMITTED',offsets_s=offsets,foreground_peak_t_s=target,theoretical_peak=best,
    xz_age_at_target_s=629.5,scope='UNEXECUTED candidate; task memcg charge superposition, not physical RAM; no system baseline added')

result=dict(common_time_origin='import submission; old manual homepage time minus 14.399224989 s',common_window_s=[0,duration],
    common_high_threshold_GiB=threshold/2**30,sources=sources,metrics=metrics,delta=delta,candidate=candidate,
    caveats=['Manual curve is Krita-only cgroup; automatic curve includes automation, worker and helpers.',
             'One valid independent sample per implementation; does not establish repeatability or new concurrent OOM.',
             'Manual capture ends while Krita is still alive; auto includes normal close/exit after timed window.',
             'Threshold durations use piecewise-linear interpolation at actual sample times; no gap extrapolation.',
             'Independent PILOT collector stops on low memory/OOM and forbids XZ; baseline must reuse action runner under baseline supervision.'])
(out/'comparison.json').write_text(json.dumps(result,indent=2))
grid=np.arange(0,duration+.001,.05)
with (out/'aligned_curves.csv').open('w',newline='') as f:
    w=csv.writer(f);w.writerow(['seconds_from_import','manual_charge_bytes','auto_charge_bytes','manual_anon_bytes','auto_anon_bytes'])
    for t in grid:w.writerow([float(t),*[float(np.interp(t,curves[k][:,0],curves[k][:,col])) for col in [1,2] for k in ['manual','auto']]])

fig=plt.figure(figsize=(12,9));gs=fig.add_gridspec(3,1,height_ratios=[2.4,1.8,1.05]);axes=[fig.add_subplot(gs[i]) for i in range(3)]
colors={'manual':'#2467ad','auto':'#e27a18'};labels={'manual':'Simulated manual','auto':'Automated timed capture'}
for key,c in curves.items():
    w=c[(c[:,0]>=0)&(c[:,0]<=duration)]
    for ax in axes[:2]:
        ax.plot(w[:,0],w[:,1]/2**30,color=colors[key],lw=1.25,label=labels[key])
        p=metrics[key];ax.scatter(p['peak_t_s'],p['charge_peak_GiB'],color=colors[key],s=28,zorder=5)
    axes[1].axvline(metrics[key]['peak_t_s'],color=colors[key],ls=':',lw=1)
for ax in axes[:2]:
    ax.grid(alpha=.2);ax.set_ylabel('Workload cgroup charge (GiB)');ax.legend(loc='lower right',fontsize=9)
axes[0].axhline(threshold/2**30,color='gray',ls='--',lw=.8,label='old peak x 95%')
axes[0].set(xlim=(0,1350),title='Foreground comparison: both aligned to import submission (t = 0)')
axes[1].set(xlim=(1030,1200),ylim=(9.7,11.15),title=f"Peak window: {metrics['manual']['peak_t_s']:.2f} s vs {metrics['auto']['peak_t_s']:.2f} s; shift +{delta['peak_time_s']:.2f} s")
for y,key in enumerate(['manual','auto']):
    spans=metrics[key]['high_common95']['segments_s'];axes[2].broken_barh([(a,b-a) for a,b in spans],(y-.25,.5),facecolors=colors[key])
    axes[2].text(1340,y,f"{metrics[key]['high_common95']['total_s']:.1f} s total",va='center',ha='right',fontsize=9,bbox=dict(facecolor='white',alpha=.85,edgecolor='none'))
axes[2].set(yticks=[0,1],yticklabels=[labels['manual'],labels['auto']],xlim=(0,1350),ylim=(-.6,1.6),
    title=f'High-memory intervals using ONE threshold: {threshold/2**30:.3f} GiB (95% of old peak)',xlabel='Seconds from import submission')
axes[2].grid(axis='x',alpha=.2)
fig.text(.5,.008,'Same assets; different cgroup scope. A single run of each supports similarity, not exact equivalence or repeatability.',ha='center',fontsize=9)
fig.tight_layout(rect=(0,.025,1,1));fig.savefig(out/'comparison.png',dpi=170);plt.close(fig)
print(json.dumps(dict(output=str(out),delta=delta,candidate=candidate,metrics={k:{a:b for a,b in m.items() if not isinstance(b,dict)} for k,m in metrics.items()}),indent=2))
