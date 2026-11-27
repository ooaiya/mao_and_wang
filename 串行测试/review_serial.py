"""Post-run verification and figures, outside the timed workload interval."""
import csv,hashlib,json,sys,time
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'基线并发'))
from common.shaped_scene import reference_unchanged, verify as verify_shaped

root=Path(sys.argv[1]);s=json.loads((root/'summary.json').read_text());provenance=json.loads((root/'input_provenance.json').read_text())
def sha(p):
    d=hashlib.sha256()
    with Path(p).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):d.update(b)
    return d.hexdigest()
verification={};unchanged={}
for op,v in provenance.items():
    try:
        unchanged[op]=reference_unchanged(v)
        verification[op]=verify_shaped(root/op,v) if s['tasks'].get(op,{}).get('returncode')==0 else dict(ok=False,reason='task did not complete')
    except (OSError,ValueError) as error:
        unchanged.setdefault(op,False)
        verification[op]=dict(ok=False,error=str(error))
assets=json.loads((root/'foreground_assets.json').read_text())
config=json.loads((root/'foreground_config.json').read_text())
contract=assets['script_contract'];prepared=contract.get('prepared_document')
asset_files=[assets['ora'],*assets['png_files']]+[assets[k] for k in ('prepared_ora','tail_ora') if k in assets]
unchanged['foreground_krita']=all(sha(f['path'])==f['sha256'] for f in asset_files)
events=[]
for line in (root/'foreground_krita/process.log').read_text().splitlines():
    if line.startswith('@@OOM_EVENT '):events.append(json.loads(line[len('@@OOM_EVENT '):]))
by={e['kind']:e for e in events if e.get('kind')};stages=all(any(e.get('kind')=='phase_end' and e.get('phase')==n and e.get('status')=='PASS' for e in events) for n in range(1,9))
foreground_check=dict(ok=stages and by.get('KRITA_EXIT',{}).get('returncode')==0
                      and by.get('CAPTURE_WINDOW_DONE',{}).get('actual_elapsed_s',0)>=config['automation']['capture_window_s'],
                      all_stages_pass=stages,import_layers_verified=False,
                      timed_window_s=by.get('CAPTURE_WINDOW_DONE',{}).get('actual_elapsed_s'))
if prepared:
    source=json.loads((root/'source_provenance.json').read_text())
    sys.path.insert(0,str(Path(source['foreground_source'])/'前台操作/前台操作自动化脚本采集'))
    from oomlab_krita_collect.validation import verify_pilot_events
    try:
        verify_pilot_events(events,contract)
        op='foreground_krita';expected_group='0::'+s['tasks'][op]['cgroup'].split('/sys/fs/cgroup',1)[1]
        for name,kind in (('process.json','KRITA_PROCESS'),('krita-post-process.json','KRITA_POST_PROCESS')):
            process=json.loads((root/op/name).read_text())
            if (process['cgroup']!=expected_group or process['pid']!=by[kind]['pid']
                or process['ppid']!=s['tasks'][op]['pid'] or not process['libqxcb_verified']):
                raise ValueError('foreground Krita identity/cgroup evidence mismatch')
    except (KeyError,ValueError,OSError) as error:
        foreground_check.update(ok=False,error=str(error))
verification['foreground_krita']=foreground_check
t0=s['T0_monotonic_ns'];curves={op:[] for op in s['order']};system=[];previous=None;gaps=[]
swap_totals=set()
with (root/'system_memory.csv').open() as f:
    for r in csv.DictReader(f):
        stamp=int(r['monotonic_ns'])
        if stamp<t0:continue
        if previous:gaps.append((stamp-previous)/1e9)
        swap_totals.add(int(r['swap_total_bytes']))
        previous=stamp;system.append(((stamp-t0)/1e9,int(r['pressure_used_bytes'])/2**30,int(r['mem_available_bytes'])/2**30,int(r['swap_used_bytes'])/2**30))
with (root/'task_memory.csv').open() as f:
    for r in csv.DictReader(f):
        if r['operation'] in curves and r['memory_current_bytes']:curves[r['operation']].append(((int(r['monotonic_ns'])-t0)/1e9,int(r['memory_current_bytes'])/2**30,int(r['stat_anon_bytes'] or 0)/2**30))
if prepared and foreground_check['ok']:
    windows={}
    for label,first,last in (
        ('pre_peak','PRE_IMPORT_REVIEW_START','PRE_IMPORT_REVIEW_DONE'),
        ('high','HIGH_DOCUMENT_SUBMITTED','CAPTURE_WINDOW_DONE'),
        ('post_peak','POST_CLOSE_REVIEW_START','POST_CLOSE_REVIEW_DONE'),
    ):
        start,end=((by[k]['monotonic_ns']-t0)/1e9 for k in (first,last))
        values=[p[1] for p in curves['foreground_krita'] if start<=p[0]<=end]
        windows[label]=dict(duration_s=end-start,samples=len(values),
                            min_GiB=min(values,default=None),max_GiB=max(values,default=None))
    foreground_check['pressure_windows']=windows
tasks={}
for op,v in s['tasks'].items():
    points=[p for p in curves[op] if v['start_ns']<=t0+p[0]*1e9<=v['empty_confirmed_ns']]
    peak=max(points,key=lambda p:p[1])
    tasks[op]=dict(**v,success=v['returncode']==0 and verification[op]['ok'] and unchanged[op],sampled_peak_GiB=peak[1],sampled_peak_time_s=peak[0]-(v['start_ns']-t0)/1e9)
handoffs=[dict(previous=a,next=b,gap_s=(tasks[b]['start_ns']-tasks[a]['empty_confirmed_ns'])/1e9) for a,b in zip(s['order'],s['order'][1:]) if a in tasks and b in tasks]
strict=s['strict_serial'] and len(handoffs)==3 and all(x['gap_s']>=0 for x in handoffs)
restoration=root/'swap_restoration.json'
swap_restored=json.loads(restoration.read_text())['restored'] if restoration.is_file() else None
swap_ok=not s['swap_changed'] or (swap_totals=={0} and swap_restored is True)
success=s['status']=='EXECUTED' and strict and s['all_groups_empty'] and s['global_oom_kill_delta']==0 and len(tasks)==4 and all(v['success'] for v in tasks.values()) and not s['collector']['errors'] and swap_ok
result=dict(success=success,tasks=tasks,total_workload_wall_s=s['total_workload_wall_s'],strict_serial=s['strict_serial'],input_files_unchanged=unchanged,output_verification=verification,
    handoffs=handoffs,global_oom_kill_delta=s['global_oom_kill_delta'],swap_changed=s['swap_changed'],swaps_after=s['swaps_after'],
    sampled_swap_totals_bytes=sorted(swap_totals),swap_restored=swap_restored,
    system_pressure_peak_GiB=max(p[1] for p in system),system_min_available_GiB=min(p[2] for p in system),system_swap_peak_GiB=max(p[3] for p in system),
    sampling=dict(samples=len(system),mean_interval_s=sum(gaps)/len(gaps),max_gap_s=max(gaps),gaps_over_1s=sum(g>1 for g in gaps)))
(root/'validation.json').write_text(json.dumps(result,indent=2))
import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
fig,axs=plt.subplots(2,1,figsize=(12,8),sharex=True)
for col,label in [(1,'RAM - MemAvailable'),(2,'MemAvailable'),(3,'system Swap used')]:axs[0].plot([p[0] for p in system],[p[col] for p in system],label=label,lw=1)
for op,points in curves.items():axs[1].plot([p[0] for p in points],[p[1] for p in points],label=op,lw=1.2)
for i,(op,r) in enumerate(tasks.items()):
    a=(r['start_ns']-t0)/1e9;b=(r['empty_confirmed_ns']-t0)/1e9
    for ax in axs:ax.axvline(a,color='gray',ls=':',lw=.7)
    if b-a>100:axs[0].text((a+b)/2,axs[0].get_ylim()[1]*.94,op,ha='center',fontsize=9)
for ax in axs:ax.legend(fontsize=9);ax.set_ylabel('GiB');ax.grid(alpha=.2)
axs[0].set_title('Serial test: '+' -> '.join(s['order'])+' | success: '+str(success));axs[1].set_xlabel('Seconds from first workload launch')
fig.tight_layout();fig.savefig(root/'serial_memory.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(4,1,figsize=(11,9))
for ax,(op,r) in zip(axs,tasks.items()):
    start=(r['start_ns']-t0)/1e9;duration=r['duration_s'];points=[p for p in curves[op] if start<=p[0]<=start+duration]
    for col,label in [(1,'cgroup current'),(2,'anonymous')]:ax.plot([p[0]-start for p in points],[p[col] for p in points],label=label,lw=1)
    ax.set_title(f"{op}: {duration:.3f} s, peak {r['sampled_peak_GiB']:.3f} GiB, success={r['success']}");ax.set_ylabel('GiB');ax.grid(alpha=.2);ax.legend(fontsize=8)
axs[-1].set_xlabel('Seconds from each task launch');fig.tight_layout();fig.savefig(root/'serial_tasks.png',dpi=160)
rows='\n'.join(f"|{op}|{r['duration_s']:.3f}|{r['sampled_peak_GiB']:.6f}|{r['returncode']}|{r['success']}|" for op,r in tasks.items())
profile=config['automation'].get('pressure_profile',{})
foreground_description=(
    f"前台使用已验收的三阶段配置。单层浏览 {profile['pre_import_review_s']} 秒，高压使用 46 层 ORA，"
    f"峰后使用 7 层 ORA 浏览 {profile['post_close_review_s']} 秒。"
    if prepared else '前台使用 9000×9000、45 张素材与 1350 秒定时自动化。'
)
swap_description=(
    f'正式采样的 SwapTotal 字节值为 {sorted(swap_totals)}。实验结束后的 Swap 恢复校验为 {swap_restored}。'
    if s['swap_changed'] else 'Swap 保持实验开始时状态。'
)
(root/'report.md').write_text(f'''# 四任务串行实测

整轮成功：**{success}**。总工作负载墙钟耗时 **{s['total_workload_wall_s']:.3f} 秒**（{s['total_workload_wall_s']/60:.3f} 分钟），从第一项启动前计至最后一项进程树为空，包含交接，不含事前哈希检查及事后校验/绘图。

|任务|时长 s|cgroup采样峰值 GiB|退出码|成功|
|---|---:|---:|---:|---|
{rows}

- 严格串行：{s['strict_serial']}；下一任务启动不早于前任务 cgroup 空确认；所有任务边界均已清空。
- 全局 oom_kill 增量：{s['global_oom_kill_delta']}；整机 RAM-MemAvailable 峰值 {result['system_pressure_peak_GiB']:.6f} GiB，可用内存最低 {result['system_min_available_GiB']:.6f} GiB。
- 输入哈希保持：{unchanged}；后台输出独立校验：{verification}。
- 平均采样间隔 {result['sampling']['mean_interval_s']:.6f}s，最大间隔 {result['sampling']['max_gap_s']:.6f}s。
- {foreground_description}
- {swap_description}
- 不清空缓存；前一任务退出后的文件缓存可能仍归属旧cgroup，曲线上残留current不等于进程仍运行。memory.current是任务记账，RAM-MemAvailable是整机另一指标，不相加。

原始 system_memory.csv/task_memory.csv/psi.csv、events.jsonl、命令、任务空确认时刻、输入清单、源代码摘要及输出校验均保留。各任务成功包含退出码和校验；OOM为0本身不足以判定整轮成功。
''')
print(json.dumps(result))
