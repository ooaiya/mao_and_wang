"""Execute the priority freezer with the independently measured raster replacing XZ."""

import argparse
import csv
import json
import math
import signal
from pathlib import Path

from independent_plan import envelope
from memory_prediction import read_events,reference_markers
from segmented_runner import SegmentedFreezer, digest, save, values
from serial_curve_plan import load


RASTER = 'raster_fft'
ROOT = Path(__file__).resolve().parents[1]
WORKER = ROOT / '后台操作/栅格频域任务/raster_fft.py'
REFERENCE_FILES = ('summary.json', 'environment.json', 'task_memory.csv', 'output.json', 'phases.jsonl')


def raster_events(path):
    with path.open(encoding='utf-8') as stream:
        for line in stream:
            try:
                event = json.loads(line)
            except json.JSONDecodeError:
                continue
            if 'event' in event and 'monotonic_ns' in event:
                yield event


def verify_raster(output, prior):
    reference = Path(prior['reference_run'])
    for rel, expected in prior['reference_hashes'].items():
        if digest(reference / rel) != expected:
            raise ValueError(f'raster reference changed: {rel}')
    if digest(prior['worker']) != prior['worker_sha256']:
        raise ValueError('raster worker changed')
    actual = load(output / 'output.json')
    expected = load(reference / 'output.json')
    if actual != expected:
        raise ValueError('raster output differs from the validated independent run')
    return dict(ok=True, method='full raster output digest and per-tile statistics match the independent run',
                filtered_sha256=actual['filtered_sha256'])


class RasterPriority(SegmentedFreezer):
    background_input_ops = ('table', 'array')
    background_ops = (RASTER, 'table', 'array')

    def __init__(self, args, *, predictor=None):
        policy_config = args.policy_config or Path(__file__).with_name('raster_priority_config.json')
        self.shaped_run = getattr(args, 'shaped_run', None)
        if self.shaped_run:
            from shaped_scene import TASKS
            self.background_ops = TASKS
            self.offsets = args.offsets
        super().__init__(args.output, '.', '.', policy_config, args.serial_run,
                         args.foreground_run, args.foreground_source, predictor=predictor,
                         independent_run=self.shaped_run or getattr(args, 'independent_run', None))
        self.raster_run = args.raster_run
        self.raster_alignment = args.raster_alignment
        self.freeze_contexts = []
        self.env.update(OPENBLAS_NUM_THREADS='1', OMP_NUM_THREADS='1', MKL_NUM_THREADS='1')
        settings = self.policy_config['priority']
        if settings.get('memory_high') or settings.get('emergency_floor_bytes') is not None:
            raise ValueError('raster execution does not configure memory.high or a live emergency floor')

    def background_provenance(self):
        if self.shaped_run:
            from shaped_scene import provenance
            return provenance(self.shaped_run)
        provenance = super().background_provenance()
        reference = self.raster_run
        summary = load(reference / 'summary.json')
        environment = load(reference / 'environment.json')
        result = load(reference / 'output.json')
        if (not summary['success'] or summary['global_oom_kill_delta']
                or summary['stats']['formal_swap_total_max_bytes'] or result['calibration_tiles'] is not None
                or result['pixels'] != result['side']**2 or digest(WORKER) != environment['workload_sha256']):
            raise ValueError('a complete verified no-Swap reference from this raster worker is required')
        provenance[RASTER] = dict(worker=str(WORKER), worker_sha256=digest(WORKER),
                                  reference_run=str(reference),
                                  reference_hashes={name: digest(reference / name) for name in REFERENCE_FILES},
                                  side=result['side'], sweeps=result['sweeps'])
        return provenance

    def validate_serial_inputs(self):
        if self.shaped_run:
            from shaped_scene import load_offsets
            load_offsets(self.offsets)
            return
        if self.independent_run:
            from independent_raster_plan import validate_inputs
            validate_inputs(self.independent_run, self.foreground_run, self.raster_run, self.provenance)
            return
        for name in ('foreground_config.json', 'foreground_assets.json'):
            if load(self.out / name) != load(self.serial_run / name):
                raise RuntimeError(f'foreground differs from the serial reference: {name}')
        prior = load(self.serial_run / 'input_provenance.json')
        for op in self.background_input_ops:
            if self.provenance[op] != prior[op]:
                raise RuntimeError(f'background input differs from the serial reference: {op}')

    def build_serial_plan(self, memory_info):
        if self.shaped_run:
            from shaped_scene import make_plan
            return make_plan(self.shaped_run, self.foreground_run, self.offsets, self.out / 'planning',
                             memory_info['MemTotal'], self.provenance, self.policy_config)
        if self.independent_run:
            from independent_raster_plan import make_plan
            return make_plan(self.independent_run, self.foreground_run, self.out / 'planning',
                             memory_info['MemTotal'], self.provenance, self.policy_config, digest)
        plan = super().build_serial_plan(memory_info)
        alignment = load(self.raster_alignment)
        offsets = alignment['predicted_offsets_s']
        if (set(offsets) != {'foreground_krita', *self.background_ops} or offsets['foreground_krita'] != 0
                or any(not math.isfinite(v) or v < 0 for v in offsets.values())):
            raise ValueError('invalid raster submission offsets')
        summary = load(self.raster_run / 'summary.json')
        duration = summary['duration_s']
        start = summary['t0_ns']
        with (self.raster_run / 'task_memory.csv').open(encoding='utf-8', newline='') as stream:
            samples = [((int(row['monotonic_ns']) - start) / 1e9,
                        int(row['memory_current_bytes']), int(row['stat_anon_bytes']))
                       for row in csv.DictReader(stream) if row['operation'] == RASTER]
        active = [(t, v) for t, v, _ in samples if 0 <= t <= duration]
        if (len(active) < 2 or active[0][0] > .5 or not math.isclose(duration, alignment['duration_s'])
                or max(v for _, v in active) != round(alignment['peaks_MiB']['memory_current_bytes'] * 2**20)):
            raise ValueError('raster curve does not match the offset calculation')
        active.insert(0, (0., active[0][1]))
        fixed = 'reserve_bytes' in plan['priority'].get('freeze_prediction', {})
        model = envelope(active, duration, max((v for t, v, _ in samples if t > duration), default=active[-1][1]),
                         factor=1.0 if fixed else 1.05)
        if fixed:
            anon = [(t, v) for t, _, v in samples if 0 <= t <= duration]
            if anon[0][0] > 0:
                anon.insert(0, (0., anon[0][1]))
            model['anonymous_curve'] = envelope(anon, duration, anon[-1][1], factor=1.0)
            phases = self.raster_run / 'phases.jsonl'
            model['phase_markers_s'] = reference_markers(RASTER, read_events(phases), start, duration)
        for key in ('models', 'priority_peaks_bytes'):
            del plan[key]['xz']
        plan['models'][RASTER] = model
        plan['priority_peaks_bytes'][RASTER] = model['peak_bytes'] + (0 if fixed else self.policy_config['model_error_bytes'])
        priorities = dict(plan['priority']['task_priorities'])
        priorities[RASTER] = priorities.pop('xz')
        plan['priority']['task_priorities'] = priorities
        plan['alignment'] = dict(offsets_s=offsets, target_s=alignment['chosen_target_s'],
                                 offline_evidence=alignment, evidence_sha256=digest(self.raster_alignment))
        plan['raster_reference'] = self.provenance[RASTER]
        durations = plan['reference']['task_duration_s']
        durations[RASTER] = duration
        plan['reference']['total_s'] += duration - durations.pop('xz')
        plan['reference']['scope'] = 'Estimated serial reference from the old serial run and the independent raster duration.'
        save(self.out / 'planning/plan.json', plan)
        return plan

    def command(self, op):
        if self.shaped_run and op in self.background_ops:
            from shaped_scene import command
            return command(op, self.home / 'bg/.venv/bin/python', self.out / op / 'output.json',
                           self.provenance[op])
        if op != RASTER:
            return super().command(op)
        inputs = self.provenance[op]
        return [str(self.home / 'bg/.venv/bin/python'), str(WORKER), '--side', str(inputs['side']),
                '--sweeps', str(inputs['sweeps']), '--output', str(self.out / op / 'output.json')]

    def background_start_ns(self, op):
        if op != RASTER:
            return super().background_start_ns(op)
        return next((e['monotonic_ns'] for e in raster_events(self.out/op/'process.log')
                     if e['event'] == 'tile_background_start'), None)

    def prediction_events(self, op):
        if op != RASTER:
            return super().prediction_events(op)
        path = self.out / op / 'process.log'
        return raster_events(path) if path.is_file() else ()

    def transition(self, op, frozen, *args, **kwargs):
        count = len(self.freeze_rows)
        super().transition(op, frozen, *args, **kwargs)
        if op == RASTER and frozen and len(self.freeze_rows) > count:
            stamp = self.freeze_rows[-1]['confirmed_monotonic_ns']
            stages = [e for e in raster_events(self.out/op/'process.log') if e['monotonic_ns'] <= stamp]
            stats = values(self.cm.checked(op) / 'memory.stat')
            self.freeze_contexts.append(dict(confirmed_monotonic_ns=stamp,
                anon_bytes=stats['anon'], file_bytes=stats['file'],
                last_stage=next((e for e in reversed(stages) if e['event'] != 'tile_progress'), None),
                progress=next((e for e in reversed(stages) if e['event'] == 'tile_progress'), None)))
            save(self.out / 'raster_freeze_context.json', self.freeze_contexts)


def run_cli(runner):
    parser = argparse.ArgumentParser(description=__doc__)
    for name in ('output', 'foreground-run', 'foreground-source'):
        parser.add_argument('--' + name, type=Path, required=True)
    parser.add_argument('--raster-run', type=Path)
    reference = parser.add_mutually_exclusive_group(required=True)
    reference.add_argument('--serial-run', type=Path)
    reference.add_argument('--independent-run', type=Path)
    reference.add_argument('--shaped-run', type=Path, help='directory containing raster, table and array solo captures')
    parser.add_argument('--offsets', type=Path, help='shared, fixed offsets JSON for a shaped run')
    parser.add_argument('--raster-alignment', type=Path)
    parser.add_argument('--policy-config', type=Path)

    def stop(signum, frame):
        raise KeyboardInterrupt('termination signal')

    signal.signal(signal.SIGTERM, stop)
    args = parser.parse_args()
    if args.shaped_run:
        if args.offsets is None or args.raster_run or args.raster_alignment:
            parser.error('--shaped-run requires --offsets and takes no legacy raster arguments')
    else:
        if args.raster_run is None or args.offsets is not None:
            parser.error('legacy runs require --raster-run and take no --offsets')
    if args.serial_run and args.raster_alignment is None:
        parser.error('--raster-alignment is required with --serial-run')
    if args.independent_run and args.raster_alignment is not None:
        parser.error('independent runs derive their offsets from their four curves')
    return runner(args).run()


if __name__ == '__main__':
    raise SystemExit(run_cli(RasterPriority))
