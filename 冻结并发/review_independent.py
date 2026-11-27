"""Post-run correctness, independent ledger check, memory figures and evidence."""
import csv,hashlib,json,subprocess,sys
from pathlib import Path
sys.path.insert(0,str(Path(__file__).resolve().parents[1]/'基线并发'))
from common.shaped_scene import reference_unchanged, verify as verify_shaped
from priority_policy import audit_decisions

root=Path(sys.argv[1]);summary=json.loads((root/'summary.json').read_text())
plan_path=root/'planning/plan.json'
if summary['status']!='EXECUTED' and (not plan_path.is_file() or not summary['tasks']):
    evidence=dict(summary,success=False,experiment_complete=False)
    (root/'validation.json').write_text(json.dumps(evidence,indent=2))
    report=f"# 实验启动失败\n\n未完成正式测量。错误为 `{summary['error']}`。\n"
    (root/'report.md').write_text(report,encoding='utf-8')
    raise SystemExit(1)
plan=json.loads(plan_path.read_text())
if plan.get('workload_kind')!='shaped' or plan.get('execution_mode')!='priority':
    raise SystemExit('Expected a predictive run of the current four-task scene')
if summary['status']!='EXECUTED':
    from review_failed import review
    review(root);raise SystemExit()

def sha(path):
    d=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):d.update(b)
    return d.hexdigest()
def save(name,v):(root/name).write_text(json.dumps(v,indent=2,ensure_ascii=False))
provenance=json.loads((root/'input_provenance.json').read_text());unchanged={};verification={}
for op,v in provenance.items():
    try:
        unchanged[op]=reference_unchanged(v)
        verification[op]=verify_shaped(root/op,v) if summary['tasks'].get(op,{}).get('returncode')==0 else dict(ok=False,reason='task not complete')
    except (OSError,ValueError) as error:
        unchanged.setdefault(op,False)
        verification[op]=dict(ok=False,error=str(error))
assets=json.loads((root/'foreground_assets.json').read_text())
fg_inputs=[assets['ora'],*assets['png_files']]+[assets[k] for k in ('prepared_ora','tail_ora') if k in assets]
unchanged['foreground_krita']=all(sha(f['path'])==f['sha256'] for f in fg_inputs)
gui=[]
for line in (root/'foreground_krita/process.log').read_text().splitlines():
    if line.startswith('@@OOM_EVENT '):gui.append(json.loads(line[len('@@OOM_EVENT '):]))
by={e['kind']:e for e in gui if 'kind' in e};phases=all(any(e.get('kind')=='phase_end' and e.get('phase')==i and e.get('status')=='PASS' for e in gui) for i in range(1,9))
window=json.loads((root/'foreground_config.json').read_text())['automation']['capture_window_s']
verification['foreground_krita']=dict(ok=phases and by.get('KRITA_EXIT',{}).get('returncode')==0 and by.get('CAPTURE_WINDOW_DONE',{}).get('actual_elapsed_s',0)>=window,
    all_stages_pass=phases,timed_window_s=by.get('CAPTURE_WINDOW_DONE',{}).get('actual_elapsed_s'),import_layers_verified=False)
source=json.loads((root/'source_provenance.json').read_text())['foreground_source']
sys.path.insert(0,str(Path(source)/'前台操作/前台操作自动化脚本采集'))
from oomlab_krita_collect.validation import verify_pilot_events
try:
    verify_pilot_events(gui,assets['script_contract'])
    task=summary['tasks']['foreground_krita']
    expected_group='0::'+task['cgroup'].split('/sys/fs/cgroup',1)[1]
    for name,kind in (('process.json','KRITA_PROCESS'),('krita-post-process.json','KRITA_POST_PROCESS')):
        process=json.loads((root/'foreground_krita'/name).read_text())
        if (process['cgroup']!=expected_group or process['pid']!=by[kind]['pid']
            or process['ppid']!=task['pid'] or not process['libqxcb_verified']):
            raise ValueError('Krita process identity mismatch')
except (ValueError,KeyError,OSError) as error:
    verification['foreground_krita'].update(ok=False,error=str(error))

models=plan['models'];budget=plan['budget']
t0=summary['T0_monotonic_ns'];curves={op:[] for op in plan['alignment']['offsets_s']};system=[]
backgrounds=[op for op in curves if op!='foreground_krita']
with (root/'system_memory.csv').open() as f:
    for r in csv.DictReader(f):
        if int(r['monotonic_ns'])>=t0:system.append(r)
with (root/'task_memory.csv').open() as f:
    for r in csv.DictReader(f):curves[r['operation']].append(r)
freezes=json.loads((root/'freeze_events.json').read_text());proofs={}
for op in backgrounds:
    pairs=[];opened=None;transition_errors=[];events=[r for r in freezes if r['operation']==op]
    record=summary['tasks'][op]
    release=record.get('release_confirmed_ns')
    actual_start=record.get('actual_start_ns')
    nominal=t0+round(plan['alignment']['offsets_s'][op]*1e9)
    if record['created_ns']<nominal:
        transition_errors.append('task submitted before the configured offset')
    if release is None or actual_start is None or not record['created_ns']<=release<=actual_start:
        transition_errors.append('missing or invalid initial gate release')
    if any('decision_tick' not in event or release is None
           or event['requested_monotonic_ns']<release for event in events):
        transition_errors.append('freezer transition outside runtime pressure control')
    for event in events:
        if event['action']=='freeze':
            if opened is not None:transition_errors.append('duplicate freeze without resume')
            opened=event
        else:
            if opened is None:transition_errors.append('resume without confirmed freeze');continue
            pairs.append((opened,event));opened=None
    terminal_empty=False
    if opened is not None:
        task=summary['tasks'].get(op,{})
        terminal_empty=task.get('returncode')==0 and summary['all_groups_empty'] and task.get('empty_confirmed_ns',0)>=opened['confirmed_monotonic_ns']
        if not terminal_empty:transition_errors.append('unclosed final pause')
    intervals=[]
    for f,u in pairs:
        held=[r for r in curves[op] if f['confirmed_monotonic_ns']+100000000<=int(r['monotonic_ns'])<=u['requested_monotonic_ns']-100000000 and r['frozen']=='1']
        delta=max((int(r['cpu_usage_usec']) for r in held),default=0)-min((int(r['cpu_usage_usec']) for r in held),default=0)
        duration=(u['confirmed_monotonic_ns']-f['confirmed_monotonic_ns'])/1e9
        if duration<0 or f['events']['frozen']!=1 or u['events']['frozen']!=0:transition_errors.append('invalid kernel transition order/state')
        if duration>.3 and not held:transition_errors.append('missing samples inside confirmed long pause')
        intervals.append(dict(freeze_ns=f['confirmed_monotonic_ns'],resume_ns=u['confirmed_monotonic_ns'],duration_s=duration,frozen_samples=len(held),cpu_delta_usec=delta))
    proofs[op]=dict(freeze_count=sum(e['action']=='freeze' for e in events),
        freeze_confirmed=bool(pairs) and all(f['events']['frozen']==1 for f,u in pairs),resume_confirmed=bool(pairs) and all(u['events']['frozen']==0 for f,u in pairs),
        frozen_sample_count=sum(p['frozen_samples'] for p in intervals),frozen_cpu_delta_usec=max((p['cpu_delta_usec'] for p in intervals),default=0),
        frozen_duration_s=sum(p['duration_s'] for p in intervals),intervals=intervals,transition_errors=transition_errors,completed_while_final_group_empty=terminal_empty)

tasks={}
for op,r in summary['tasks'].items():
    points=curves[op];peak=max(points,key=lambda x:int(x['memory_current_bytes']))
    tasks[op]=dict(**r,success=r.get('returncode')==0 and verification[op]['ok'] and unchanged[op],sampled_peak_GiB=int(peak['memory_current_bytes'])/2**30,
        sampled_anon_peak_GiB=max(int(p['stat_anon_bytes']) for p in points)/2**30,sampled_file_peak_GiB=max(int(p['stat_file_bytes']) for p in points)/2**30,
        prior_model_peak_GiB=models[op]['peak_bytes']/2**30 if op in models else None,
        actual_to_prior_peak_ratio=int(peak['memory_current_bytes'])/models[op]['peak_bytes'] if op in models else None,
        peak_homepage_s=(int(peak['monotonic_ns'])-t0)/1e9,submitted_homepage_s=(r['created_ns']-t0)/1e9,
        actual_start_homepage_s=(r.get('actual_start_ns',r['created_ns'])-t0)/1e9,
        release_homepage_s=(r['release_confirmed_ns']-t0)/1e9 if r.get('release_confirmed_ns') else None)

fg_task=tasks['foreground_krita'];foreground_interval=(fg_task['created_ns'],fg_task['empty_confirmed_ns'])
overlap_with_foreground={}
for op in backgrounds:
    task=tasks[op];intervals=task.get('running_intervals_ns',[[task['actual_start_ns'],task['empty_confirmed_ns']]])
    overlap_with_foreground[op]=sum(max(0,min(end,foreground_interval[1])-max(start,foreground_interval[0])) for start,end in intervals if end is not None)/1e9
reference=Path(plan['independent_run'])
checkpoint=summary['runtime_policy']['confirmed_checkpoint_ns']
priority_audit=audit_decisions(root,plan,freezes,checkpoint)
for rel,expected in plan['independent_hashes'].items():
    if sha(reference/rel)!=expected:priority_audit['errors'].append('reference input hash differs: '+rel)
if checkpoint is not None:
    marker=plan['priority_checkpoint']
    event=by.get(marker['event'],{})
    if (event.get('monotonic_ns')!=checkpoint or event.get('returncode')!=0
        or event.get('pid')!=by.get(marker['identity_event'],{}).get('pid')):
        priority_audit['errors'].append('checkpoint does not match successful process exit')

# Collect kernel evidence only after the measured interval. Use the GUI's paired
# MONOTONIC/wall stamp to select this experiment's kernel journal interval.
anchor=gui[0];first=min(r['created_ns'] for r in summary['tasks'].values());finish=max(r['empty_confirmed_ns'] for r in summary['tasks'].values())
wall=lambda stamp:(anchor['wall_time_ns']+stamp-anchor['monotonic_ns'])/1e9
journal=subprocess.run(['journalctl','-k','-o','json','--no-pager','--since','@'+str(wall(first)-1),'--until','@'+str(wall(finish)+1)],capture_output=True,text=True)
(root/'kernel_journal.jsonl').write_text(journal.stdout)
oom=[]
for line in journal.stdout.splitlines():
    try:e=json.loads(line)
    except ValueError:continue
    msg=e.get('MESSAGE','').lower()
    if any(s in msg for s in ['out of memory','oom-kill:','killed process']):oom.append(e)
swap_restoration=json.loads((root/'swap_restoration.json').read_text())
no_swap=bool(system) and all(int(r['swap_total_bytes'])==0 for r in system)
cg_oom={op:json.loads(rows[-1]['memory_events_json']).get('oom_kill',0) for op,rows in curves.items() if rows}
freezer_proofs_ok=all(not p['transition_errors'] and p['frozen_cpu_delta_usec']<1000
                      for p in proofs.values())
success=(summary['status']=='EXECUTED' and len(tasks)==4 and all(r['success'] for r in tasks.values())
         and summary['all_groups_empty'] and summary['global_oom_kill_delta']==0 and not any(cg_oom.values())
         and journal.returncode==0 and not oom and no_swap and swap_restoration['restored']
         and not summary['collector']['errors'] and freezer_proofs_ok and not priority_audit['errors'])
result=dict(success=success,tasks=tasks,output_verification=verification,input_files_unchanged=unchanged,freezer_proofs=proofs,
    total_from_homepage_s=summary['total_from_homepage_s'],total_from_first_launch_s=summary['total_from_first_launch_s'],global_oom_kill_delta=summary['global_oom_kill_delta'],cgroup_oom_kill=cg_oom,
    swap_zero_all_formal_samples=no_swap,swap_restoration=swap_restoration,kernel_journal_read_ok=journal.returncode==0,kernel_oom_records=oom,
    sampling=summary['collector'],source_kind=plan['source_kind'],baseline_rerun=False,
    review_source_sha256=sha(__file__),foreground_background_thawed_overlap_s=overlap_with_foreground,
    priority_audit=priority_audit,
    system_min_available_GiB=min(int(r['mem_available_bytes']) for r in system)/2**30,system_pressure_peak_GiB=max(int(r['pressure_used_bytes']) for r in system)/2**30)

import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
colors=dict(foreground_krita='tab:blue',raster='tab:orange',table='tab:green',array='tab:red')
fig,axs=plt.subplots(3,1,figsize=(12,10),sharex=True,gridspec_kw=dict(height_ratios=[2,2,1]))
x=[(int(r['monotonic_ns'])-t0)/1e9 for r in system]
for key,label in [('pressure_used_bytes','RAM - MemAvailable'),('mem_available_bytes','MemAvailable')]:axs[0].plot(x,[int(r[key])/2**30 for r in system],label=label,lw=1)
axs[0].axhline(budget['memtotal_bytes']/2**30,color='gray',ls='--',label='Physical RAM')
for i,(op,r) in enumerate(tasks.items()):
    points=curves[op];axs[1].plot([(int(p['monotonic_ns'])-t0)/1e9 for p in points],[int(p['memory_current_bytes'])/2**30 for p in points],label=op,color=colors[op],lw=1)
    a=r['submitted_homepage_s'];b=r['release_homepage_s'];end=(r['empty_confirmed_ns']-t0)/1e9
    if r.get('pause_intervals_ns') is not None:
        for first,last in r['pause_intervals_ns']:
            if last is not None:axs[2].barh(i,(last-first)/1e9,left=(first-t0)/1e9,color='lightgray')
        for first,last in r['running_intervals_ns']:
            if last is not None:axs[2].barh(i,(last-first)/1e9,left=(first-t0)/1e9,color=colors[op])
    else:
        if op!='foreground_krita':axs[2].barh(i,b-a,left=a,color='lightgray')
        axs[2].barh(i,end-b,left=b,color=colors[op])
axs[2].set_yticks(range(4),list(tasks));axs[2].set_xlabel('Seconds from automatic homepage readiness; gray = frozen, color = executing')
for ax in axs:ax.grid(alpha=.2)
for ax in axs[:2]:ax.set_ylabel('GiB');ax.legend(fontsize=8)
title='Independent-prior freezer experiment'
axs[0].set_title(title+' | Swap OFF | all checks passed = '+str(success))
fig.tight_layout();fig.savefig(root/'freezer_memory.png',dpi=160);plt.close(fig)
fig,axs=plt.subplots(4,1,figsize=(11,10))
for ax,(op,r) in zip(axs,tasks.items()):
    points=curves[op];start=r.get('actual_start_ns',r['created_ns'])
    for key,label in [('memory_current_bytes','cgroup current'),('stat_anon_bytes','anonymous')]:ax.plot([(int(p['monotonic_ns'])-start)/1e9 for p in points if start<=int(p['monotonic_ns'])<=r['empty_confirmed_ns']],[int(p[key])/2**30 for p in points if start<=int(p['monotonic_ns'])<=r['empty_confirmed_ns']],label=label,lw=1)
    for first,last in r.get('pause_intervals_ns',[]):
        if last is not None and last>start:ax.axvspan(max(0,(first-start)/1e9),(last-start)/1e9,color='gray',alpha=.15)
    ax.set_title('%s: peak %.3f GiB; frozen %.2f s; execution %.2f s'%(op,r['sampled_peak_GiB'],r.get('frozen_s',0),r['execution_wall_s']));ax.set_ylabel('GiB');ax.legend(fontsize=8);ax.grid(alpha=.2)
axs[-1].set_xlabel('Seconds from actual execution start (foreground: automation launch); frozen waiting excluded');fig.tight_layout();fig.savefig(root/'freezer_tasks.png',dpi=160);plt.close(fig)

table='\n'.join('|%s|%.3f|%.3f|%.3f|%.3f|%s|'%(op,r['submitted_homepage_s'],r.get('frozen_s',0),r['execution_wall_s'],r['sampled_peak_GiB'],r['success']) for op,r in tasks.items())
measured=summary['total_from_first_launch_s']
report=f"""# 按内存压力分级的冻结并发

四项任务及输出校验通过 **{success}**。本轮总耗时 {measured:.3f} 秒。

|任务|实际提交（首页后秒）|冻结（秒）|执行跨度（秒）|cgroup 采样峰值（GiB）|成功|
|---|---:|---:|---:|---:|---|
{table}

- 后台按提交偏移直接执行，运行中按压力决定冻结。
- 后台与前台重叠的解冻时间（秒）为 {overlap_with_foreground}。
- 复核了 {priority_audit['ticks']} 次预算决策和 {priority_audit['memory_high_writes']} 次软限额写入。压力冻结确认最长 {priority_audit['max_pressure_freeze_ms']:.3f} ms。审计错误为 {priority_audit['errors']}。
- 最低 MemAvailable 为 {result['system_min_available_GiB']:.3f} GiB。全局 OOM kill 增量为 {summary['global_oom_kill_delta']}。正式样本 Swap 为零的校验为 {no_swap}，系统 Swap 恢复为 {swap_restoration['restored']}。

[验证结果](validation.json) · [预算和曲线来源](planning/plan.json) · [内存与执行曲线](freezer_memory.png)
"""
(root/'report.md').write_text(report,encoding='utf-8')
save('validation.json',result)
print(json.dumps(dict(success=success,comparison=result.get('serial_comparison'),audit=priority_audit)))
raise SystemExit(0 if success else 1)
