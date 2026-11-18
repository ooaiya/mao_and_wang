"""Post-run review: identify stretched batches, preserve raw observations."""
import csv,json,re,statistics,sys
from pathlib import Path
import numpy as np
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

root=Path(sys.argv[1]);s=json.loads((root/'summary.json').read_text());t0=s['T0_monotonic_ns']
def load(name):
 with (root/name).open() as f:return list(csv.DictReader(f))
system=load('system_memory.csv')
offset=statistics.median((int(r['wall_time_ns'])-int(r['monotonic_ns']))/1e9 for r in system if 1100<(int(r['monotonic_ns'])-t0)/1e9<1140)
bad={int(r['monotonic_ns']) for r in system if (int(r['wall_time_ns'])-int(r['monotonic_ns']))/1e9-offset>.5}
def elapsed(r):return (int(r['monotonic_ns'])-t0)/1e9
delays=[dict(t_s=elapsed(r),early_read_delay_s=(int(r['wall_time_ns'])-int(r['monotonic_ns']))/1e9-offset) for r in system if int(r['monotonic_ns']) in bad]
kernel=[json.loads(x) for x in (root/'kernel_journal.jsonl').read_text().splitlines()]
kill=next(k for k in kernel if 'Out of memory: Killed process' in k.get('MESSAGE',''))
kt=float(kill['__MONOTONIC_TIMESTAMP'])/1e6-t0/1e9
snapshot={}
names={'6641':'Krita','7953':'XZ','8658':'Array','8661':'Table'}
for r in kernel:
 m=re.match(r'\[\s*(6641|7953|8658|8661)\]\s+(.*)',r.get('MESSAGE',''))
 if m:
  v=m.group(2).split();snapshot[names[m.group(1)]]=dict(pid=int(m.group(1)),rss_GiB=int(v[3])*4096/2**30,anon_GiB=int(v[4])*4096/2**30,source_message=r['MESSAGE'])
ops=['foreground_krita','xz','array','table'];labels=['Krita','XZ','Array','Table'];colors=['#1677b8','#e88718','#ce3946','#2a9b57']
task={op:[] for op in ops}
with (root/'task_memory.csv').open() as f:
 for r in csv.DictReader(f):
  if r['operation'] in task and r['memory_current_bytes'] and elapsed(r)>=0:task[r['operation']].append(r)
sysgood=[r for r in system if int(r['monotonic_ns']) not in bad and elapsed(r)>=0]
good={op:[r for r in rows if int(r['monotonic_ns']) not in bad] for op,rows in task.items()}
gapstart=delays[0]['t_s'];gapend=min(elapsed(r) for r in sysgood if elapsed(r)>gapstart)
lastpre=max(elapsed(r) for r in sysgood if elapsed(r)<gapstart)
def points(rows,field):
 xs=[];ys=[];last=None
 for r in rows:
  t=elapsed(r)
  if last is not None and t-last>1:xs.append(np.nan);ys.append(np.nan)
  xs.append(t);ys.append(int(r[field])/2**30);last=t
 return xs,ys
def mark(ax,zoom=False):
 ax.axvspan(lastpre,gapend,color='#aaaaaa',alpha=.22,label='unresolved sampling interval')
 ax.axvline(kt,color='#b60000',ls='--',label='kernel OOM kill',lw=1.2)
 ax.grid(alpha=.2);ax.set_ylabel('GiB');ax.set_xlabel('Seconds from Krita homepage T0')
 if zoom:ax.set_xlim(1151,1191)
fig,axs=plt.subplots(2,1,figsize=(12,7.6),sharex=True)
for op,label,color in zip(ops,labels,colors):axs[0].plot(*points(good[op],'memory_current_bytes'),color=color,label=label,lw=1.2)
axs[0].set_title('Actual concurrent run: task cgroup memory.current')
axs[1].plot(*points(sysgood,'mem_available_bytes'),label='system MemAvailable',color='#7b3fa1',lw=1.2)
axs[1].set_title('Available system RAM; Linux Swap = 0 throughout measurement')
for ax in axs:mark(ax);ax.legend(fontsize=9,loc='best')
fig.tight_layout();fig.savefig(root/'actual_baseline_review.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(2,2,figsize=(12,7.8),sharex=True)
starts={'xz':529.5810465,'array':1153.819147157,'table':1155.930935782}
for ax,op,label,color in zip(axs.flat,ops,labels,colors):
 ax.plot(*points(good[op],'memory_current_bytes'),color=color,label='cgroup memory.current',lw=1.5)
 mark(ax,True);ax.set_ylim(bottom=0);ax.set_title(label)
 if op in ['array','table']:ax.axvline(starts[op],color='gray',ls=':',label='task start')
 ax.legend(fontsize=8,loc='upper right' if op in ['foreground_krita','xz'] else 'upper left')
fig.suptitle('OOM window: 14 s batch delay excluded; each task has its own vertical scale',fontsize=12)
fig.tight_layout();fig.savefig(root/'oom_tasks_review.png',dpi=170);plt.close(fig)
before=min(sysgood,key=lambda r:abs(elapsed(r)-lastpre));after=min(sysgood,key=lambda r:abs(elapsed(r)-gapend))
bvm=json.loads(before['vmstat_json']);avm=json.loads(after['vmstat_json'])
vmkeys=['pgscan_direct','pgsteal_direct','pgscan_kswapd','pgsteal_kswapd','allocstall_normal','allocstall_movable','pgmajfault','compact_stall','pswpout','oom_kill']
vm_delta={k:avm.get(k,0)-bvm.get(k,0) for k in vmkeys}
psipoints={}
with (root/'psi.csv').open() as f:
 for r in csv.DictReader(f):
  if r['scope']=='system' and r['resource']=='memory' and min(abs(elapsed(r)-lastpre),abs(elapsed(r)-gapend))<1e-6:psipoints.setdefault(r['stall'],[]).append(r)
psidelta={k:(int(v[1]['total_us'])-int(v[0]['total_us']))/1e6 for k,v in psipoints.items()}
task_summary={}
for op,rows in good.items():
 peak=max(rows,key=lambda r:int(r['memory_current_bytes']));post=min(rows,key=lambda r:abs(elapsed(r)-gapend))
 task_summary[op]=dict(sampled_peak_GiB=int(peak['memory_current_bytes'])/2**30,sampled_peak_t_s=elapsed(peak),kernel_peak_by_first_post_OOM_GiB=int(post['memory_peak_bytes'])/2**30,kernel_peak_whole_run_GiB=max(int(r['memory_peak_bytes']) for r in rows)/2**30)
evidence=dict(kernel_kill_t_s=kt,kernel_task_RSS_snapshot=snapshot,delayed_batches=delays,last_reliable_pre_batch_s=lastpre,next_batch_s=gapend,vmstat_delta_across_stall=vm_delta,memory_PSI_stall_delta_s=psidelta,tasks=task_summary,
 conclusion='Global OOM during four-task concurrency is confirmed. Four actual maxima were not aligned: Table kernel high-water after kill was only 0.203 GiB, reaching 2.630 GiB later.',
 timestamp_note='Batch stamp is recorded before meminfo and vmstat reads; wall_time_ns is obtained after both. One batch has 13.895 s of early-read/scheduling delay. Exact blocked syscall cannot be identified without per-step timing or tracing.')
(root/'oom_window_review.json').write_text(json.dumps(evidence,indent=2))
print(json.dumps(evidence,indent=2))
