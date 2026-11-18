"""Preserve incomplete trials as failures, never as short successful runs."""
import csv,hashlib,json,subprocess
from pathlib import Path

def review(root):
    root=Path(root);s=json.loads((root/'summary.json').read_text());p=json.loads((root/'planning/plan.json').read_text());t0=s.get('T0_monotonic_ns')
    events=[json.loads(line) for line in (root/'events.jsonl').read_text().splitlines() if line.strip()]
    error=next((e for e in reversed(events) if e['event_type']=='freezer_error'),None)
    end=error['actual_monotonic_ns'] if error else max(r['created_ns'] for r in s['tasks'].values())
    origin=min(r['created_ns'] for r in s['tasks'].values());systems=[];curves={op:[] for op in s['tasks']}
    with (root/'system_memory.csv').open() as f:
        for r in csv.DictReader(f):
            if (not t0 or int(r['monotonic_ns'])>=t0) and int(r['monotonic_ns'])<=end:systems.append(r)
    with (root/'task_memory.csv').open() as f:
        for r in csv.DictReader(f):
            if r['operation'] in curves:curves[r['operation']].append(r)
    tasks={}
    for op,r in s['tasks'].items():
        peak=max((int(x['memory_current_bytes']) for x in curves[op]),default=0)
        tasks[op]=dict(**r,success=False,sampled_peak_GiB=peak/2**30,actual_to_prior_peak_ratio=peak/p['models'][op]['peak_bytes'],
            outcome='not normally completed' if r.get('returncode')!=0 else 'completed before run failure')
    freezes=json.loads((root/'freeze_events.json').read_text()) if (root/'freeze_events.json').exists() else []
    proofs={op:dict(freeze_count=sum(x['operation']==op and x['action']=='freeze' for x in freezes),resume_count=sum(x['operation']==op and x['action']=='resume' for x in freezes),intervals=[],transition_errors=['trial aborted; not a complete acceptance']) for op in ['xz','table','array']}
    restored=json.loads((root/'swap_restoration.json').read_text())
    v=dict(success=False,experiment_complete=False,status=s['status'],error=s['error'],tasks=tasks,
        total_from_first_launch_s=(end-origin)/1e9,total_from_homepage_s=(end-t0)/1e9 if t0 else None,total_is_abort_latency_not_completion=True,
        global_oom_kill_delta=s['global_oom_kill_delta'],all_groups_empty=s['all_groups_empty'],swap_restoration=restored,
        swap_zero_all_formal_samples=bool(systems) and all(int(r['swap_total_bytes'])==0 for r in systems),
        system_min_available_GiB=min((int(r['mem_available_bytes']) for r in systems),default=0)/2**30,
        sampling=s['collector'],freezer_proofs=proofs,foreground_background_thawed_overlap_s=None,
        review_source_sha256=hashlib.sha256(Path(__file__).read_bytes()).hexdigest())
    (root/'validation.json').write_text(json.dumps(v,indent=2,ensure_ascii=False))
    (root/'report.md').write_text('# 分段冻结未完成轮次\n\n**本轮失败，不能作为完成四任务的性能结果。**\n\n保护中止：首页后 %.3f 秒；从自动化启动计 %.3f 秒（这是中止耗时，不是完成耗时）。\n\n原因：%s\n\n全局OOM kill增量 %s；本轮进程组已清空 %s；正式样本Swap为0 %s；原Swap恢复 %s。\n\nXZ冻结 %d 次、恢复 %d 次。Table/Array尚未提交。退出码未被旧管理器记录的字段保持未知，不补造正常完成。\n\n原始CSV、决策、内核确认、源码摘要和保护中止日志全部保留。\n'%(v['total_from_homepage_s'],v['total_from_first_launch_s'],s['error'],s['global_oom_kill_delta'],s['all_groups_empty'],v['swap_zero_all_formal_samples'],restored['restored'],proofs['xz']['freeze_count'],proofs['xz']['resume_count']))
    print(json.dumps(dict(success=False,error=s['error'],abort_elapsed_s=v['total_from_first_launch_s'])))

if __name__=='__main__':
    import sys
    review(sys.argv[1])
