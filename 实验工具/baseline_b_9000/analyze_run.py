"""Run AFTER formal sampling stops; do not read/plot large logs during collection."""
import csv
import json
import math
from pathlib import Path
import sys

root=Path(sys.argv[1]);summary=json.loads((root/'summary.json').read_text())
t0=summary['T0_monotonic_ns'];ops=('foreground_krita','xz','table','array')
task_peaks={op:0 for op in ops};swap_peaks={op:0 for op in ops};gaps=[];last=None
system=dict(resident_peak=0,pressure_peak=0,swap_peak=0,min_available=None)
plot=[]
with (root/'system_memory.csv').open() as f:
 for r in csv.DictReader(f):
  stamp=int(r['monotonic_ns'])
  if t0 is None or stamp<t0:continue
  if last is not None:gaps.append((stamp-last)/1e9)
  last=stamp
  for dst,src in [('resident_peak','resident_allocated_bytes'),('pressure_peak','pressure_used_bytes'),('swap_peak','swap_used_bytes')]:
   system[dst]=max(system[dst],int(r[src]))
  v=int(r['mem_available_bytes']);system['min_available']=v if system['min_available'] is None else min(v,system['min_available'])
  if not plot or stamp-plot[-1]['stamp']>=500_000_000:
   plot.append(dict(stamp=stamp,t=(stamp-t0)/1e9,resident=int(r['resident_allocated_bytes']),pressure=int(r['pressure_used_bytes']),available=v,swap=int(r['swap_used_bytes'])))
with (root/'task_memory.csv').open() as f:
 for r in csv.DictReader(f):
  op=r['operation'];stamp=int(r['monotonic_ns'])
  if op not in task_peaks or t0 is None or stamp<t0 or not r['memory_current_bytes']:continue
  task_peaks[op]=max(task_peaks[op],int(r['memory_current_bytes']))
  swap_peaks[op]=max(swap_peaks[op],int(r['memory_swap_current_bytes'] or 0))
best=None;all95_count=0;four_active_count=0;current_stamp=None;sample={}
def finish_sample(stamp,values):
 global best,all95_count,four_active_count
 if stamp is None or len(values)!=4:return
 total=sum(values.values())
 if best is None or total>best['total_task_charge_bytes']:
  best=dict(t=(stamp-t0)/1e9,values=values.copy(),total_task_charge_bytes=total)
 if all(values.get(op,0)>32*1024**2 for op in ops):four_active_count+=1
 if all(task_peaks[op]>0 and values.get(op,0)>=.95*task_peaks[op] for op in ops):all95_count+=1
with (root/'task_memory.csv').open() as f:
 for r in csv.DictReader(f):
  stamp=int(r['monotonic_ns']);op=r['operation']
  if t0 is None or stamp<t0 or not r['memory_current_bytes']:continue
  if stamp!=current_stamp:
   finish_sample(current_stamp,sample);current_stamp=stamp;sample={}
  sample[op]=int(r['memory_current_bytes'])
 finish_sample(current_stamp,sample)
events=[json.loads(x) for x in (root/'events.jsonl').read_text().splitlines() if x.strip()]
starts={e['operation']:e['actual_monotonic_ns'] for e in events if e['event_type']=='process_created'}
ends={e['operation']:e['actual_monotonic_ns'] for e in events if e['event_type']=='process_exit'}
concurrent_process_s=None
if set(ops)<=set(starts):
 concurrent_process_s=max(0,(min(ends.get(op,last) for op in ops)-max(starts[op] for op in ops))/1e9)
phases={}
for op in ops[1:]:
 p=root/op/'phase_trace.jsonl'
 phases[op]=[json.loads(x) for x in p.read_text().splitlines() if x.strip()] if p.exists() else []
kills=json.loads((root/'oom_kernel_records.json').read_text())
report=dict(source=str(root),summary=summary,system=system,task_current_peaks=task_peaks,
 task_swap_peaks=swap_peaks,maximum_simultaneous_task_charge=best,
 four_tasks_above_32MiB_samples=four_active_count,
 four_process_lifetime_overlap_s=concurrent_process_s,
 all_four_at_95pct_of_this_runs_observed_current_max_samples=all95_count,
 caveat='Observed maxima may be OOM-truncated; task memcg charge is not identical to physical anonymous memory. No independent-curve maxima have been substituted.',
 sample_gaps=dict(n=len(gaps),maximum_s=max(gaps) if gaps else None,over_1s=sum(v>1 for v in gaps)),
 kernel_messages=[x.get('MESSAGE','') for x in kills],events=events,phases=phases)
(root/'analysis.json').write_text(json.dumps(report,indent=2,ensure_ascii=False))
with (root/'system_plot.csv').open('w',newline='') as f:
 w=csv.DictWriter(f,fieldnames=['stamp','t','resident','pressure','available','swap']);w.writeheader();w.writerows(plot)
print(json.dumps({k:v for k,v in report.items() if k not in ['events','phases','summary']},ensure_ascii=True,indent=2))
