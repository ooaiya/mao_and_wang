"""Replan the segmented executor from a successful no-Swap serial trace."""
import csv
import json
import math
import statistics
from pathlib import Path

from independent_plan import OPS, align, envelope, save, sha
from memory_prediction import read_events,reference_markers
from offline_plan import continuation

GIB=2**30
MIB=2**20


def load(path):
    return json.loads(path.read_text(encoding='utf-8'))


def priority_settings(config):
    settings=dict(config['priority'])
    settings['resume_stable_s']=config['resume_stable_s']
    fixed='reserve_bytes' in settings.get('freeze_prediction',{})
    if not fixed:
        settings.update({key:config[key] for key in ('history_s','rate_window_s','rate_multiplier','reaction_s')})
    if 'freeze_prediction' in settings:
        settings['freeze_prediction']=dict(settings['freeze_prediction'],
            confirmation_s=config['freeze_timeout_s']+config['guard_interval_s'])
        if fixed:
            settings['freeze_prediction'].setdefault('reserve_foreground_peak', True)
        else:
            settings['freeze_prediction']['growth_margin_bytes']=config['model_error_bytes']
    return settings


def make_serial_plan(run,out,memtotal,live_pressure,binary,config,priority=False):
    run=Path(run)
    summary=load(run/'summary.json')
    review=load(run/'validation.json')
    if (not review['success'] or not review['strict_serial']
        or review['sampled_swap_totals_bytes']!=[0] or review['sampling']['max_gap_s']>.5):
        raise ValueError('a verified, complete no-Swap serial run is required')
    tasks=summary['tasks']
    gui=[json.loads(line[12:]) for line in (run/'foreground_krita/process.log').read_text(encoding='utf-8').splitlines()
         if line.startswith('@@OOM_EVENT ')]
    events={e['kind']:e for e in gui if 'kind' in e}
    homepage=events['KRITA_PROCESS']['monotonic_ns']
    checkpoint=config.get('priority',{}).get('foreground_checkpoint') if priority else None
    stage_event=checkpoint['event'] if checkpoint else (None if priority else 'HIGH_INSTANCE_EXIT')
    high_exit=events.get(stage_event,{}).get('monotonic_ns')
    fg_end=tasks['foreground_krita']['empty_confirmed_ns']
    points={op:[] for op in tasks}
    anonymous={op:[] for op in tasks}
    ends={op:[] for op in tasks}
    fixed=priority and 'reserve_bytes' in config['priority'].get('freeze_prediction',{})
    with (run/'task_memory.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            op=row['operation'];stamp=int(row['monotonic_ns']);task=tasks[op]
            start=homepage if op=='foreground_krita' else task['start_ns']
            charge=int(row['memory_current_bytes'])
            if start<=stamp<=task['empty_confirmed_ns']:
                points[op].append(((stamp-start)/1e9,charge))
                if fixed:
                    anonymous[op].append(((stamp-start)/1e9,int(row['stat_anon_bytes'])))
            if task['empty_confirmed_ns']<=stamp<=task['empty_confirmed_ns']+500_000_000:
                ends[op].append(charge)
    for op,curve in points.items():
        if len(curve)<2 or curve[0][0]>.5:raise ValueError('missing task curve: '+op)
        curve.insert(0,(0.,curve[0][1]))
    models={op:envelope(curve,(tasks[op]['empty_confirmed_ns']-
             (homepage if op=='foreground_krita' else tasks[op]['start_ns']))/1e9,
             max(ends[op],default=curve[-1][1]),factor=1.0 if fixed else 1.05)
            for op,curve in points.items()}
    phase_files=[]
    if fixed:
        for op,track in anonymous.items():
            track.insert(0,(0.,track[0][1]))
            start=homepage if op=='foreground_krita' else tasks[op]['start_ns']
            duration=(tasks[op]['empty_confirmed_ns']-start)/1e9
            models[op]['anonymous_curve']=envelope(track,duration,track[-1][1],factor=1.0)
            if op=='foreground_krita':
                rows=gui
            else:
                phase_file=f'{op}/phase_trace.jsonl'
                if not (run/phase_file).is_file():
                    continue
                phase_files.append(phase_file)
                rows=read_events(run/phase_file)
            models[op]['phase_markers_s']=reference_markers(op,rows,start,duration)
    alignment=align(points,{'backgrounds':{'xz':{'durations_s':[tasks['xz']['duration_s']]}}})
    if min(alignment['offsets_s'][op] for op in OPS)<0:raise ValueError('negative background offset')
    fg_system=[];tail=[];post=[]
    with (run/'system_memory.csv').open(encoding='utf-8',newline='') as stream:
        for row in csv.DictReader(stream):
            stamp=int(row['monotonic_ns']);used=int(row['pressure_used_bytes'])
            if homepage<=stamp<=fg_end:fg_system.append(used)
            if high_exit is not None and high_exit<=stamp<=fg_end:tail.append(used)
            if fg_end<stamp<=tasks['xz']['start_ns']+4_000_000_000:post.append(used)
    if not fg_system:raise ValueError('missing foreground pressure observations')
    reserve=config['priority']['freeze_prediction']['reserve_bytes'] if fixed else math.ceil(memtotal*.116)
    waiting=16*MIB
    # Check that the foreground-only reference fits its emergency floor.
    fg_floor=load(run/'foreground_config.json')['safety']['min_available_bytes']
    live_adjust=max(0,live_pressure-statistics.median(fg_system[:100]))
    floor_predicted=memtotal-max(fg_system)-3*waiting-math.ceil(live_adjust)
    if floor_predicted<fg_floor:raise ValueError('foreground-only phase exceeds its floor with waiting tasks')
    evidence=('summary.json','validation.json','system_memory.csv','task_memory.csv',
              'foreground_krita/process.log','foreground_config.json','foreground_assets.json','input_provenance.json',
              *phase_files)
    if priority:
        settings=priority_settings(config)
        records=dict(schema='oomlab-priority-freezer-v1',execution_mode='priority',background_start='run_on_submit',
            source_kind='MEASURED_SERIAL_CURVES',serial_run=str(run),serial_hashes={name:sha(run/name) for name in evidence},
            alignment=alignment,models=models,priority=settings,
            budget=dict(memtotal_bytes=memtotal,reserve_bytes=reserve,foreground_only_floor_bytes=fg_floor,
                        emergency_floor_bytes=settings.get('emergency_floor_bytes',fg_floor)),
            reference=dict(total_s=summary['total_workload_wall_s'],
                           task_duration_s={op:t['duration_s'] for op,t in tasks.items()}),
            priority_peaks_bytes={op:model['peak_bytes']+(0 if fixed else config['model_error_bytes'])
                                  for op,model in models.items()})
        if high_exit is not None:
            start=(high_exit-homepage)/1e9
            remaining=[charge for age,charge in points['foreground_krita'] if age>=start]
            if remaining:
                records['priority_checkpoint']=dict(**checkpoint,
                    peak_bytes=max(remaining) if fixed else math.ceil(1.05*max(remaining))+config['model_error_bytes'])
                if 'freeze_prediction' in settings:
                    records['priority_checkpoint']['reference_age_s']=start
        Path(out).mkdir(parents=True,exist_ok=True)
        save(Path(out)/'plan.json',records)
        return records
    if not tail or not post:raise ValueError('missing serial system-pressure phase')
    tail_upper=math.ceil(max(tail)*1.05+live_adjust)
    headroom=64*MIB+config['model_error_bytes']
    required=tail_upper+models['xz']['peak_bytes']+reserve+3*waiting+headroom
    if required>memtotal:raise ValueError('full XZ peak cannot fit in the foreground tail')
    base=math.ceil(max(live_pressure,max(post)))
    if base+3*waiting+reserve+sum(models[op]['peak_bytes'] for op in OPS)>memtotal:
        raise ValueError('all background peaks do not fit after the foreground')
    native=continuation(models,memtotal,base,reserve,waiting,binary,out)
    records=dict(
        schema='oomlab-serial-curve-freezer-v2',source_kind='MEASURED_SERIAL_CURVES',
        serial_run=str(run),
        serial_hashes={name:sha(run/name) for name in ('summary.json','validation.json','system_memory.csv',
                     'task_memory.csv','foreground_krita/process.log','foreground_config.json','foreground_assets.json',
                     'input_provenance.json')},
        alignment=alignment,models=models,continuation=native,native=native['native'],
        budget=dict(memtotal_bytes=memtotal,reserve_bytes=reserve,waiting_per_task_bytes=waiting,
                    base_pressure_bytes=base,foreground_only_floor_bytes=fg_floor,
                    predicted_foreground_only_available_bytes=floor_predicted,
                    tail_system_upper_bytes=tail_upper,tail_headroom_bytes=headroom,
                    tail_with_full_xz_and_reserve_bytes=required,
                    observed_foreground_min_available_bytes=memtotal-max(fg_system)),
        schedule=dict(xz='confirmed HIGH_INSTANCE_EXIT, then live admission',
                      table='confirmed foreground cgroup empty, then native offset and live admission',
                      array='confirmed foreground cgroup empty, then native offset and live admission'),
        reference=dict(total_s=summary['total_workload_wall_s'],task_duration_s={op:t['duration_s'] for op,t in tasks.items()},
                       high_exit_from_homepage_s=(high_exit-homepage)/1e9,
                       tail_after_high_exit_s=(fg_end-high_exit)/1e9),
    )
    save(Path(out)/'plan.json',records)
    return records
