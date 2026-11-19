"""After a sealed project run, create a separate review without rewriting it."""
import csv,hashlib,json,os,subprocess,sys,time
from pathlib import Path
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt

run=Path(sys.argv[1]);h=Path.home();source=Path((h/'TeamOOM/runtime/src/KRITA_TIMED_SOURCE.txt').read_text().strip())
base=source/'前台操作/前台操作自动化脚本采集'
sys.path.insert(0,str(base))
from oomlab_krita_collect.validation import validate_run,iter_samples
summary=validate_run(run)
events=[json.loads(x) for x in (run/'krita/phase-events.jsonl').read_text().splitlines()]
by={e['kind']:e for e in events if e.get('kind')}
origin=by['LAYER_IMPORT_SUBMITTED']['monotonic_ns'];deadline=origin+int(1350e9)
review=h/'TeamOOM/reports/reviews'/('timed-'+run.name);review.mkdir(parents=True,exist_ok=False)
rows=[];last=None;gaps=[]
with (review/'foreground_curve.csv').open('w',newline='') as f:
    fields=['t_since_import_s','memory_current_bytes','kernel_peak_bytes','anon_bytes','file_bytes','swap_bytes','system_available_bytes','krita_rss_bytes']
    w=csv.DictWriter(f,fieldnames=fields);w.writeheader()
    for r in iter_samples(run):
        if r['scope']!='krita':continue
        row=dict(t_since_import_s=(r['monotonic_ns']-origin)/1e9,memory_current_bytes=r['memory_current'],kernel_peak_bytes=r['memory_peak'],
                 anon_bytes=r['stat_anon'],file_bytes=r['stat_file'],swap_bytes=r['swap_current'],system_available_bytes=r['mem_available_bytes'],krita_rss_bytes=r['krita_vm_rss_bytes'])
        w.writerow(row);rows.append(row)
        if last is not None:gaps.append((r['monotonic_ns']-last)/1e9)
        last=r['monotonic_ns']
window=[r for r in rows if 0<=r['t_since_import_s']<=1350]
peak=max(window,key=lambda r:r['memory_current_bytes'])
fig,axs=plt.subplots(2,1,figsize=(11,7),sharex=True)
for field,label in [('memory_current_bytes','workload cgroup charge'),('anon_bytes','anonymous'),('file_bytes','file cache'),('krita_rss_bytes','Krita process RSS')]:
    axs[0].plot([r['t_since_import_s'] for r in rows],[r[field]/2**30 if r[field] is not None else float('nan') for r in rows],label=label,lw=1)
for field,label in [('system_available_bytes','system MemAvailable'),('swap_bytes','workload Swap')]:
    axs[1].plot([r['t_since_import_s'] for r in rows],[r[field]/2**30 for r in rows],label=label,lw=1)
for ax in axs:
    ax.axvline(0,color='gray',ls=':',label='import submitted');ax.axvline(1350,color='red',ls='--',label='timed window end')
    ax.grid(alpha=.2);ax.legend(fontsize=8);ax.set_ylabel('GiB')
axs[0].set_title('Automated independent foreground: 9000 x 9000, 45 imported files')
axs[1].set_xlabel('Seconds from import submission');fig.tight_layout();fig.savefig(review/'foreground_curve.png',dpi=160);plt.close(fig)
config=json.loads((run/'config.snapshot.json').read_text());meta=json.loads((run/'metadata.json').read_text())
result=dict(source_run=str(run),source_checkout=str(source),summary=summary,import_origin_monotonic_ns=origin,
    requested_window_s=config['automation']['capture_window_s'],actual_window_s=(by['CAPTURE_WINDOW_DONE']['monotonic_ns']-origin)/1e9,
    window_peak_GiB=peak['memory_current_bytes']/2**30,window_peak_t_s=peak['t_since_import_s'],max_sample_gap_s=max(gaps),
    mean_sample_interval_s=sum(gaps)/len(gaps),sample_count=len(rows),window_sample_count=len(window),
    all_eight_stages_pass=all(any(e.get('kind')=='phase_end' and e.get('phase')==i and e.get('status')=='PASS' for e in events) for i in range(1,9)),
    accessibility_queries_in_window=sum(1 for e in events if e.get('kind')=='ACCESSIBILITY_QUERY' and origin<=e['monotonic_ns']<=deadline),
    imported_layers_verified_by_automation=False,
    normal_Krita_exit=by['KRITA_EXIT'].get('returncode')==0,assets_unchanged=meta.get('assets_unchanged'),
    scope_note='Workload cgroup includes Krita, automation, worker and spawned helpers; collector and shared desktop services excluded. Not pure Krita RSS.')
(review/'verification.json').write_text(json.dumps(result,indent=2))
(review/'report.md').write_text(f'''# 定时前台自动化实机验证

- 项目结果：{summary.get('status')}；valid={summary.get('valid')}；formal_eligible=false。
- 八阶段全部 PASS：{result['all_eight_stages_pass']}；Krita 正常退出：{result['normal_Krita_exit']}。
- 沿用 9000×9000 空白 ORA 与 45 张 PNG；前后素材一致：{result['assets_unchanged']}。
- 从导入提交计时 {result['actual_window_s']:.6f} 秒，要求 {result['requested_window_s']} 秒；没有 1800 秒保持。
- 窗口内 ACCESSIBILITY_QUERY 事件数：{result['accessibility_queries_in_window']}。不通过轮询图层表推进采集；import_layers_verified=false。
- 窗口内 workload memory.current 采样峰值 {result['window_peak_GiB']:.6f} GiB，位于导入提交后 {result['window_peak_t_s']:.6f} 秒。
- 样本 {result['sample_count']} 个，平均间隔 {result['mean_sample_interval_s']:.6f} 秒，最大间隔 {result['max_sample_gap_s']:.6f} 秒。
- 原始运行目录：{run}。
- 验证错误：{summary.get('errors')}。

采集成功按定时窗口、正常操作退出、素材、归属和样本完整性判定；经过时间不自动证明 46 层已导入。该曲线记录 workload cgroup（含自动化/worker/helper），同时另绘 Krita RSS，不能把两者混为一谈。此 review 位于封印运行目录之外，不改写原 CSV 或 manifest.sha256。
''')
print(json.dumps(dict(review=str(review),**result),ensure_ascii=True))
