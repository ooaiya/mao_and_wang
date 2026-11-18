"""Review a completed or OOM-truncated raster baseline without conflating cleanup and OOM."""

import csv
import json
import re
import subprocess
import sys
from bisect import bisect_right
from pathlib import Path

from raster_priority import raster_events, verify_raster
from serial_curve_plan import load


GIB = 2**30
LABELS = dict(foreground_krita='Krita', raster_fft='Raster FFT', xz='XZ', array='Array', table='Table')
OOM = re.compile(r'out of memory|oom-kill:|killed process\s+\d+', re.I)
KILL = re.compile(r'killed process\s+(\d+)\s+\((.*?)\)', re.I)


def csv_rows(path):
    with path.open(encoding='utf-8', newline='') as text:
        return list(csv.DictReader(text))


def workload_start(root, op, task, raster):
    if 'actual_start_ns' in task:
        return task['actual_start_ns']
    if op == 'raster_fft':
        return next((e['monotonic_ns'] for e in raster if e['event']=='tile_background_start'), None)
    if op != 'foreground_krita':
        return next((e['monotonic_ns'] for e in json_rows(root/op/'phase_trace.jsonl')
                     if e.get('event_type')=='task_start'), None)
    return None


def json_rows(path, prefix=''):
    if path.exists():
        with path.open(encoding='utf-8') as text:
            return [json.loads(line[len(prefix):]) for line in text if line.strip() and line.startswith(prefix)]
    return []


def kernel_evidence(root, start, end, gui):
    anchor = next(e for e in gui if 'wall_time_ns' in e and 'monotonic_ns' in e)
    wall_offset = anchor['wall_time_ns'] - anchor['monotonic_ns']
    options = ['-o', 'json', '--no-pager', '--since', f'@{(start+wall_offset)/1e9-2:.6f}',
               '--until', f'@{(end+wall_offset)/1e9+2:.6f}']
    unit = subprocess.run(['journalctl', '-u', 'oomlab-'+root.name, *options],
                          capture_output=True, text=True, timeout=30)
    (root/'unit_journal.jsonl').write_text(unit.stdout, encoding='utf-8')
    boots = {e['_BOOT_ID'] for e in json_rows(root/'unit_journal.jsonl') if e.get('_BOOT_ID')}
    if unit.returncode or len(boots) != 1:
        (root/'kernel_journal.jsonl').write_text('', encoding='utf-8')
        return False, []
    command = ['journalctl', '--boot='+boots.pop(), '-k', *options]
    log = subprocess.run(command, capture_output=True, text=True, timeout=30)
    (root/'kernel_journal.jsonl').write_text(log.stdout, encoding='utf-8')
    evidence = []
    for entry in json_rows(root/'kernel_journal.jsonl'):
        message = entry.get('MESSAGE', '')
        stamp = int(entry.get('_SOURCE_MONOTONIC_TIMESTAMP', entry['__MONOTONIC_TIMESTAMP'])) * 1000
        if start <= stamp <= end + 500_000_000 and isinstance(message, str) and OOM.search(message):
            victim = KILL.search(message)
            evidence.append(dict(monotonic_ns=stamp, message=message,
                                 victim_pid=int(victim[1]) if victim else None,
                                 victim_name=victim[2] if victim else None))
    return log.returncode == 0, evidence


def review_completed_task(root, op, task, gui, provenance):
    if task.get('returncode') != 0 or task.get('cleanup_terminated'):
        return dict(ok=False, reason='task did not complete normally')
    try:
        if op == 'raster_fft':
            return verify_raster(root/op, provenance[op])
        if op != 'foreground_krita':
            from oomlab.workloads import verify
            return verify(provenance[op]['path'], root/op)
        from oomlab_krita_collect.validation import verify_pilot_events
        verify_pilot_events(gui, load(root/'foreground_assets.json')['script_contract'])
        return dict(ok=True, method='verified Krita timed workflow and successful exit')
    except (ValueError, OSError, KeyError) as error:
        return dict(ok=False, error=str(error))


def draw(root, t0, system, curves, kills, target):
    import matplotlib
    matplotlib.use('Agg')
    from matplotlib import pyplot as plt
    fig, (top, bottom) = plt.subplots(2, 1, figsize=(11, 7), sharex=True, layout='constrained')
    variant = 'Raster' if 'raster_fft' in curves else 'XZ'
    fig.suptitle(f'{variant} baseline: swap off, no throttling or freezing', fontsize=15, fontweight='bold')
    age = lambda row: (int(row['monotonic_ns'])-t0)/1e9
    def plot(ax, rows, key, **style):
        x, y = [], []
        for row in rows:
            t = age(row)
            if x and t-x[-1] > .5:
                x.append(t)
                y.append(float('nan'))
            if int(row['read_end_ns'])-int(row['monotonic_ns']) <= 500_000_000:
                x.append(t)
                y.append(int(row[key])/GIB)
        ax.plot(x, y, **style)
    plot(top, system, 'mem_available_bytes', label='MemAvailable', color='#116b90')
    for op, rows in curves.items():
        plot(bottom, rows, 'memory_current_bytes', label=LABELS[op])
    for ax in (top, bottom):
        ax.axvline(target, color='#6b7789', linestyle=':', label='Planned alignment')
        if kills:
            ax.axvline((kills[0]['monotonic_ns']-t0)/1e9, color='#b42929', linestyle='--', label='Kernel OOM kill')
        ax.set_ylabel('GiB')
        ax.legend(loc='best', frameon=False)
        ax.grid(axis='y', alpha=.22)
    last = age(system[-1])
    bottom.set_xlim(max(0, min(last-20, target-75)), min(last+1, max(target+70, last if kills else target)))
    bottom.set_xlabel('Seconds since Krita homepage readiness')
    fig.savefig(root/'baseline_memory.png', dpi=165)
    plt.close(fig)


def review(root):
    summary = load(root/'summary.json')
    plan = load(root/'planning/plan.json')
    operations = plan['alignment']['offsets_s'].keys()
    t0 = summary['T0_monotonic_ns']
    end = summary['runtime_policy']['formal_end_monotonic_ns']
    start = min(r['created_ns'] for r in summary['tasks'].values())
    gui = json_rows(root/'foreground_krita/process.log', '@@OOM_EVENT ')
    logs_ok, kernel = kernel_evidence(root, start, end, gui)
    kills = [r for r in kernel if r['victim_pid'] is not None]
    cutoff = min(end, min((r['monotonic_ns'] for r in kernel), default=end))
    raster_log = root/'raster_fft/process.log'
    raster = list(raster_events(raster_log)) if raster_log.exists() else []
    workload_starts = {op: workload_start(root, op, task, raster)
                       for op, task in summary['tasks'].items()}
    workload_starts['foreground_krita'] = t0
    system = [r for r in csv_rows(root/'system_memory.csv') if t0 <= int(r['monotonic_ns']) and int(r['read_end_ns']) <= end]
    batches = [r for r in csv_rows(root/'sampling_batches.csv') if t0 <= int(r['start_ns'])
               and int(r['end_ns']) <= cutoff and float(r['duration_s']) <= .5]
    starts = [int(r['start_ns']) for r in batches]
    simultaneous = [{} for _ in batches]
    curves = {op: [] for op in operations}
    for row in csv_rows(root/'task_memory.csv'):
        stamp = int(row['monotonic_ns'])
        if not t0 <= stamp or int(row['read_end_ns']) > end:
            continue
        op = row['operation']
        curves[op].append(row)
        index = bisect_right(starts, stamp)-1
        started = workload_starts.get(op)
        if (index >= 0 and started is not None and started <= stamp and row['populated'] == '1'
                and int(row['read_end_ns']) <= int(batches[index]['end_ns'])):
            simultaneous[index][op] = int(row['memory_current_bytes'])
    complete = [(i, batch) for i, batch in enumerate(simultaneous) if batch.keys() == operations]
    peak = max(complete, key=lambda item: sum(item[1].values()), default=None)
    count_95 = sum(all(batch[op] >= .95*plan['models'][op]['peak_bytes'] for op in operations) for _, batch in complete)
    source = load(root/'source_provenance.json')
    sys.path.insert(0, str(Path.home()/'bg'))
    sys.path.insert(0, str(Path(source['foreground_source'])/'前台操作/前台操作自动化脚本采集'))
    provenance = load(root/'input_provenance.json')
    stamp = lambda ns: (ns-t0)/1e9
    timed = summary['runtime_policy']['background_start']=='independent_deadline_release'
    tasks = {}
    for op, task in summary['tasks'].items():
        submitted = task.get('release_confirmed_ns') if timed and op!='foreground_krita' else task['created_ns']
        actual = workload_starts[op]
        tasks[op] = dict(returncode=task.get('returncode'), cleanup_terminated=task.get('cleanup_terminated', False),
                         prepared_s=stamp(task['created_ns']), submitted_s=stamp(submitted) if submitted is not None else None,
                         actual_start_s=stamp(actual) if actual is not None else None,
                         started_before_cutoff=actual is not None and actual<cutoff,
                         end_s=stamp(task['empty_confirmed_ns']),
                         peak_GiB=max((int(r['memory_current_bytes']) for r in curves[op]), default=0)/GIB,
                         memory_events=task.get('final_memory_events'),
                         output_verification=review_completed_task(root, op, task, gui, provenance))
    flags = [record['memory_events'] or {} for record in tasks.values()]
    oom = bool(kernel or summary['global_oom_kill_delta'] or any(r.get('oom_kill') or r.get('oom') for r in flags))
    no_swap = bool(system) and all(int(r['swap_total_bytes']) == 0 for r in system)
    no_intervention = not load(root/'freeze_events.json') and not (root/'priority_decisions.jsonl').exists() and all(
        r['frozen']=='0' and json.loads(r['memory_events_json']).get('high', 0)==0 for rows in curves.values() for r in rows)
    restored = load(root/'swap_restoration.json')['restored']
    valid = logs_ok and no_swap and no_intervention and restored and not summary['collector']['errors']
    success = valid and not oom and summary['status']=='EXECUTED' and len(tasks)==4 and all(
        r['output_verification']['ok'] for r in tasks.values())
    offsets = plan['alignment']['offsets_s']
    delays = {op: (tasks[op]['submitted_s']-offsets[op]
                   if op in tasks and tasks[op]['submitted_s'] is not None else None)
              for op in operations if op!='foreground_krita'}
    timed_launch_valid = (all(delay is not None and 0 <= delay <= .25 for delay in delays.values())
                          and all(tasks[op]['started_before_cutoff'] for op in delays))
    result = dict(success=success, evidence_valid=valid, oom=oom if oom or logs_ok else None,
                  oom_scope='global' if any('global_oom' in r['message'] for r in kernel) else None,
                  global_oom_kill_delta=summary['global_oom_kill_delta'], kernel_oom_records=kernel,
                  victim_events=[dict(r, homepage_s=stamp(r['monotonic_ns'])) for r in kills],
                  kernel_journal_read_ok=logs_ok, no_swap=no_swap, no_intervention=no_intervention,
                  swap_restored=restored, tasks=tasks, planned_offsets_s=offsets,
                  launch_delay_s=delays, timed_launch_valid=timed_launch_valid,
                  lowest_available_MiB=min(int(r['mem_available_bytes']) for r in system)/2**20,
                  all_tasks_high_batches=count_95, all_tasks_populated_batches=len(complete),
                  max_complete_batch_before_oom=dict(homepage_s=stamp(int(batches[peak[0]]['start_ns'])),
                      sum_charge_GiB=sum(peak[1].values())/GIB,
                      tasks_GiB={op:charge/GIB for op, charge in peak[1].items()}) if peak else None,
                  foreground_high_exit_s=next((stamp(e['monotonic_ns']) for e in gui if e.get('kind')=='HIGH_INSTANCE_EXIT'), None),
                  raster_stages_s={e['event']:stamp(e['monotonic_ns']) for e in raster if e['event']!='tile_progress'},
                  sampler_max_gap_s=summary['collector']['max_gap_s'], summary_status=summary['status'],
                  runner_error=summary['error'], measured_duration_s=stamp(end))
    (root/'validation.json').write_text(json.dumps(result, indent=2)+'\n', encoding='utf-8')
    victim_text=''.join(f"- 首页后 {stamp(row['monotonic_ns']):.3f} s。内核杀死 {row['victim_name']}（PID {row['victim_pid']}）。\n" for row in kills)
    launch_table='\n'.join(f"| {LABELS[op]} | {offsets[op]:.3f} s | {tasks.get(op, {}).get('submitted_s')} | {tasks.get(op, {}).get('actual_start_s')} |" for op in delays)
    variant = '栅格' if 'raster_fft' in operations else 'XZ'
    report=(f'# {variant} 负载无干预基线\n\n'
            f"| 核对项 | 结果 |\n|---|---|\n| OOM | {result['oom']} |\n"
            f"| `oom_kill` 增量 | {summary['global_oom_kill_delta']} |\n| 四项均通过校验 | {success} |\n"
            f"| 最低 `MemAvailable` | {result['lowest_available_MiB']:.2f} MiB |\n"
            f"| 四任务均达参考峰值 95% 的同批采样数 | {count_95} |\n\n"
            f'{victim_text}\n以 Krita 首页就绪为 0 秒。\n\n'
            '| 后台任务 | 计算偏移 | 实际放行（秒） | 开始工作（秒） |\n|---|---:|---:|---:|\n'
            f'{launch_table}\n\n'
            f"最大采样间隔 {result['sampler_max_gap_s']:.3f} 秒。曲线在采样缺口处断开。\n\n"
            '[验证结果](validation.json) · [内核日志](kernel_journal.jsonl) · [内存曲线](baseline_memory.png)\n')
    (root/'report.md').write_text(report, encoding='utf-8')
    draw(root, t0, system, curves, kills, plan['alignment']['target_s'])
    print(json.dumps(result, ensure_ascii=True))


if __name__ == '__main__':
    review(Path(sys.argv[1]))
