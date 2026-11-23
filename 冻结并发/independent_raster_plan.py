"""Build a raster-scene priority plan from one validated independent capture per task."""

import csv
import json
import math

from independent_plan import envelope, save
from memory_prediction import read_events,reference_markers
from serial_curve_plan import load, priority_settings


TASKS = ('foreground_krita', 'raster_fft', 'array', 'table')


def validate_inputs(batch, foreground_run, raster_run, provenance):
    status = load(batch / 'collection_status.json')
    if (not status['finished'] or status['stage'] != 'finished'
            or not status['tasks']['krita']['valid']
            or not all(status['tasks'][op]['returncode'] == 0 for op in TASKS[1:])
            or (foreground_run / 'summary.json').resolve() !=
            (batch / status['tasks']['krita']['summary']).resolve()
            or raster_run.resolve() != (batch / 'raster_fft').resolve()):
        raise ValueError('all four captures must belong to the same completed independent batch')
    for op in ('array', 'table'):
        metadata, = (batch / op).glob('*/*/metadata.json')
        row = load(metadata)
        if (not row['success'] or not row['verified'] or not row['cleanup_ok']
                or row['input_manifest'] != provenance[op]['manifest']):
            raise ValueError(f'independent {op} capture does not match the current workload')


def make_plan(batch, foreground_run, out, memtotal, provenance, config, digest):
    profiles = load(batch / 'curves/peak_summary.json')
    if not profiles['isolated_nonoverlap_verified']:
        raise ValueError('reference capture windows overlap')
    aliases = {'foreground_krita': 'krita', 'raster_fft': 'raster_fft', 'array': 'array', 'table': 'table'}
    settings = priority_settings(config)
    fixed = 'reserve_bytes' in settings['freeze_prediction']
    priorities = dict(settings['task_priorities'])
    xz_priority = priorities.pop('xz', 0)
    priorities.setdefault('raster_fft', xz_priority)
    settings['task_priorities'] = priorities
    models, peaks, durations, files, curves = {}, {}, {}, {}, {}
    for op, alias in aliases.items():
        record = profiles['metrics'][alias]
        path = batch / 'curves' / (alias + '.csv')
        with path.open(encoding='utf-8', newline='') as stream:
            samples = [(float(row['elapsed_s']), int(row['memory_current_bytes']), int(row['anonymous_bytes']))
                       for row in csv.DictReader(stream)]
        points = [(t, total) for t, total, _ in samples]
        duration = record['duration_s']
        if (not record['valid'] or record['missing_samples'] or record['max_sample_swap_bytes']
                or len(points) != record['samples'] or len(points) < 2
                or points[0][0] < 0 or points[0][0] > .5 or points[-1][0] > duration
                or any(not math.isfinite(t) or total < 0 or anon < 0 for t, total, anon in samples)
                or any(a[0] >= b[0] or b[0] - a[0] > .5 for a, b in zip(points, points[1:]))):
            raise ValueError(f'invalid independent curve for {op}')
        peak = max(points, key=lambda row: row[1])
        if peak != (record['peak_elapsed_s'], record['peak_bytes']):
            raise ValueError(f'independent peak differs from its curve for {op}')
        curves[op] = points
        peaks[op] = peak
        durations[op] = duration
        # The first sample observed after release anchors the initial bin.
        active = [(0., points[0][1]), *points] if points[0][0] > 0 else points
        models[op] = envelope(active, duration, points[-1][1], factor=1.0 if fixed else 1.05)
        if fixed:
            anon_track = [(t, anon) for t, _, anon in samples]
            if anon_track[0][0] > 0:
                anon_track.insert(0, (0., anon_track[0][1]))
            models[op]['anonymous_curve'] = envelope(anon_track, duration, anon_track[-1][1], factor=1.0)
            if op == 'foreground_krita':
                phases = foreground_run / 'krita/phase-events.jsonl'
            elif op == 'raster_fft':
                phases = batch / op / 'phases.jsonl'
            else:
                phases, = (batch / op).glob('*/*/phase_trace.jsonl')
            models[op]['phase_markers_s'] = reference_markers(
                op, read_events(phases), record['origin_monotonic_ns'], duration)
            files[str(phases.relative_to(batch))] = digest(phases)
        files[str(path.relative_to(batch))] = digest(path)

    target = peaks['foreground_krita'][0]
    offsets = {op: round(target - time, 9) for op, (time, _) in peaks.items()}
    if any(offset < 0 for offset in offsets.values()):
        raise ValueError('peak alignment would require a pre-homepage background start')
    checkpoint = settings.get('foreground_checkpoint')
    marker = {}
    if checkpoint is not None:
        events = foreground_run / 'krita/phase-events.jsonl'
        by_kind = {row['kind']: row for row in map(json.loads, events.read_text(encoding='utf-8').splitlines())
                   if row.get('kind')}
        start = by_kind[checkpoint['identity_event']]['monotonic_ns']
        exit_event = by_kind[checkpoint['event']]
        age = (exit_event['monotonic_ns'] - start) / 1e9
        if not 0 <= age < durations['foreground_krita'] or exit_event.get('returncode') != 0:
            raise ValueError('invalid foreground checkpoint in the independent capture')
        tail = max(charge for t, charge in curves['foreground_krita'] if t >= age)
        marker['priority_checkpoint'] = dict(checkpoint, reference_age_s=age,
                                             peak_bytes=tail if fixed else math.ceil(1.05 * tail) + config['model_error_bytes'])
        files[str(events.relative_to(batch))] = digest(events)

    for name in ('collection_status.json', 'curves/peak_summary.json'):
        files[name] = digest(batch / name)
    floor = load(foreground_run / 'config.snapshot.json')['safety']['min_available_bytes']
    plan = dict(schema='oomlab-priority-freezer-v1', execution_mode='priority', background_start='run_on_submit',
                source_kind='MEASURED_INDEPENDENT_CURVES', independent_run=str(batch), independent_hashes=files,
                alignment=dict(offsets_s=offsets, target_s=target,
                               sampled_peak_times_s={op: t for op, (t, _) in peaks.items()},
                               summed_at_aligned_peaks_bytes=sum(size for _, size in peaks.values())),
                models=models, priority=settings, raster_reference=provenance['raster_fft'],
                priority_peaks_bytes={op: m['peak_bytes'] + (0 if fixed else config['model_error_bytes'])
                                      for op, m in models.items()},
                budget=dict(memtotal_bytes=memtotal, reserve_bytes=settings['freeze_prediction']['reserve_bytes']
                            if fixed else math.ceil(memtotal * .116),
                            foreground_only_floor_bytes=floor,
                            emergency_floor_bytes=settings.get('emergency_floor_bytes', floor)),
                reference=dict(task_duration_s=durations), **marker)
    out.mkdir(parents=True, exist_ok=True)
    save(out / 'plan.json', plan)
    return plan
