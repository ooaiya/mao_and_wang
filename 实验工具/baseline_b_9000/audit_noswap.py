"""Audit the finished run; never run this during sampling."""
import csv,json,sys
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
root=Path(sys.argv[1]);a=json.loads((root/'analysis.json').read_text());v=json.loads((root/'validation.json').read_text())
t0=a['summary']['T0_monotonic_ns'];events=a['events']
kernel=json.loads((root/'oom_kernel_records.json').read_text())
kills=[k for k in kernel if 'Out of memory: Killed process' in k['MESSAGE']]
kill_t=float(kills[0]['__MONOTONIC_TIMESTAMP'])/1e6-t0/1e9
starts={e['operation']:(e['actual_monotonic_ns']-t0)/1e9 for e in events if e['event_type']=='process_created'}
system=[];gaps=[];previous=None
with (root/'system_memory.csv').open() as f:
 for r in csv.DictReader(f):
  t=(int(r['monotonic_ns'])-t0)/1e9
  if t<0:continue
  if previous is not None and t-previous>1:gaps.append(dict(start_s=previous,end_s=t,duration_s=t-previous))
  system.append((t,int(r['pressure_used_bytes'])/2**30,int(r['mem_available_bytes'])/2**30))
  previous=t
ops=['foreground_krita','xz','table','array'];curves={op:[] for op in ops}
with (root/'task_memory.csv').open() as f:
 for r in csv.DictReader(f):
  if r['operation'] in curves and r['memory_current_bytes']:
   t=(int(r['monotonic_ns'])-t0)/1e9
   if t>=0:curves[r['operation']].append((t,int(r['memory_current_bytes'])/2**30))
v.update(kernel_kill_t_s=kill_t,actual_process_start_s=starts,
 four_process_overlap_until_kernel_kill_s=kill_t-max(starts.values()),
 sampling_gaps=gaps,actual_four_independent_peaks_overlap_verified=False,
 timestamp_caveat='Collector stamps each batch at its start, then reads fields sequentially. The 14 s stall can span the OOM event. Counter-event timestamps and per-task sums are not atomic observations; use kernel timestamps for kill timing.',
 actual_peak_caveat='Sampled curves have a gap covering the critical window; observed maxima are lower bounds, and no interpolation across the gap is evidence of a measured peak.')
(root/'validation.json').write_text(json.dumps(v,indent=2))
fig,axes=plt.subplots(2,2,figsize=(14,8),sharex='col')
def broken(points,index):
 xs=[];ys=[];last=None
 for p in points:
  if last is not None and p[0]-last>1:xs.append(float('nan'));ys.append(float('nan'))
  xs.append(p[0]);ys.append(p[index]);last=p[0]
 return xs,ys
for col in range(2):
 ax=axes[0,col]
 for i,label in [(1,'RAM - MemAvailable'),(2,'MemAvailable')]:ax.plot(*broken(system,i),label=label,lw=1)
 ax.axhline(16722575360/2**30,color='gray',ls=':',label='RAM capacity')
 for op,points in curves.items():axes[1,col].plot(*broken(points,1),label=op,lw=1)
 for row in range(2):
  ax=axes[row,col]
  for g in gaps:ax.axvspan(g['start_s'],g['end_s'],color='gray',alpha=.2,label='sampling stall' if g==gaps[0] else None)
  ax.axvline(kill_t,color='red',ls='--',lw=1,label='kernel OOM kill')
  ax.grid(alpha=.2);ax.set_ylabel('GiB');ax.legend(fontsize=8,loc='best')
 axes[1,col].set_xlabel('Seconds from observed Krita homepage T0')
axes[0,0].set_title('Whole run; Linux Swap = 0')
axes[0,1].set_title('Critical window; shaded interval has incomplete sampling')
for row in range(2):axes[row,1].set_xlim(1148,1195)
fig.tight_layout();fig.savefig(root/'actual_baseline.png',dpi=160)
plan=json.loads((root/'overlap_plan.json').read_text())
report=f'''# 无 Swap 基线并发：已触发全局 OOM

四项工作负载保持原素材和参数，Krita 仍使用原内存配额；唯一系统内存配置变更是正式实验期间关闭 Linux Swap，实验后已恢复原 /swapfile（约 2 GiB）。没有人为设置任务 memory.max/high 上限。

| 操作 | 计划启动偏移 s | 实际进程创建偏移 s | 退出情况 |
|---|---:|---:|---|
| Krita | 0（欢迎页观察 T0） | {starts['foreground_krita']:.6f}（先启动，后观察主页） | 内核 OOM 杀死，PID 6641，返回 -9 |
| XZ | {plan['offsets_s']['xz']:.2f} | {starts['xz']:.6f} | 0，输出校验通过 |
| Array | {plan['offsets_s']['array']:.2f} | {starts['array']:.6f} | 0，输出校验通过 |
| Table | {plan['offsets_s']['table']:.2f} | {starts['table']:.6f} | 0，输出校验通过 |

理论四曲线叠加峰值为 **{plan['theoretical_peak_GiB']:.6f} GiB**（{plan['theoretical_peak_GB']:.6f} GB），目标时刻 +1159.04 s。XZ 在目标时刻取独立曲线峰值的 96.299%，用约 58 秒的历史提前结束余量换取存活保障。该数值是独立 cgroup charge 叠加，不能直接当作不可回收物理 RAM 需求。

## 内核证据

本轮系统 oom_kill 增量为 1，内核记录 CONSTRAINT_NONE / global_oom，受害进程为 Krita。内核杀进程时间为 **T0 +{kill_t:.6f} s**（约 19 分 32 秒），比理论对齐目标晚约 {kill_t-plan['theoretical_peak']['t_s']:.2f} 秒。从最后一个 Table 进程创建到内核 kill 记录，四项同时存活约 **{v['four_process_overlap_until_kernel_kill_s']:.6f} s**；进程退出轮询口径为 {v['four_process_overlap_s']:.6f} s，包含检测延迟。

```
{kills[0]['MESSAGE']}
```

全部正式样本 SwapTotal=0，结束后 swapon 返回 0，SwapTotal 恢复为 2147479552 字节。后台输入文件 SHA256 前后相同，三个后台结果均通过独立校验。Krita 在导入完成前被杀，其前台任务按未完成记录。

## 采样限制与峰值解释

采样间隔目标为 50 ms，正式样本 {a['summary']['collector']['formal_samples']} 个，无采集器异常；但严重内存压力下，从 +{gaps[0]['start_s']:.6f} 到 +{gaps[0]['end_s']:.6f} s 出现 **{gaps[0]['duration_s']:.6f} s** 的采样间隔。图中以灰色标出，曲线不跨间隔连接。采样批次时间在开始时记录，各字段顺序读取，因此该批次内的 OOM 计数事件时间也不能代替内核 kill 时间。

整机观测最小 MemAvailable 为 {v['actual_system_peak']['min_available']/2**20:.2f} MiB。逐任务同时采样账面和的观测最高值约 {v['simultaneous_task_peak']['total_task_charge_bytes']/2**30:.6f} GiB，但这些读数并非原子快照，关键窗口也存在缺口，不能把它当作实际完整峰值。

结论：**已验证四项并发期间发生真实的 Linux 全局 OOM；尚不能证明四项实际峰值精确重合。** 理论对齐与实际时序因内存回收、运行变慢和 OOM 截断而不同。本轮无需再改素材或配额即可复现 OOM；原始 CSV、逐任务日志和内核记录完整保留。
'''
(root/'report.md').write_text(report)
print(json.dumps({k:v[k] for k in ['global_OOM_confirmed','kernel_kill_t_s','four_process_overlap_until_kernel_kill_s','swap_restored','sampling_gaps']}))
