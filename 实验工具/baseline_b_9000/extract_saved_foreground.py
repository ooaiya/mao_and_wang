"""Postprocess the preserved run; never mutate its raw collection files."""
import csv
import hashlib
import json
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path.home()/'TeamOOM/results/baselineB-9000-45-20261108T151125Z'
summary=json.loads((root/'summary.json').read_text());t0=summary['T0_monotonic_ns']
events=[json.loads(x) for x in (root/'events.jsonl').read_text().splitlines()]
curves={op:[] for op in ['foreground_krita','xz','table','array']}
fore=[]
with (root/'task_memory.csv').open() as f:
 for r in csv.DictReader(f):
  if r['operation'] not in curves or not r['memory_current_bytes']:continue
  t=(int(r['monotonic_ns'])-t0)/1e9
  if t<0:continue
  current=int(r['memory_current_bytes']);curves[r['operation']].append((t,current))
  if r['operation']=='foreground_krita':
   fore.append(dict(t_s=t,monotonic_ns=int(r['monotonic_ns']),cgroup_current_bytes=current,
      anon_bytes=int(r['stat_anon_bytes'] or 0),file_bytes=int(r['stat_file_bytes'] or 0),
      cgroup_swap_bytes=int(r['memory_swap_current_bytes'] or 0),
      memory_stat_json=r['memory_stat_json'],process_memory_json=r['process_memory_json']))
with (root/'foreground_curve.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=list(fore[0]));w.writeheader();w.writerows(fore)
peak=max(fore,key=lambda r:r['cgroup_current_bytes'])
marks={}
for e in events:
 if e['event_type'] in ['import_submit','import_complete','hold_complete','nominal_release','process_exit']:
  marks[e['event_type']+':'+e['operation']]=(e['actual_monotonic_ns']-t0)/1e9
fig,axes=plt.subplots(2,1,figsize=(12,8),sharex=True,gridspec_kw={'height_ratios':[2,1]})
ax=axes[0];xs=[r['t_s'] for r in fore]
for key,label in [('cgroup_current_bytes','Krita cgroup memory.current'),('anon_bytes','Krita cgroup anonymous pages'),('cgroup_swap_bytes','Krita cgroup Linux swap')]:
 ax.plot(xs,[r[key]/2**30 for r in fore],label=label,lw=1.4)
ax.axhline(14.3,color='#a65b20',ls=':',label='14.3 GiB GUI document size (not resident RAM)')
ax.scatter([peak['t_s']],[peak['cgroup_current_bytes']/2**30],color='#264b96',s=30,zorder=5)
ax.annotate(f"Sampled peak: {peak['cgroup_current_bytes']/2**30:.3f} GiB\nt={peak['t_s']:.1f}s",xy=(peak['t_s'],peak['cgroup_current_bytes']/2**30),xytext=(25,18),textcoords='offset points')
for name,color in [('import_submit:foreground_krita','#555555'),('import_complete:foreground_krita','#238b45'),('nominal_release:xz','#8a489b'),('nominal_release:table','#b33b28')]:
 if name in marks:
  label=name.split(':')[0]+' '+name.split(':')[1].replace('foreground_krita','Krita')
  ax.axvline(marks[name],color=color,ls='--',alpha=.6,label=label)
for op,color in [('xz','#8a489b'),('table','#b33b28'),('array','#238b45')]:
 pairs=curves[op]
 axes[1].plot([p[0] for p in pairs],[p[1]/2**30 for p in pairs],label=op,color=color,lw=1.3)
for a in axes:a.grid(alpha=.2);a.set_ylabel('GiB');a.legend(fontsize=8,loc='upper left')
axes[0].set_title('Preserved Krita 9000 x 9000 / 45 imported layers: measured task curve')
axes[1].set_xlabel('Seconds from this run\'s observed main-window T0')
fig.text(.5,.01,'Concurrent-run extraction; not a standalone foreground trial. Original CSVs preserved. Global OOM kills: 0.',ha='center',fontsize=9)
fig.tight_layout(rect=[0,.025,1,1]);fig.savefig(root/'foreground_curve.png',dpi=160);plt.close(fig)
info=dict(source_kind='MEASURED_CONCURRENT_TASK_CURVE',source_run=str(root),
 source_raw_file=str(root/'task_memory.csv'),sample_count=len(fore),duration_s=xs[-1]-xs[0],
 T0_event=summary['T0_event'],peak_cgroup_current_bytes=peak['cgroup_current_bytes'],
 peak_cgroup_current_GiB=peak['cgroup_current_bytes']/2**30,peak_t_s=peak['t_s'],
 kernel_memory_peak_bytes=11681058816,GUI_document_size_GiB_approx=14.3,
 events_s=marks,OOM_kill_delta=summary['global_oom_kill_delta'],
 output_csv=str(root/'foreground_curve.csv'),output_png=str(root/'foreground_curve.png'),
 note='Backgrounds overlap part of this curve; use as measured concurrent evidence, not label it independent.')
(root/'foreground_curve_metadata.json').write_text(json.dumps(info,indent=2))
print(json.dumps(info,indent=2))
