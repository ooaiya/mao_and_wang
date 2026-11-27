"""Connect the three shaped workloads and their solo captures to the freezer."""

import bisect
import csv
import hashlib
import json
import math
import sys
from pathlib import Path

from .phase_events import read_events, reference_markers


WORKER = Path(__file__).resolve().parents[2] / '后台操作/曲线任务/shaped_workload.py'
sys.path.insert(0, str(WORKER.parent))
from shaped_workload import PROFILES, TIMING_FLAGS, timing_args, timing_for

TASKS = tuple(PROFILES)
FOREGROUND = 'foreground_krita'
REFERENCE_FILES = ('summary.json', 'environment.json', 'task_memory.csv', 'output.json', 'phase_trace.jsonl')


def load(path):
    return json.loads(Path(path).read_text(encoding='utf-8'))


def save(path, value):
    Path(path).write_text(json.dumps(value, indent=2, ensure_ascii=False), encoding='utf-8')


def sha(path):
    return hashlib.sha256(Path(path).read_bytes()).hexdigest()


def priority_settings(config):
    settings = dict(config['priority'])
    settings['resume_stable_s'] = config['resume_stable_s']
    prediction = dict(settings['freeze_prediction'])
    prediction['confirmation_s'] = config['freeze_timeout_s'] + config['guard_interval_s']
    prediction.setdefault('reserve_foreground_peak', True)
    settings['freeze_prediction'] = prediction
    return settings


def value(curve,t):
    if t<curve[0][0]-1e-7 or t>curve[-1][0]+1e-7:return None
    t=min(curve[-1][0],max(curve[0][0],t))
    at=bisect.bisect_right(curve,(t,float('inf')))-1
    if at==len(curve)-1:return curve[at][1]
    a,b=curve[at:at+2]
    return a[1]+(b[1]-a[1])*(t-a[0])/(b[0]-a[0])

def envelope(curve,duration,terminal,tail_bound=None,factor=1.05):
    """500 ms upper envelope; unobserved tail is a labelled conservative bound."""
    bins={}
    for t,b in curve:
        if t>=0:bins.setdefault(int(t*2),[]).append(b)
    result=[];last=curve[0][1]
    end=math.ceil(duration*2)*500
    for ms in range(0,end,500):
        vals=bins.get(ms//500,[])
        # Include both interval endpoints; observed samples bound sampled data only.
        vals+= [v for v in [value(curve,ms/1000),value(curve,(ms+500)/1000)] if v is not None]
        if ms/1000>curve[-1][0]:vals=[tail_bound if tail_bound is not None else last]
        v=math.ceil(max(vals or [last])*factor);last=v/factor
        if not result or v!=result[-1][1]:result.append([ms,v])
    result.append([end,math.ceil(terminal*factor)])
    return dict(duration_ms=end,curve=result,peak_bytes=max(v for _,v in result),terminal_bytes=result[-1][1],reference_level_scale=factor)

def provenance(batch):
    result = {}
    worker_hash = sha(WORKER)
    for op, profile in PROFILES.items():
        reference = batch / op
        summary = load(reference / 'summary.json')
        environment = load(reference / 'environment.json')
        output = load(reference / 'output.json')
        peak_bytes = profile.elements * sum(int(dtype[-1]) for dtype in profile.dtypes)
        if (summary.get('returncode') != 0 or not summary['success'] or summary['global_oom_kill_delta']
                or summary['stats']['formal_swap_total_max_bytes'] or summary['stats']['errors']
                or environment['workload_sha256'] != worker_hash or environment.get('operation') != op
                or output.get('task') != op or output.get('elements') != profile.elements
                or output.get('block_elements') != profile.block_elements
                or output.get('peak_buffer_bytes') != peak_bytes):
            raise ValueError(f'{op} needs a passing solo capture from the current shaped workload')
        timing = output['timing_s']
        if set(timing) != set(TIMING_FLAGS) or timing != timing_for(op, timing):
            raise ValueError(f'invalid timing record for {op}')
        result[op] = dict(workload_kind='shaped', worker=str(WORKER), worker_sha256=worker_hash,
                          reference_run=str(reference), timing_s=timing,
                          reference_hashes={name: sha(reference / name) for name in REFERENCE_FILES})
    return result


def command(op, python, output, prior):
    return [str(python), prior['worker'], '--task', op, '--output', str(output),
            *timing_args(prior['timing_s'])]


def reference_unchanged(prior):
    reference = Path(prior['reference_run'])
    return sha(prior['worker']) == prior['worker_sha256'] and all(
        sha(reference / name) == digest for name, digest in prior['reference_hashes'].items())


def verify(output, prior):
    if not reference_unchanged(prior):
        raise ValueError('shaped workload source or independent reference changed')
    actual = load(output / 'output.json')
    if actual != load(Path(prior['reference_run']) / 'output.json'):
        raise ValueError('shaped output differs from its independent reference')
    return dict(ok=True, method='deterministic output matches the independent reference',
                data_sha256=actual['data_sha256'])


def load_offsets(path):
    offsets = load(path)
    if (not isinstance(offsets, dict) or set(offsets) != {FOREGROUND, *TASKS}
            or any(type(seconds) not in (int, float) or not math.isfinite(seconds) or seconds < 0
                   for seconds in offsets.values())
            or offsets[FOREGROUND] != 0):
        raise ValueError('supply a nonnegative fixed offset for each shaped task and zero for Krita')
    return offsets


def read_curve(path, op, origin, finish):
    foreground = op == FOREGROUND
    scope, total, anon, swap = (('scope', 'memory_current', 'stat_anon', 'swap_current') if foreground
                                 else ('operation', 'memory_current_bytes', 'stat_anon_bytes',
                                       'memory_swap_current_bytes'))
    tag = 'krita' if foreground else op
    samples = []
    with path.open(encoding='utf-8', newline='') as stream:
        for row in csv.DictReader(stream):
            stamp = int(row['monotonic_ns'])
            if row[scope] != tag or not origin <= stamp <= finish:
                continue
            charge, anonymous = int(row[total]), int(row[anon])
            if int(row[swap]) or min(charge, anonymous) < 0:
                raise ValueError(f'invalid memory accounting in the {op} reference')
            samples.append(((stamp - origin) / 1e9, charge, anonymous))
    duration = (finish - origin) / 1e9
    if (len(samples) < 2 or samples[0][0] > .5 or duration - samples[-1][0] > .5
            or any(not 0 < b[0] - a[0] <= .5 for a, b in zip(samples, samples[1:]))):
        raise ValueError(f'incomplete curve for {op}')
    if samples[0][0] > 0:
        samples.insert(0, (0., *samples[0][1:]))
    return samples


def make_plan(batch, foreground_run, offset_path, out, memtotal, inputs, config):
    offsets = load_offsets(offset_path)
    settings = priority_settings(config)
    if 'reserve_bytes' not in settings['freeze_prediction']:
        raise ValueError('shaped workloads require the fixed predictive policy')
    priorities = settings['task_priorities']
    # Older configs list XZ instead of raster. The shaped scene has its own priority levels.
    if 'raster' in priorities:
        if any(type(priorities.get(op)) is not int for op in (FOREGROUND, *TASKS)):
            raise ValueError('set an integer priority for Krita and each shaped task')
        settings['task_priorities'] = {op: priorities[op] for op in (FOREGROUND, *TASKS)}
    else:
        settings['task_priorities'] = {FOREGROUND: priorities[FOREGROUND], **dict.fromkeys(TASKS, 0)}
    settings['freeze_prediction']['phase_search_s'] = {
        key: seconds for key, seconds in settings['freeze_prediction']['phase_search_s'].items()
        if key in ('default', FOREGROUND, *TASKS)
    }

    curves, models, durations = {}, {}, {}
    files = {str(offset_path.resolve()): sha(offset_path)}
    foreground_trace = foreground_run / 'krita/phase-events.jsonl'
    foreground_events = list(read_events(foreground_trace))
    by_kind = {row['kind']: row for row in foreground_events if 'kind' in row}
    checkpoint = settings['foreground_checkpoint']
    exit_event = by_kind[checkpoint['event']]
    if exit_event.get('returncode') != 0 or exit_event['pid'] != by_kind[checkpoint['identity_event']]['pid']:
        raise ValueError('invalid Krita checkpoint in the solo capture')
    for op in (FOREGROUND, *TASKS):
        if op == FOREGROUND:
            events_path = foreground_trace
            samples_path = foreground_run / 'samples.csv'
            origin = by_kind['KRITA_PROCESS']['monotonic_ns']
            finish = by_kind['KRITA_EXIT']['monotonic_ns']
            events = foreground_events
        else:
            reference = Path(inputs[op]['reference_run'])
            events_path = reference / 'phase_trace.jsonl'
            samples_path = reference / 'task_memory.csv'
            events = list(read_events(events_path))
            origin = next(row['monotonic_ns'] for row in events if row['event_type'] == 'task_start')
            finish = next(row['monotonic_ns'] for row in events if row['event_type'] == 'task_end')
        samples = read_curve(samples_path, op, origin, finish)
        durations[op] = (finish - origin) / 1e9
        curves[op] = [(t, charge) for t, charge, _ in samples]
        anonymous = [(t, anon) for t, _, anon in samples]
        models[op] = envelope(curves[op], durations[op], curves[op][-1][1], factor=1.)
        models[op]['anonymous_curve'] = envelope(anonymous, durations[op], anonymous[-1][1], factor=1.)
        models[op]['phase_markers_s'] = reference_markers(op, events, origin, durations[op])
        for path in (events_path, samples_path):
            files[str(path.resolve())] = sha(path)
        if op == FOREGROUND:
            checkpoint_age = (exit_event['monotonic_ns'] - origin) / 1e9
            if not 0 <= checkpoint_age < durations[op]:
                raise ValueError('Krita exit checkpoint falls outside its curve')

    knots = {t + offsets[op] for op, points in curves.items() for t, _ in points}
    target = max(sorted(knots),
                 key=lambda t: sum(value(points, t - offsets[op]) or 0 for op, points in curves.items()))
    combined = {op: value(points, target - offsets[op]) or 0 for op, points in curves.items()}
    plan = dict(schema='oomlab-priority-freezer-v1', execution_mode='priority',
                background_start='run_on_submit', source_kind='MEASURED_INDEPENDENT_CURVES',
                workload_kind='shaped', independent_run=str(batch), independent_hashes=files,
                alignment=dict(offsets_s=offsets, target_s=target, contributions_bytes=combined,
                               summed_at_aligned_peaks_bytes=sum(combined.values())),
                models=models, priority=settings,
                priority_peaks_bytes={op: model['peak_bytes'] for op, model in models.items()},
                priority_checkpoint=dict(checkpoint, reference_age_s=checkpoint_age,
                                         peak_bytes=max(charge for t, charge in curves[FOREGROUND]
                                                        if t >= checkpoint_age)),
                budget=dict(memtotal_bytes=memtotal, reserve_bytes=settings['freeze_prediction']['reserve_bytes']),
                reference=dict(task_duration_s=durations))
    out.mkdir(exist_ok=True)
    save(out / 'plan.json', plan)
    return plan
