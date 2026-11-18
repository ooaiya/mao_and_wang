"""Post-run correctness, independent ledger check, memory figures and evidence."""
import bisect,csv,hashlib,json,subprocess,sys
from pathlib import Path
root=Path(sys.argv[1]);h=Path.home();summary=json.loads((root/'summary.json').read_text())
plan_path=root/'planning/plan.json'
realtime_mode=summary.get('runtime_policy',{}).get('name')=='realtime_freezer'
if summary['status']!='EXECUTED' and (realtime_mode or not plan_path.is_file() or not summary['tasks']):
    evidence=dict(summary,success=False,experiment_complete=False)
    (root/'validation.json').write_text(json.dumps(evidence,indent=2))
    report=(f"# 实验未完成\n\n错误为 `{summary['error']}`。原始采样和事件保存在本轮目录。\n" if realtime_mode
            else f"# 实验启动失败\n\n未完成正式测量。错误为 `{summary['error']}`。\n")
    (root/'report.md').write_text(report,encoding='utf-8')
    raise SystemExit(1)
plan=json.loads(plan_path.read_text())
serial_curves=plan.get('source_kind')=='MEASURED_SERIAL_CURVES'
priority_mode=plan.get('execution_mode')=='priority'
run_on_submit=plan.get('background_start')=='run_on_submit'
if summary['status']!='EXECUTED':
    from review_failed import review
    review(root);raise SystemExit()
sys.path.insert(0,str(h/'bg'));from oomlab.workloads import verify

def sha(path):
    d=hashlib.sha256()
    with Path(path).open('rb') as f:
        for b in iter(lambda:f.read(1048576),b''):d.update(b)
    return d.hexdigest()
def save(name,v):(root/name).write_text(json.dumps(v,indent=2,ensure_ascii=False))
def step(points,t):
    at=bisect.bisect_right(points,[t,float('inf')])-1
    return points[max(0,at)][1]

provenance=json.loads((root/'input_provenance.json').read_text());unchanged={};verification={}
for op,v in provenance.items():
    if op=='raster_fft':
        from raster_priority import verify_raster
        unchanged[op]=sha(v['worker'])==v['worker_sha256'] and all(
            sha(Path(v['reference_run'])/name)==digest for name,digest in v['reference_hashes'].items())
        try:verification[op]=verify_raster(root/op,v)
        except (OSError,ValueError) as error:verification[op]=dict(ok=False,error=str(error))
        continue
    unchanged[op]=sha(Path(v['path'])/v['manifest']['file'])==v['input_sha256']
    try:verification[op]=verify(v['path'],root/op) if summary['tasks'].get(op,{}).get('returncode')==0 else dict(ok=False,reason='task not complete')
    except Exception as e:verification[op]=dict(ok=False,error=repr(e))
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
if serial_curves or realtime_mode:
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

ledger=[]
if not (priority_mode or realtime_mode):
    ledger_name='continuation_ledger.tsv' if serial_curves else 'native_ledger.tsv'
    with (root/'planning'/ledger_name).open() as f:ledger=list(csv.DictReader(f,delimiter='\t'))
ledger_errors=[];models=plan.get('models',{});budget=plan['budget']
if priority_mode or realtime_mode:
    releases={}
elif serial_curves:
    releases=plan['continuation']['release_after_foreground_exit_s']
    xz_peak=models['xz']['peak_bytes']
else:
    releases=plan['planned_release_s']
for row in ledger:
    t=int(row['time_ms'])
    foreground=xz_peak if serial_curves else step(models['foreground_krita']['curve'],t)
    total=budget['base_pressure_bytes']+budget['reserve_bytes']+3*budget['waiting_per_task_bytes']+foreground
    for op in releases:
        age=t-round(releases[op]*1000)
        if age>=0:total+=step(models[op]['curve'],age)
    if total!=int(row['reserved_bytes']) or total>budget['memtotal_bytes']:ledger_errors.append(dict(time_ms=t,calculated=total,native=int(row['reserved_bytes'])))

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
    if run_on_submit:
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

segmented_audit=None
offline_audit=None
if (root/'planning/offline_plan.json').exists():
    from offline_audit import audit
    offline_audit=audit(root)
if (root/'segmented_policy.json').exists():
    from segmented_scheduler import audit_decisions
    cfg=json.loads((root/'segmented_policy.json').read_text())
    with (root/'segment_decisions.jsonl').open() as f:decisions=[json.loads(line) for line in f if line.strip()]
    segmented_audit=audit_decisions(decisions,models,cfg,budget['reserve_bytes'])
    held=[r for r in decisions if r['retention_hold']]
    segmented_audit['retention_hold']=dict(ticks=len(held),first_elapsed_s=held[0]['elapsed_s'] if held else None,
        emergency_ticks=sum(r['emergency_deficit'] for r in decisions),
        explanation='prediction deficit latches all backgrounds frozen until foreground exits; actual reserve plus observed reaction growth remains monitored')
    indexed={r['tick']:r for r in decisions}
    for e in freezes:
        if e.get('reason')!='approved_next_segment':continue
        d=indexed.get(e['decision_tick'])
        if not d or e['operation'] not in d['resume'] or e['requested_monotonic_ns']/1e9>=d['leases'].get(e['operation'],0):
            segmented_audit['errors'].append(dict(operation=e['operation'],reason='thaw lacks an unexpired matching lease'))

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
serial_curve_audit=None
priority_audit=None
if serial_curves:
    errors=[]
    reference=Path(plan['serial_run'])
    for rel,expected in plan['serial_hashes'].items():
        if sha(reference/rel)!=expected:errors.append('serial input hash differs: '+rel)
    if priority_mode:
        from priority_policy import audit_decisions
        checkpoint=summary['runtime_policy']['confirmed_checkpoint_ns']
        priority_audit=audit_decisions(root,plan,freezes,checkpoint)
        priority_audit['errors'].extend(errors)
        if checkpoint is not None:
            marker=plan['priority_checkpoint']
            event=by.get(marker['event'],{})
            if (event.get('monotonic_ns')!=checkpoint or event.get('returncode')!=0
                or event.get('pid')!=by.get(marker['identity_event'],{}).get('pid')):
                priority_audit['errors'].append('checkpoint does not match successful process exit')
if serial_curves and not priority_mode:
    high_exit=by['HIGH_INSTANCE_EXIT']['monotonic_ns'];fg_end=fg_task['empty_confirmed_ns']
    if summary['runtime_policy']['confirmed_high_exit_ns']!=high_exit:
        errors.append('observed high-instance exit differs from release barrier')
    for op in ('xz','table','array'):
        resumes=[e for e in freezes if e['operation']==op and e['action']=='resume']
        if len(resumes)!=1:
            errors.append(op+' does not have exactly one resume')
            continue
        e=resumes[0];tail_release=e['reason']=='serial_curve_tail_release'
        earliest=high_exit if tail_release else fg_end+round(releases.get(op,0)*1e9)
        check=e['admission']
        if e['requested_monotonic_ns']<earliest or (tail_release and op!='xz'):
            errors.append(op+' resumed before its barrier')
        if e['reason'] not in ('serial_curve_tail_release','offline_native_continuation'):
            errors.append(op+' unknown resume reason')
        if not check['allowed'] or check['available_bytes']<check['required_bytes']:
            errors.append(op+' resume budget denied')
        if tail_release and check.get('confirmed_high_exit_ns')!=high_exit:
            errors.append('XZ tail admission lacks matching exit evidence')
    start,end=(by[k]['monotonic_ns'] for k in ('POST_CLOSE_REVIEW_START','POST_CLOSE_REVIEW_DONE'))
    tail_charge=[int(r['memory_current_bytes']) for r in curves['foreground_krita']
                 if start<=int(r['monotonic_ns'])<=end]
    xz=tasks['xz']
    overlap=max(0,min(fg_end,xz['empty_confirmed_ns'])-xz['actual_start_ns'])/1e9
    serial_curve_audit=dict(errors=errors,high_exit_homepage_s=(high_exit-t0)/1e9,
        foreground_tail_charge_GiB=[min(tail_charge)/2**30,max(tail_charge)/2**30],
        xz_execution_overlap_s=overlap)
    progress_path=root/'xz_tail_progress.json'
    if progress_path.exists():
        progress=json.loads(progress_path.read_text())
        stamp=progress['sample_monotonic_ns']
        if (start<=stamp<=end and xz['actual_start_ns']<=stamp<fg_end
            and progress['foreground_populated_before'] and progress['foreground_populated_after']
            and 0<progress['input_offset_bytes']<=progress['input_total_bytes']
            and progress['compressed_output_bytes']>0):
            serial_curve_audit['xz_progress_during_review']=progress

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
freezer_proofs_ok=all(not p['transition_errors'] and p['frozen_cpu_delta_usec']<1000 and
                      (run_on_submit or (p['freeze_confirmed'] and p['resume_confirmed'] and p['frozen_sample_count']>0))
                      for p in proofs.values())
success=summary['status']=='EXECUTED' and len(tasks)==4 and all(r['success'] for r in tasks.values()) and summary['all_groups_empty'] and summary['global_oom_kill_delta']==0 and not any(cg_oom.values()) and journal.returncode==0 and not oom and no_swap and swap_restoration['restored'] and not summary['collector']['errors'] and not ledger_errors and freezer_proofs_ok and (segmented_audit is None or bool(segmented_audit['rows']) and not segmented_audit['errors']) and (offline_audit is None or not offline_audit['errors']) and (serial_curve_audit is None or not serial_curve_audit['errors']) and (priority_audit is None or not priority_audit['errors'])
realtime_audit=None
if realtime_mode:
    from realtime_audit import audit
    try:realtime_audit=audit(root,plan,summary,freezes)
    except (OSError,ValueError,KeyError,TypeError) as error:
        realtime_audit=dict(errors=[repr(error)],ticks=0,freeze_count=0)
    success=success and not realtime_audit['errors']
result=dict(success=success,tasks=tasks,output_verification=verification,input_files_unchanged=unchanged,freezer_proofs=proofs,
    total_from_homepage_s=summary['total_from_homepage_s'],total_from_first_launch_s=summary['total_from_first_launch_s'],global_oom_kill_delta=summary['global_oom_kill_delta'],cgroup_oom_kill=cg_oom,
    swap_zero_all_formal_samples=no_swap,swap_restoration=swap_restoration,kernel_journal_read_ok=journal.returncode==0,kernel_oom_records=oom,
    independent_ledger_recheck=None if priority_mode or realtime_mode else dict(rows=len(ledger),errors=ledger_errors,native_status=plan['native']['status'],optimality_proven=plan['native']['status']=='OPTIMAL',role='Table and Array continuation after foreground exit' if serial_curves else 'whole-job reference; segmented execution is audited separately'),segmented_decision_audit=segmented_audit,
    sampling=summary['collector'],source_kind=plan['source_kind'],baseline_rerun=False,review_source_sha256=sha(__file__),foreground_background_thawed_overlap_s=overlap_with_foreground,
    offline_plan_audit=offline_audit,serial_curve_audit=serial_curve_audit,priority_audit=priority_audit,
    optimization_success=success and (summary['total_from_first_launch_s']<plan['reference']['total_s'] if serial_curves else bool(offline_audit and offline_audit['real_xz_progress_while_foreground_alive'])),
    system_min_available_GiB=min(int(r['mem_available_bytes']) for r in system)/2**30,system_pressure_peak_GiB=max(int(r['pressure_used_bytes']) for r in system)/2**30)

import matplotlib;matplotlib.use('Agg');import matplotlib.pyplot as plt
colors=dict(foreground_krita='tab:blue',xz='tab:orange',raster_fft='tab:orange',table='tab:green',array='tab:red')
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
title='Real-time priority freezer' if realtime_mode else ('Freezer plan from measured serial curves' if serial_curves else 'Independent-prior freezer experiment')
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
if realtime_mode:
    result.update(realtime_audit=realtime_audit, optimization_success=None)
    report=f"""# 实时反馈分级冻结

四项任务及调度校验通过 **{success}**。从前台启动到整批结束用时 **{summary['total_from_first_launch_s']:.3f} 秒**。

|任务|实际提交（首页后秒）|冻结（秒）|执行跨度（秒）|cgroup 采样峰值（GiB）|成功|
|---|---:|---:|---:|---:|---|
{table}

- 首次实际执行均在分配门放行之后。实测冻结请求须晚于任务自身的 `task_start`，前台始终受保护。
- 有效现场决策 {realtime_audit['ticks']} 次，冻结 {realtime_audit['freeze_count']} 次。复核错误为 {realtime_audit['errors']}。
- 最低 `MemAvailable` 为 {result['system_min_available_GiB']:.3f} GiB。全局 OOM kill 增量为 {summary['global_oom_kill_delta']}。正式测量无 Swap 校验为 {no_swap}，原 Swap 恢复为 {swap_restoration['restored']}。

[验证结果](validation.json) · [现场决策](realtime_decisions.jsonl) · [内存与执行曲线](freezer_memory.png)
"""
    (root/'report.md').write_text(report,encoding='utf-8')
    save('validation.json',result)
    print(json.dumps(dict(success=success,audit=realtime_audit)))
    raise SystemExit(0 if success else 1)
if priority_mode:
    serial_total=plan['reference']['total_s']
    measured=summary['total_from_first_launch_s']
    result['serial_comparison']=dict(serial_s=serial_total,freezer_s=measured,shorter_s=serial_total-measured)
    serial_label='已有同条件串行轮'
    if 'raster_reference' in plan:
        serial_label='按实测单任务耗时换算的串行参考'
        result['serial_comparison']['scope']=plan['reference']['scope']
        contexts=root/'raster_freeze_context.json'
        result['raster_freeze_context']=json.loads(contexts.read_text()) if contexts.exists() else []
    else:
        xz=tasks['xz']
        input_size=provenance['xz']['manifest'].get('size_bytes')
        result['xz_input_mib_per_thawed_second']=(input_size/2**20/xz['unfrozen_wall_s']
                                                if input_size and xz['unfrozen_wall_s'] else None)
    start_description=('后台按提交偏移直接执行，运行中按压力决定冻结。'
                       if run_on_submit else '后台按提交偏移先冻结，预算稳定通过后开始执行。')
    report=f"""# 按内存压力分级的冻结并发

四项任务及输出校验通过 **{success}**。本轮总耗时 {measured:.3f} 秒，{serial_label}为 {serial_total:.3f} 秒。

|任务|实际提交（首页后秒）|冻结（秒）|执行跨度（秒）|cgroup 采样峰值（GiB）|成功|
|---|---:|---:|---:|---:|---|
{table}

- {start_description}
- 后台与前台重叠的解冻时间（秒）为 {overlap_with_foreground}。
- 复核了 {priority_audit['ticks']} 次预算决策和 {priority_audit['memory_high_writes']} 次软限额写入。压力冻结确认最长 {priority_audit['max_pressure_freeze_ms']:.3f} ms。审计错误为 {priority_audit['errors']}。
- 最低 MemAvailable 为 {result['system_min_available_GiB']:.3f} GiB。全局 OOM kill 增量为 {summary['global_oom_kill_delta']}。正式样本 Swap 为零的校验为 {no_swap}，系统 Swap 恢复为 {swap_restoration['restored']}。

[验证结果](validation.json) · [预算和曲线来源](planning/plan.json) · [内存与执行曲线](freezer_memory.png)
"""
    (root/'report.md').write_text(report,encoding='utf-8')
    save('validation.json',result)
    print(json.dumps(dict(success=success,comparison=result['serial_comparison'],audit=priority_audit)))
    raise SystemExit(0 if success else 1)
if serial_curves:
    serial_total=plan['reference']['total_s']
    measured=summary['total_from_first_launch_s']
    difference=serial_total-measured
    baseline_tasks=plan['reference']['task_duration_s']
    result['serial_comparison']=dict(serial_s=serial_total,freezer_s=measured,shorter_s=difference,
                                     shorter_percent=100*difference/serial_total)
    xz=tasks['xz']
    if xz['empty_confirmed_ns']==max(t['empty_confirmed_ns'] for t in tasks.values()):
        xz_seconds=xz['unfrozen_wall_s']
        parts=dict(foreground_duration_difference_s=baseline_tasks['foreground_krita']-fg_task['execution_wall_s'],
                   xz_duration_difference_s=baseline_tasks['xz']-xz_seconds,
                   serial_short_tasks_and_handoffs_s=serial_total-baseline_tasks['foreground_krita']-baseline_tasks['xz'],
                   xz_lead_at_foreground_end_s=(fg_task['empty_confirmed_ns']-xz['release_confirmed_ns'])/1e9)
        if abs(sum(parts.values())-difference)<.001:
            result['serial_comparison']['difference_decomposition']=parts
    tail=serial_curve_audit['foreground_tail_charge_GiB']
    progress=serial_curve_audit.get('xz_progress_during_review')
    progress_note=''
    if progress:
        progress_note=(f"中压浏览期间的一次进度采样显示，XZ 已读入 "
                       f"{progress['input_offset_bytes']/2**20:.2f} MiB，已写出 "
                       f"{progress['compressed_output_bytes']/2**20:.2f} MiB 压缩数据。")
    report=f"""# 第二版冻结并发 · 串行曲线重规划

四项任务及输出校验通过 **{success}**。两轮均从前台自动化启动计至最后一个任务的 cgroup 确认为空，工作负载计时包含等待与交接。

|策略|总耗时（秒）|全局 OOM kill 增量|
|---|---:|---:|
|无 Swap 串行|{serial_total:.3f}|0|
|无 Swap 冻结并发|{measured:.3f}|{summary['global_oom_kill_delta']}|

串行减去并发的耗时差为 **{difference:.3f} 秒（{100*difference/serial_total:.2f}%）**。XZ 与前台的实测执行重叠为 **{serial_curve_audit['xz_execution_overlap_s']:.3f} 秒**。{progress_note}单轮耗时还包含各任务自身时长波动，拆分见验证 JSON。

|任务|实际提交（首页后秒）|冻结（秒）|执行墙钟（秒）|cgroup 采样峰值（GiB）|成功|
|---|---:|---:|---:|---:|---:|
{table}

- 模型来源为同条件无 Swap 串行的四条曲线。所有后台先在分配门前冻结。XZ 恢复须等待高压 Krita 实例真正退出并通过现场内存检查，Table 和 Array 须等待整个前台 cgroup 为空。串行轨迹的前台峰附近采用 1.50 GiB 前台单独运行保护线，后台放行后采用原 11.6% 预留及现场增长保护。
- 前台配置、素材及三项后台输入均和串行一致。90 秒中压浏览的前台 charge 范围为 {tail[0]:.3f}–{tail[1]:.3f} GiB。
- 全部正式样本 SwapTotal 为 0 的校验为 {no_swap}，系统 Swap 恢复为 {swap_restoration['restored']}。逐任务 OOM kill 为 {cg_oom}，内核 OOM 日志记录数为 {len(oom)}。
- 最低 MemAvailable 为 {result['system_min_available_GiB']:.3f} GiB，整机压力峰值为 {result['system_pressure_peak_GiB']:.3f} GiB。最大采样间隔 {summary['collector']['max_gap_s']:.4f} 秒。
- 三项后台的实际冻结、恢复和冻结期间 CPU 核对见验证 JSON。前台退出后原生账本复算 {len(ledger)} 个时槽，发现 {len(ledger_errors)} 项差异。事件与恢复核对错误为 {serial_curve_audit['errors']}。

[并发内存与执行曲线](freezer_memory.png) · [各任务曲线](freezer_tasks.png) · [验证结果](validation.json) · [规划及曲线来源](planning/plan.json)
"""
    (root/'report.md').write_text(report,encoding='utf-8')
    save('validation.json',result)
    print(json.dumps(dict(success=success,comparison=result['serial_comparison'],
                         oom_kill=summary['global_oom_kill_delta'],audit=serial_curve_audit),ensure_ascii=True))
    raise SystemExit(0 if success else 1)
(root/'report.md').write_text('''# 独立曲线规划的冻结并发实测

本轮成功：**%s**。从首页 T0 计 **%.3f 秒**，从前台动作脚本启动计 **%.3f 秒**。总耗时包含冻结等待和交接，不含事前输入检查/规划和事后校验/绘图。

|任务|实际提交：首页后 s|确认冻结时长 s|实际执行墙钟 s|cgroup采样峰值 GiB|成功|
|---|---:|---:|---:|---:|---|
%s

- 现有9000×9000、45张PNG和1350秒前台定时自动化保持；后台素材、参数保持，输入哈希前后一致：%s。
- 所有正式系统样本 SwapTotal=0：%s；实验后原Swap恢复：%s。
- 全局 oom_kill 增量：%s；逐任务 oom_kill：%s；内核读取成功：%s，本轮OOM记录 %d 条。不同scope计数不相加。
- 最低 MemAvailable %.6f GiB，RAM-MemAvailable 峰值 %.6f GiB。
- 50ms轻量采样：平均间隔 %.6fs，最大间隔 %.6fs；每组字段保留读取起止，批次单独记录，不在采集环中读smaps。
- 三项后台的冻结、恢复均以cgroup.events确认，冻结区间CPU增量和样本数见 validation.json。
- 分段模式存在时，逐次核对所有冻结/恢复配对、逐条重放预算决策，并检查每次恢复有未到期的对应许可；解冻累计运行时间另存unfrozen_wall_s，execution_wall_s为首次执行至退出跨度，可能包含中途冻结。
- 名义偏移来自已有四条独立曲线；理论任务记账峰值 %.6f GiB，不是实测物理内存峰值。没有重跑无冻结基线。
- 原生Oracle规划器状态 %s；Python独立复算了全部 %d 个预算时槽。可行不等于已经证明最优。
- 规划使用独立曲线500ms采样上包络、1.05倍需求、已有轮次退出驻留值及显式未知尾段保守上界。来源类型始终是 MEASURED_INDEPENDENT_PRIOR，不冒充完整并发实测画像。
- 实际恢复还须现场余量覆盖前台可能增长、运行后台可能增长、候选需求和11.6%% RAM预留。模型结束不代表运行任务退出，不预支其释放；延后原因保存在events.jsonl。
- 分段模式下，原生完整任务计划只作参考，实际允许早于参考放行时刻、但不早于名义提交；运行以segment_decisions.jsonl中的短执行许可、未来前台与冻结驻留预算及内核确认日志为准。新策略尚未实机验证前，不能沿用旧轮次的PASS。
- 前台成功指既定定时窗口、八阶段通过和正常退出，import_layers_verified=false，不声称自动验证46层导入完成。
- memory.current包含文件缓存；整机可用余量、任务记账和PSS不是同一指标。本轮只证明该素材、参数和环境下的效果，不声称任意负载均不会OOM。
- validation.json逐项给出先验模型峰值、实测峰值比值以及匿名/文件记账峰值。超过先验时保留偏差，不把实测改写为预测值；不同缓存初态可影响任务文件记账，不能单凭总current归因于匿名需求增长。
'''%(success,summary['total_from_homepage_s'],summary['total_from_first_launch_s'],table,unchanged,no_swap,swap_restoration['restored'],summary['global_oom_kill_delta'],cg_oom,journal.returncode==0,len(oom),result['system_min_available_GiB'],result['system_pressure_peak_GiB'],summary['collector']['mean_interval_s'],summary['collector']['max_gap_s'],plan['alignment']['theoretical_peak_GiB'],plan['native']['status'],len(ledger)))
save('validation.json',result)
print(json.dumps(dict(success=success,tasks={op:{k:v[k] for k in ['execution_wall_s','sampled_peak_GiB','success']} for op,v in tasks.items()},total_s=summary['total_from_homepage_s'],oom_kill=summary['global_oom_kill_delta'])))
